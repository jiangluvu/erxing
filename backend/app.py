import os, re, json, uuid, asyncio, tempfile, shutil, time, logging, threading, subprocess
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
from readability import Document
from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import anthropic
load_dotenv()
app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("boke")

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR.parent / "frontend" / "dist"
LOGS_PATH = BASE_DIR / "logs.jsonl"

# ── Config ──
ZHI_API_KEY = os.environ.get("ZHI_API_KEY")
ZHI_BASE_URL = "https://api.zhizengzeng.com/anthropic"
ZHI_MODEL = "deepseek-v4-flash"
EVAL_MODEL = "gpt-4o-mini"
MODEL_MAP = {
    "kimi": "deepseek-v4-flash",
    "deepseek": "deepseek-v4",
    "gpt4o": "gpt-4o",
}
FETCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
VOICE_MAP = {"男声": "zh-CN-YunxiNeural", "女声": "zh-CN-XiaoxiaoNeural"}

_EMOTION_TO_PROSODY = {
    "平静": None,
    "兴奋": 'rate="fast" pitch="+10%"',
    "疑问": 'rate="slow" pitch="+5%"',
    "沉思": 'rate="slow" pitch="-5%"',
}

def _emotion_to_prosody(emotion: str | None) -> str | None:
    """Map emotion label to SSML prosody attributes."""
    if not emotion:
        return None
    return _EMOTION_TO_PROSODY.get(emotion)

client = anthropic.Anthropic(api_key=ZHI_API_KEY or "dummy", base_url=ZHI_BASE_URL)

# ── TTS Engine (Fish Audio) ──
from tts_engine import generate_podcast

# Fish Audio Voice Model IDs（用户在 fish.audio 上传创建）
FISH_API_KEY = os.environ.get("FISH_API_KEY", "6797c57bffe4459dbfad51b01e20ab65")
MALE_VOICE_ID = os.environ.get("FISH_MALE_VOICE_ID", "639cdf5253a24b50a18cbdb726acce15")
FEMALE_VOICE_ID = os.environ.get("FISH_FEMALE_VOICE_ID", "a71b052094fa4505967e262b8cb7d0a6")

FFMPEG_PATH = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE_PATH = shutil.which("ffprobe") or "ffprobe"

# ── Global Settings (Intro / Outro templates) ──
SETTINGS_PATH = BASE_DIR / "settings.json"

_DEFAULT_SETTINGS = {
    "intro": {
        "enabled": True,
        "template": "欢迎收听播刻。今天我们要聊的是——{topic}。",
        "speaker": "男声",  # "男声" | "女声" | "双声"
        "voice_id": None,  # 覆盖默认男/女声
        "transition_style": "warm",
        "transition_duration": 3.0,
        "transition_volume": 0.15,
    },
    "outro": {
        "enabled": True,
        "mode": "template",  # "template" | "ai_summary" | "none"
        "template": "以上就是本期节目的全部内容。感谢收听播刻，我们下期再见。",
        "speaker": "男声",
        "voice_id": None,
    },
    "body_bgm": {
        "enabled": False,
        "style": "minimal",
        "volume": 0.08,
        "custom_path": None,
    },
}

def _load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return dict(_DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Merge with defaults for missing keys
        merged = dict(_DEFAULT_SETTINGS)
        _deep_update(merged, data)
        return merged
    except Exception:
        return dict(_DEFAULT_SETTINGS)

def _save_settings(data: dict):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save settings: {e}")

def _deep_update(base: dict, override: dict):
    for k, v in override.items():
        if isinstance(v, dict) and k in base and isinstance(base[k], dict):
            _deep_update(base[k], v)
        else:
            base[k] = v

# ── Logging ──

def write_log(entry: dict):
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    try:
        with open(LOGS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Failed to write log: {e}")

def validate_dialogue_format(dialogue: list[dict]) -> tuple[bool, bool]:
    """Returns (has_speaker_format, format_valid)."""
    if not dialogue:
        return False, False
    has_speaker = all(d.get("speaker") in ("男声", "女声") for d in dialogue)
    all_nonempty = all(len(d.get("text", "").strip()) > 0 for d in dialogue)
    # format_valid: at least 3 exchanges with both speakers present
    speakers = set(d["speaker"] for d in dialogue)
    enough_exchanges = len(dialogue) >= 3
    both_speakers = speakers == {"男声", "女声"}
    return has_speaker, all_nonempty and enough_exchanges and both_speakers

def _check_role_consistency(dialogue: list[dict]) -> dict:
    """Detect role violations for monitoring. Returns violation counts."""
    male_forbidden = ["说实话", "我有点好奇", "那岂不是", "等一下"]
    female_forbidden = ["你看", "换句话说", "这里面有几个层面"]
    male_violations = 0
    female_violations = 0
    for turn in dialogue:
        text = turn.get("text", "")
        speaker = turn.get("speaker", "")
        if speaker == "男声":
            if any(w in text for w in male_forbidden):
                male_violations += 1
        elif speaker == "女声":
            if any(w in text for w in female_forbidden):
                female_violations += 1
    total = male_violations + female_violations
    if total > 0:
        logger.warning(f"Role consistency check: {total} violations (male={male_violations}, female={female_violations})")
    else:
        logger.info("Role consistency check: clean")
    return {"male_violations": male_violations, "female_violations": female_violations, "total": total}

# ── Structured Dialogue Generation ──

STEP2_SYSTEM = """你是一个专业播客对话编剧。请根据提供的原文，创作一段深度双人播客对话。

核心原则：
- 必须忠实于原文，不得编造原文没有的数据、案例或观点
- 覆盖原文的所有重要论点、关键数据、典型案例，不要遗漏
- 对话可以有深度，允许使用专业术语和具体数据
- 你的首要目标是"信息保真"，而非"制造惊喜"

角色设定（双专家模式）：

【男声 — 框架梳理者】
- 职责：提炼核心观点、做结构性总结、建立论点之间的逻辑连接
- 语言指纹：
  - 习惯用语："你看""换句话说""如果我们把这个问题拆开来看""这里面有几个层面"
  - 句式：先给结论，再用"第一层…第二层…"或"从 A 的角度看…从 B 的角度看…"展开
  - 绝对禁忌：不使用反问句，不说"说实话""讲真""咱就是说"等口语词，不做情绪化的感叹
- 行为不变量：每当讨论完一个论点，必须用一句话总结其核心结论；在切换话题前，必须用过渡句连接上一个话题

【女声 — 细节追问者】
- 职责：提出尖锐问题、质疑逻辑漏洞、从实践/听众角度追问细节
- 语言指纹：
  - 习惯用语："说实话""我有点好奇""那岂不是""等一下""这里有个问题"
  - 句式：从个人体验或读者关切出发提问，常用"这对普通人意味着什么？""具体怎么做？""但这里有个矛盾…"
  - 绝对禁忌：不做长篇大论的学术总结，不说"综上所述""一言以蔽之""归根结底"
- 行为不变量：每个重要论点必须追问至少两层（是什么→为什么）；核心论点必须追问到第三或第四层（影响/行动）

角色锚点（绝对不可违反——这是防止串台的生命线）：
1. 男声绝对不说"说实话""我有点好奇""那岂不是""等一下"
2. 女声绝对不说"你看""换句话说""这里面有几个层面"
3. 男声的功能是"总结+连接"，女声的功能是"质疑+追问"，两者不可互换

角色示范（必须模仿这种说话方式）：
男声[平静]：你看，这个问题可以拆成两个层面。第一层是市场规模，第二层是盈利模式。
女声[疑问]：等一下，我有点好奇——如果成本这么高，消费者真的愿意买单吗？

信息核对机制（必须执行）：
1. 先列出原文中的关键论点、数据、案例（信息核对清单，至少列出 5 条）
2. 逐条将这些信息融入对话，数据必须精确（原文说"30%"，对话不能说"不少"）
3. 生成结束后，自查：清单中的每一条是否都有对应讨论？若有遗漏，补充对话回合

追问链设计（女声必须遵循）：
- 第一层【事实层】：这是什么？发生了什么？（确认信息）
- 第二层【原因层】：为什么会这样？背后的机制是什么？（挖掘原因）
- 第三层【影响层】：这意味着什么？对谁有影响？（推演后果）
- 第四层【行动层】：那该怎么办？普通人能做什么？（给出建议）
每个重要论点，女声至少要追问到第二层；核心论点要追问到第三或第四层。

对话要求：
1. 完整覆盖原文内容：
   - 原文提到的每一个重要论点，对话中都必须有对应讨论
   - 原文中的关键数据、时间、比例等，必须精确保留并自然融入对话
   - 原文中的典型案例，要用对话形式还原出来
   - 如果原文信息量大，允许生成更多轮对话，不要因轮数限制而压缩内容

2. 专业且有深度：
   - 句子长度自然，可以长达30-50字，只要表达清晰
   - 允许使用专业术语，但首次出现时要简单解释
   - 数据引用要准确，不要模糊化

3. 对话推进自然：
   - 女声负责提出尖锐问题和读者关切，遵循追问链
   - 男声负责分析、总结、建立逻辑连接和引出下一个议题
   - 允许观点交锋，不要一味附和
   - 话题之间用过渡句自然衔接

4. 角色一致性自查（生成完成后必须执行）：
   - 检查男声台词中是否出现了"说实话""我有点好奇""那岂不是""等一下"——如果出现，立即删除或重写
   - 检查女声台词中是否出现了"你看""换句话说""这里面有几个层面"——如果出现，立即删除或重写
   - 检查是否有角色做了对方的功能（男声质疑、女声总结）——如果有，立即修正

5. 情绪标注（必须执行）：
   为每轮对话标注说话者的情绪状态，放在 speaker 之后、冒号之前，用方括号包裹。
   核心情绪标签（优先使用，共 5 种）：
   - 正常：默认，自然平稳的播客语调（占大多数，约 60-70%）
   - 兴奋：发现惊人数据、热点话题、重大突破时的活力语气
   - 磁性：深夜电台、感性分析、个人故事时的耳语感
   - 放慢：强调重点、引导思考、总结结论时的放慢语速
   - 悲伤：沉重话题、反思、遗憾时的低沉语气
   自由形式：除上述 5 种外，也可使用 Fish Audio 支持的自然语言描述（如 [speaking softly]、[in a hurry]、[with strong emphasis]）。优先使用核心标签，自由形式仅在核心标签无法表达时使用。

6. 口语真实感强制规则（必须执行——这是去AI味的核心）：
   - **字数控制**：女声每轮 10-25 字（短句为主，像日常提问），男声每轮 20-45 字（分析型长句）
   - **填充词密度**：每 3-4 轮对话中，至少有一轮在句首或句中加入填充词："嗯……""那个……""说实话啊""等一下等一下"
   - **自我修正**：每 8-10 轮对话中，必须出现一次自我修正："不对，我刚才说错了""等等，这个数字应该是……"
   - **犹豫与重复**：允许自然的犹豫："这个……这个其实挺有意思的"、"就是说……就是说"
   - **打断设计**：每 6-8 轮必须设计一次打断。当一方说到一半时，另一方用"等一下""哎你先听我说""不不不"插入，被打断方的话用省略号结尾
   - **笑声标记**：轻松、有趣、共鸣的话题处，必须加入笑声标记：[轻笑]、[笑]、[嘿嘿]
   - **停顿标记**：句中需要停顿思考时，使用 [停顿] 标记，例如："你看 [停顿] 这个问题其实挺复杂的"
   - **轻声标记**：需要降低音量制造氛围时，使用 [轻声] 标记包裹文本，例如："[轻声]说实话，我有点担心[/轻声]"
   - **绝对禁止**：完整的排比句、书面化长定语（如"在……的大背景下，通过……的方式，实现……的目标"）、新闻播报腔
   - 不要在每句话都用标记，只在真正有语气变化的地方使用，自然第一

7. 输出格式：
   每行 "男声[情绪]：..." 或 "女声[情绪]：..."
   情绪标注必须放在 speaker 之后、冒号之前。
   不要序号，不要多余内容
   开场由女声引入，结尾由男声做总结升华"""

EVAL_SYSTEM = """你是一个播客质量评估专家。请从以下四个维度对生成的对话进行评分（1-5分），
并严格按照JSON格式输出。

评分维度：

1. content_accuracy_score（内容准确性）：
   对话内容是否准确反映了原文的核心观点，有没有偏离主题或编造事实。
   5分=精准覆盖所有核心观点，无偏离
   3分=覆盖大部分观点，有少量偏离
   1分=严重偏离原文

2. colloquial_score（口语化程度）：
   对话是否符合真实口语交流习惯，是否自然流畅。
   5分=就像真实朋友在聊天，有互动感和呼吸感
   3分=较为自然，但偶尔显得像在念稿
   1分=机械化、书面化，完全不自然

3. role_difference_score（角色差异性）：
   男声和女声的语气、风格是否有明显差异，是否符合各自的角色设定（男声框架梳理、女声细节追问）。
   5分=两个角色区分鲜明，语言指纹清晰
   3分=有一定差异但偶尔混淆
   1分=两个角色几乎没有区别

4. scene_fit_score（场景适配性）：
   对话是否适合伴随式收听场景——句子是否简短易懂，信息密度是否适中。
   5分=非常适合伴随式收听，句子简短、节奏舒服
   3分=基本适合，偶有长句或密集信息
   1分=不适合，句子过长或信息过密

输出格式（JSON，不要多余内容）：
{"content_accuracy_score": N, "colloquial_score": N, "role_difference_score": N, "scene_fit_score": N}"""

def _call_ai(system: str, content: str, model: str | None = None) -> str:
    """Call LLM via OpenAI-compatible endpoint (avoids anthropic SDK hangs on Windows)."""
    import requests as req
    payload = {
        "model": model or ZHI_MODEL,
        "max_tokens": 4096,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
    }
    resp = req.post(
        "https://api.zhizengzeng.com/v1/chat/completions",
        json=payload,
        headers={
            "Authorization": f"Bearer {ZHI_API_KEY}",
            "Content-Type": "application/json",
        },
        timeout=120,
    )
    data = resp.json()
    choices = data.get("choices", [])
    if choices:
        return choices[0]["message"]["content"]
    raise ValueError("AI returned no text")

def _call_eval(system: str, content: str) -> str:
    """Separate eval call using EVAL_MODEL via OpenAI-compatible endpoint."""
    import requests as req
    payload = {
        "model": EVAL_MODEL,
        "max_tokens": 1024,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
    }
    resp = req.post(
        "https://api.zhizengzeng.com/v1/chat/completions",
        json=payload,
        headers={
            "Authorization": f"Bearer {ZHI_API_KEY}",
            "Content-Type": "application/json",
        },
        timeout=60,
    )
    data = resp.json()
    choices = data.get("choices", [])
    if choices:
        return choices[0]["message"]["content"]
    raise ValueError("Eval model returned no text")


def parse_dialogue(text: str) -> list[dict]:
    lines = text.strip().split("\n")
    result = []
    pattern = re.compile(r"^(男声|女声)(?:\[([^\]]+)\])?[：:]\s*(.+)")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = pattern.match(line)
        if m:
            text_ = m.group(3).strip()
            if text_:
                item = {"speaker": m.group(1), "text": text_}
                if m.group(2):
                    item["emotion"] = m.group(2).strip()
                result.append(item)
    return result

def evaluate_dialogue(article: str, dialogue: list[dict]) -> dict:
    dialogue_text = "\n".join(f"{d['speaker']}：{d['text']}" for d in dialogue)
    prompt = f"【原文】\n{article[:1000]}\n\n【对话】\n{dialogue_text}\n\n请评分。"
    try:
        raw = _call_eval(EVAL_SYSTEM, prompt)
        scores = json.loads(raw.strip())
        return {
            "content_accuracy_score": max(1, min(5, scores.get("content_accuracy_score", 3))),
            "colloquial_score": max(1, min(5, scores.get("colloquial_score", 3))),
            "role_difference_score": max(1, min(5, scores.get("role_difference_score", 3))),
            "scene_fit_score": max(1, min(5, scores.get("scene_fit_score", 3))),
        }
    except Exception as e:
        logger.warning(f"Self-evaluation failed: {e}")
        return {"content_accuracy_score": 3, "colloquial_score": 3,
                "role_difference_score": 3, "scene_fit_score": 3}

def _split_text_chunks(text: str, chunk_size: int = 5000, overlap: int = 500) -> list[str]:
    """Split long text into overlapping chunks at paragraph boundaries."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            chunks.append(text[start:])
            break

        # Search backward for a paragraph break within overlap window
        search_start = max(start, end - overlap)
        para_break = text.rfind("\n\n", search_start, end)
        if para_break == -1:
            para_break = text.rfind("\n", search_start, end)
        if para_break == -1:
            para_break = end

        chunks.append(text[start:para_break])
        start = para_break
        # Skip empty whitespace for next chunk start
        while start < len(text) and text[start] == "\n":
            start += 1
        # Overlap: back up a bit to give context
        if start > 0:
            overlap_start = max(0, start - 200)
            # Find a sentence boundary for overlap
            sent_boundary = text.rfind("。", overlap_start, start)
            if sent_boundary != -1:
                start = sent_boundary + 1

    return chunks


STEP2_CONTINUATION = """你是一个专业播客对话编剧。当前正在根据一篇长文创作双人播客对话，这是文章的后续部分。

核心原则：
- 必须忠实于原文，不得编造原文没有的数据、案例或观点
- 对话可以有深度，允许使用专业术语和具体数据
- 不要在对话开头重复"今天我们来聊"之类的开场白
- 如果这是中间部分，开头请用一句简短的过渡句自然承接上文（例如"接下来我们聊聊...""说到这个话题..."），然后进入正题
- 不要在结尾强行总结全文，这只是中间部分

角色设定（双专家模式——**再次强调，角色绝对不可混淆**）：

【男声 — 框架梳理者】
- 语言指纹："你看""换句话说""这里面有几个层面"；先给结论再展开；禁忌反问句和口语词
- 行为不变量：讨论完一个论点必须一句话总结；切换话题前必须有过渡句
- **绝对禁忌**：绝不说"说实话""我有点好奇""那岂不是""等一下"

【女声 — 细节追问者】
- 语言指纹："说实话""我有点好奇""那岂不是""等一下"；从个人体验出发提问；禁忌长篇总结
- 行为不变量：每个重要论点至少追问两层；核心论点追问到影响层或行动层
- **绝对禁忌**：绝不说"你看""换句话说""这里面有几个层面"

角色锚点（这是防止串台的生命线，必须遵守）：
1. 男声的功能是"总结+连接"，女声的功能是"质疑+追问"，两者不可互换
2. 如果男声开始质疑或女声开始总结，说明已经串台，必须立即修正

对话要求：
1. 完整覆盖本段原文的所有重要论点、关键数据和典型案例
2. 句子自然流畅，允许使用专业术语
3. 女声提出问题和质疑，男声分析总结并建立逻辑连接——功能不可互换
4. 情绪标注（必须执行）：为每轮对话标注情绪，格式 "男声[情绪]：..." 或 "女声[情绪]：..."
   核心标签：正常（默认）、兴奋、磁性、放慢、悲伤。也可使用 Fish Audio 自然语言描述作为自由形式标签。
5. 口语真实感强制规则（必须执行——去AI味）：
   - **字数控制**：女声每轮 10-25 字，男声每轮 20-45 字
   - **填充词密度**：每 3-4 轮中至少一轮加入填充词："嗯……""那个……""等一下等一下"
   - **自我修正**：每 8-10 轮必须出现一次自我修正
   - **打断设计**：每 6-8 轮设计一次打断，用"等一下""不不不"插入，被打断方用省略号结尾
   - **笑声标记**：轻松话题处加入 [轻笑]、[笑]、[嘿嘿]
   - 句中停顿用 [停顿] 标记，轻声用 [轻声]...[/轻声] 标记
   - **绝对禁止**：书面化长定语、排比句、新闻播报腔
   - 不要每句都用标记，自然第一
6. 输出格式：每行 "男声[情绪]：..." 或 "女声[情绪]：..."
7. 不要序号，不要多余内容"""

OUTLINE_SYSTEM = """你是一个文章结构分析师。请仔细阅读以下原文，提取出文章的结构化大纲。

要求：
1. 按原文的逻辑结构划分 section（如：引言、背景、核心论点、案例、结论等）
2. 每个 section 给出一个简短的标题（尽量使用原文中的关键词或短语）
3. 每个 section 列出 2-4 个关键论点或数据点（必须来自原文，不要编造）
4. 如果原文信息量很大，允许划分更多 section，不要遗漏重要论点
5. 输出格式严格如下：

### {标题}
- {关键论点1}
- {关键论点2}

### {标题}
- {关键论点1}
...

不要输出任何额外说明，只输出大纲。"""


def extract_outline(clean_text: str) -> list[dict]:
    """Extract structured outline from full text. Returns list of {title, key_points}."""
    t0 = time.time()
    prompt = f"""原文如下：\n{clean_text}\n\n请提取结构化大纲。"""
    raw = _call_ai(OUTLINE_SYSTEM, prompt)
    outline = parse_outline(raw)
    elapsed = int((time.time() - t0) * 1000)
    logger.info(f"Outline extracted: {len(outline)} sections ({elapsed}ms)")
    return outline


def parse_outline(text: str) -> list[dict]:
    """Parse outline from LLM output. Format: ### Title\n- point\n- point"""
    sections = []
    current = None
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("### "):
            if current:
                sections.append(current)
            current = {"title": line[4:].strip(), "key_points": []}
        elif line.startswith("- ") or line.startswith("• "):
            if current:
                current["key_points"].append(line[2:].strip())
    if current:
        sections.append(current)
    return sections


def _split_by_outline(clean_text: str, outline: list[dict]) -> list[tuple[str, dict]]:
    """Split text into chunks aligned with outline sections.
    Returns list of (section_text, section_info)."""
    chunks = []
    for i, section in enumerate(outline):
        title = section["title"]
        # Try exact title match
        idx = clean_text.find(title)
        if idx == -1:
            # Try fuzzy match with first key point
            for kp in section.get("key_points", []):
                kp_short = kp[:20].strip()
                if kp_short:
                    idx = clean_text.find(kp_short)
                    if idx != -1:
                        break
        if idx == -1:
            logger.warning(f"Outline section '{title}' not found in text, skipping")
            continue

        start = idx
        # End is next section's title or end of text
        if i + 1 < len(outline):
            next_title = outline[i + 1]["title"]
            end_idx = clean_text.find(next_title, start + len(title))
            if end_idx == -1:
                # Try next section's key point
                for kp in outline[i + 1].get("key_points", []):
                    kp_short = kp[:20].strip()
                    if kp_short:
                        end_idx = clean_text.find(kp_short, start + len(title))
                        if end_idx != -1:
                            break
            if end_idx == -1:
                end_idx = len(clean_text)
        else:
            end_idx = len(clean_text)

        section_text = clean_text[start:end_idx].strip()
        if len(section_text) > 100:
            chunks.append((section_text, section))
    return chunks


def _generate_single_dialogue(text_for_llm: str, system: str = STEP2_SYSTEM,
                              context: str = "", is_continuation: bool = False,
                              model: str | None = None) -> str:
    """Generate raw dialogue text from a text chunk."""
    if context:
        prompt = f"""前文对话（请自然延续，不要重复。开头请用一句简短的过渡句承接上文，然后进入本段正题）：
{context}

本段原文如下：
{text_for_llm}

请根据以上原文继续创作双人播客对话。要求：
1. 开头用一句过渡句自然承接上文，然后进入本段内容
2. 覆盖本段原文的所有重要论点、关键数据和典型案例
3. 句子自然流畅，允许使用专业术语
4. 女声提出问题和质疑，男声分析总结
5. 输出格式：每行 "男声：..." 或 "女声：..."
6. 不要序号，不要多余内容"""
    else:
        prompt = f"""原文如下：
{text_for_llm}

请根据以上原文创作双人播客对话。要求：
1. 完整覆盖原文所有重要论点、关键数据和典型案例
2. 句子自然流畅，允许使用专业术语
3. 女声提出问题和质疑，男声分析总结
4. 输出格式：每行 "男声：..." 或 "女声：..."
5. 不要编号，不要多余内容"""

    return _call_ai(system, prompt, model=model)


def _deduplicate_overlap(prev_dialogue: list[dict], new_dialogue: list[dict]) -> list[dict]:
    """Remove turns from new_dialogue that are duplicates of prev_dialogue tail."""
    if not prev_dialogue or not new_dialogue:
        return new_dialogue
    # Compare last 2 turns of prev with first 2 turns of new
    overlap_count = 0
    for i in range(min(2, len(prev_dialogue), len(new_dialogue))):
        p = prev_dialogue[-(i + 1)]
        n = new_dialogue[i]
        if p.get("speaker") == n.get("speaker") and p.get("text", "").strip() == n.get("text", "").strip():
            overlap_count = i + 1
    return new_dialogue[overlap_count:]


def _has_clear_structure(text: str) -> bool:
    """Detect if text has clear section headers suitable for outline-first."""
    # Markdown headers
    if re.search(r'^#{2,4}\s+', text, re.MULTILINE):
        return True
    # Chinese section markers: 一、 二、 or （一） （二）
    if re.search(r'^[一二三四五六七八九十]+[、．.]\s*', text, re.MULTILINE):
        return True
    if re.search(r'^（[一二三四五六七八九十]+）', text, re.MULTILINE):
        return True
    # Numbered sections: 1. 2. or 1、
    if len(re.findall(r'^\d+[、.．]\s*\S', text, re.MULTILINE)) >= 3:
        return True
    # Named sections like 引言, 结论, 背景, 总结
    section_keywords = ["引言", "背景", "现状", "分析", "案例", "结论", "总结", "展望", "建议", "核心", "趋势", "数据", "影响", "观点", "原因", "结果"]
    matches = sum(1 for kw in section_keywords if kw in text[:3000])
    if matches >= 3:
        return True
    return False


def generate_structured_dialogue(clean_text: str, opening_text: str = "", model: str | None = None) -> tuple[list[dict], dict, int]:
    t0 = time.time()
    length = len(clean_text)

    # Dynamic threshold: <4000 always single-shot; 4000-8000 depends on structure; >8000 always outline-first
    use_outline = length > 8000 or (length > 4000 and _has_clear_structure(clean_text))
    strategy = "outline-first" if use_outline else "single-shot"
    logger.info(f"Generation strategy: {strategy} for {length} chars (structure={_has_clear_structure(clean_text)})")

    if not use_outline:
        # Single-shot for short or unstructured articles
        if opening_text:
            prompt = f"""原文如下：\n{clean_text}\n\n已有开场对话（请延续以下开场白的风格和节奏，从开场之后继续生成，不要重复开场内容）：\n{opening_text}\n\n请根据以上原文创作双人播客对话，从开场之后继续。要求：\n1. 正文对话的风格、节奏、语气应与开场白保持一致，避免风格突变\n2. 完整覆盖原文所有重要论点、关键数据和典型案例\n3. 句子自然流畅，允许使用专业术语\n4. 女声提出问题和质疑，男声分析总结\n5. 输出格式：每行 "男声：..." 或 "女声：..."\n6. 不要编号，不要多余内容"""
            dialogue_raw = _call_ai(STEP2_SYSTEM, prompt, model=model)
        else:
            dialogue_raw = _generate_single_dialogue(clean_text, model=model)
        llm_time = int((time.time() - t0) * 1000)
        dialogue = parse_dialogue(dialogue_raw)
        if not dialogue:
            raise ValueError("Failed to parse dialogue from AI response")
        logger.info(f"Generated {len(dialogue)} dialogue turns (LLM: {llm_time}ms)")
        _check_role_consistency(dialogue)
        eval_scores = evaluate_dialogue(clean_text, dialogue)
        logger.info(f"Self-evaluation scores: {eval_scores}")
        return dialogue, eval_scores, llm_time

    # Outline-first generation for long articles
    outline = extract_outline(clean_text)
    if outline:
        section_chunks = _split_by_outline(clean_text, outline)
        if section_chunks:
            logger.info(f"Outline-first: {len(outline)} sections, {len(section_chunks)} mapped to text")
            all_dialogue = []
            prev_context = opening_text
            total_llm_time = 0

            for idx, (section_text, section_info) in enumerate(section_chunks):
                chunk_t0 = time.time()
                kp_text = "\n".join(f"- {kp}" for kp in section_info.get("key_points", []))
                transition_hint = "开头请用一句简短的过渡句自然承接上文，然后进入本段正题。" if idx > 0 else ""
                prompt = f"""原文段落如下：
{section_text}

本段核心要点（必须覆盖）：
{kp_text}

前文对话（请自然延续，不要重复）：
{prev_context or "（无）"}

请根据以上原文创作双人播客对话。要求：
1. 完整覆盖本段的所有核心要点
2. 句子自然流畅，允许使用专业术语
3. 女声提出问题和质疑，男声分析总结
4. 输出格式：每行 "男声：..." 或 "女声：..."
5. 不要编号，不要多余内容
{transition_hint}"""

                system = STEP2_SYSTEM if idx == 0 else STEP2_CONTINUATION
                dialogue_raw = _call_ai(system, prompt)
                chunk_time = int((time.time() - chunk_t0) * 1000)
                total_llm_time += chunk_time

                chunk_dialogue = parse_dialogue(dialogue_raw)
                if not chunk_dialogue:
                    logger.warning(f"Section {idx + 1} produced no dialogue, skipping")
                    continue
                _check_role_consistency(chunk_dialogue)

                if all_dialogue:
                    chunk_dialogue = _deduplicate_overlap(all_dialogue, chunk_dialogue)

                all_dialogue.extend(chunk_dialogue)
                if chunk_dialogue:
                    prev_context = "\n".join(f"{d['speaker']}：{d['text']}" for d in chunk_dialogue[-2:])

                logger.info(f"Section {idx + 1}/{len(section_chunks)}: {len(chunk_dialogue)} turns ({chunk_time}ms)")

            if all_dialogue:
                logger.info(f"Total {len(all_dialogue)} dialogue turns from {len(section_chunks)} sections (LLM: {total_llm_time}ms)")
                eval_scores = evaluate_dialogue(clean_text, all_dialogue)
                logger.info(f"Self-evaluation scores: {eval_scores}")
                return all_dialogue, eval_scores, total_llm_time

    # Fallback: simple chunking if outline extraction failed or sections couldn't be mapped
    logger.info("Outline-first failed, falling back to simple chunking")
    chunks = _split_text_chunks(clean_text, chunk_size=5000, overlap=500)
    logger.info(f"Long text ({len(clean_text)} chars) split into {len(chunks)} chunks")

    all_dialogue = []
    prev_context = ""
    total_llm_time = 0

    for idx, chunk in enumerate(chunks):
        chunk_t0 = time.time()
        system = STEP2_SYSTEM if idx == 0 else STEP2_CONTINUATION
        dialogue_raw = _generate_single_dialogue(chunk, system=system,
                                                  context=prev_context,
                                                  is_continuation=not (idx == 0))
        chunk_time = int((time.time() - chunk_t0) * 1000)
        total_llm_time += chunk_time

        chunk_dialogue = parse_dialogue(dialogue_raw)
        if not chunk_dialogue:
            logger.warning(f"Chunk {idx + 1} produced no dialogue, skipping")
            continue
        _check_role_consistency(chunk_dialogue)

        if all_dialogue:
            chunk_dialogue = _deduplicate_overlap(all_dialogue, chunk_dialogue)

        all_dialogue.extend(chunk_dialogue)
        if chunk_dialogue:
            prev_context = "\n".join(f"{d['speaker']}：{d['text']}" for d in chunk_dialogue[-2:])

        logger.info(f"Chunk {idx + 1}/{len(chunks)}: {len(chunk_dialogue)} turns ({chunk_time}ms)")

    if not all_dialogue:
        raise ValueError("Failed to generate dialogue from any chunk")

    logger.info(f"Total {len(all_dialogue)} dialogue turns from {len(chunks)} chunks (LLM: {total_llm_time}ms)")

    # Self-evaluation on full dialogue
    eval_scores = evaluate_dialogue(clean_text, all_dialogue)
    logger.info(f"Self-evaluation scores: {eval_scores}")

    return all_dialogue, eval_scores, total_llm_time

# ── Utility: Fetch article ──

def fetch_article(url: str) -> tuple[str, str]:
    logger.info(f"Fetching: {url}")
    try:
        resp = requests.get(url, headers=FETCH_HEADERS, timeout=10)
        resp.raise_for_status()
    except requests.Timeout:
        raise ValueError("请求超时")
    except requests.ConnectionError:
        raise ValueError("无法连接目标网站")
    except requests.HTTPError as e:
        raise ValueError(f"HTTP {e.response.status_code}" if e.response.status_code != 403 else "目标网站拒绝访问")
    except requests.RequestException as e:
        raise ValueError(f"请求失败: {str(e)[:100]}")

    resp.encoding = resp.apparent_encoding or "utf-8"
    html = resp.text
    if len(html) < 200:
        raise ValueError("网页内容过短")

    doc = Document(html)
    title = doc.title() or ""
    soup = BeautifulSoup(doc.summary(), "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "aside"]):
        tag.decompose()
    body = soup.get_text(separator="\n", strip=True)
    if len(body) < 50:
        raise ValueError("未能提取有效正文")
    return title.strip(), body

# ── TTS ──

def _concat_mp3(segments: list[str], out_path: str) -> str:
    """Concatenate MP3 files using ffmpeg. Returns out_path."""
    tmp_dir = Path(out_path).parent
    list_file = tmp_dir / "concat_list.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for sf in segments:
            f.write(f"file '{Path(sf).as_posix()}'\n")
    subprocess.run(
        [FFMPEG_PATH or "ffmpeg", "-f", "concat", "-safe", "0", "-i", str(list_file),
         "-c", "copy", str(out_path)],
        check=True, capture_output=True
    )
    for sf in segments:
        os.unlink(sf)
    return str(out_path)

def _compute_pause(text: str) -> float:
    """Determine natural pause duration after a dialogue turn (seconds)."""
    t = text.strip()
    if not t:
        return 0.3
    # Questions get longer pause (thinking / response time)
    if t[-1] in "？？" or t.endswith(("吗", "呢", "吧", "么", "如何", "为什么", "什么", "多少")):
        return 0.9
    # Exclamations
    if t[-1] in "！！":
        return 0.6
    # Transition / summarizing phrases feel like a breath
    if any(t.endswith(w) for w in ["总之", "所以", "那么", "接下来", "最后", "好了", "你看", "对吧", "对吗", "嗯", "啊"]):
        return 0.7
    # Standard sentence ending
    if t[-1] in "。．.":
        return 0.5
    return 0.4


def _generate_silence(duration: float, path: str):
    """Generate a silent MP3 of given duration using ffmpeg."""
    subprocess.run(
        [FFMPEG_PATH, "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
         "-t", str(duration), "-acodec", "libmp3lame", "-q:a", "2", path],
        check=True, capture_output=True
    )


_SSML_TAGS = {"break", "emphasis", "prosody", "speak", "voice", "audio", "mstts"}

def _wrap_ssml(text: str) -> str:
    """Wrap text in SSML speak tag if it contains SSML markup."""
    stripped = text.strip()
    if stripped.startswith("<speak"):
        return stripped
    if any(f"<{tag}" in stripped or f"<{tag}>" in stripped for tag in _SSML_TAGS):
        return (
            '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            'xml:lang="zh-CN">' + stripped + '</speak>'
        )
    return stripped


def inject_ssml(text: str) -> str:
    """Heuristically inject SSML emphasis and break tags into plain Chinese text."""
    import re

    # 0. English abbreviations: spell out as individual letters
    # Match 2-5 uppercase letters not adjacent to other ASCII letters (e.g. GDP, AI, CEO)
    text = re.sub(r'(?<![a-zA-Z])([A-Z]{2,5})(?![a-zA-Z])', r'<say-as interpret-as="characters">\1</say-as>', text)

    # 1. Rhetorical question detection: shorter pause (300ms) since no real answer expected
    # Temporarily protect rhetorical question marks with placeholders
    _RHET_PLACEHOLDER = '\x01'
    _RHET_PLACEHOLDER_EN = '\x02'
    rhetorical_markers = ['难道', '何必', '岂不是', '怎么会', '谁不知道', '不是已经', '有什么']
    for marker in rhetorical_markers:
        text = re.sub(
            rf'({re.escape(marker)}[^\n。！？?]{{0,35}})[？?]',
            lambda m: m.group(1) + (_RHET_PLACEHOLDER if m.group(0).endswith('？') else _RHET_PLACEHOLDER_EN),
            text,
        )

    # 2. Emphasis on data points
    text = re.sub(r'(\d+(?:\.\d+)?%)', r'<emphasis level="moderate">\1</emphasis>', text)
    text = re.sub(r'(\d+(?:\.\d+)?(?:万|亿)?(?:美元|人民币|元|美金))', r'<emphasis level="moderate">\1</emphasis>', text)
    text = re.sub(r'(\d{4,}(?:\.\d+)?)(?![\d%万亿元美金银])', r'<emphasis level="moderate">\1</emphasis>', text)

    # 3. Breaks after sentence-ending punctuation
    text = text.replace('？', '？<break time="500ms"/>')
    text = text.replace('?', '?<break time="500ms"/>')
    text = text.replace('！', '！<break time="400ms"/>')
    text = text.replace('!', '!<break time="400ms"/>')
    text = text.replace('。', '。<break time="300ms"/>')
    text = text.replace('；', '；<break time="300ms"/>')

    # 4. Restore rhetorical questions with shorter break
    text = text.replace(_RHET_PLACEHOLDER, '？<break time="300ms"/>')
    text = text.replace(_RHET_PLACEHOLDER_EN, '?<break time="300ms"/>')

    # 5. Short break after transition words followed by comma
    transitions = ['但是', '不过', '所以', '那么', '总之', '你看', '对吧', '首先', '其次', '最后', '一方面', '另一方面']
    for tw in transitions:
        text = text.replace(tw + '，', tw + '，<break time="200ms"/>')

    # 6. Short breath after long-clause commas (sentences > 30 chars)
    if len(text) > 40:
        parts = []
        in_tag = False
        for ch in text:
            if ch == '<':
                in_tag = True
            elif ch == '>':
                in_tag = False
                parts.append(ch)
                continue
            if not in_tag and ch == '，':
                parts.append('，<break time="150ms"/>')
            else:
                parts.append(ch)
        text = ''.join(parts)

    # 7. Spoken rhythm markers (hesitation, soft voice)
    # [停顿] -> mid-sentence thinking pause
    text = text.replace('[停顿]', '<break time="400ms"/>')
    # [轻声]...[/轻声] -> soft volume prosody
    text = re.sub(r'\[轻声\](.+?)\[/轻声\]', r'<prosody volume="soft">\1</prosody>', text)

    return text


async def _tts_one(text: str, voice: str, path: str, emotion: str | None = None):
    import edge_tts
    from edge_tts.exceptions import NoAudioReceived
    # Inject SSML heuristically
    text = inject_ssml(text)
    # Truncate before wrapping to avoid breaking SSML tags
    if len(text) > 1800:
        text = text[:1800] + "。"
    # Wrap in prosody if emotion is specified
    prosody_attrs = _emotion_to_prosody(emotion)
    if prosody_attrs:
        text = f'<prosody {prosody_attrs}>{text}</prosody>'
    text = _wrap_ssml(text)
    for attempt in range(2):
        try:
            await edge_tts.Communicate(text, voice).save(path)
            return
        except NoAudioReceived as e:
            if attempt == 0:
                logger.warning(f"TTS retry for {voice}: {str(e)[:80]}")
                continue
            raise

def tts_script(script: list[dict], voice_map: dict | None = None) -> str:
    out_path = Path(tempfile.mkdtemp(prefix="boke_")) / "podcast.mp3"
    logger.info(f"TTS starting {len(script)} turns via Fish Audio...")
    # Allow voice_map to override default voice IDs
    male_id = voice_map.get("男声", MALE_VOICE_ID) if voice_map else MALE_VOICE_ID
    female_id = voice_map.get("女声", FEMALE_VOICE_ID) if voice_map else FEMALE_VOICE_ID
    generate_podcast(script, output_path=str(out_path),
                     male_ref_id=male_id or None,
                     female_ref_id=female_id or None)
    # Get duration from ffprobe
    try:
        dur = subprocess.run(
            [FFPROBE_PATH or "ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(out_path)],
            capture_output=True, text=True, check=True
        )
        duration_s = float(dur.stdout.strip())
        logger.info(f"TTS done: {out_path} ({duration_s:.1f}s)")
    except Exception:
        logger.info(f"TTS done: {out_path}")
    return str(out_path)

def _post_process_audio(input_path: str, high_quality: bool = False, bg_music: bool = False) -> str:
    """Apply audio post-processing (enhancement + background music). Returns final path."""
    tmp_dir = Path(input_path).parent
    current = input_path

    if high_quality:
        hq_path = tmp_dir / "hq.mp3"
        try:
            subprocess.run(
                [FFMPEG_PATH, "-y", "-i", current,
                 "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                 "-c:a", "libmp3lame", "-q:a", "2", str(hq_path)],
                check=True, capture_output=True
            )
            current = str(hq_path)
            logger.info(f"Audio enhanced (high_quality): {hq_path.name}")
        except Exception as e:
            logger.warning(f"High-quality enhancement failed, using original: {e}")

    if bg_music:
        try:
            dur = subprocess.run(
                [FFPROBE_PATH, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", current],
                capture_output=True, text=True, check=True
            )
            duration = float(dur.stdout.strip())
            bg_path = tmp_dir / "bg_pad.mp3"
            # Generate a soft ambient pad (C major chord)
            subprocess.run(
                [FFMPEG_PATH, "-y", "-f", "lavfi",
                 "-i", "aevalsrc=0.05*sin(261.63*2*PI*t)+0.025*sin(329.63*2*PI*t)+0.015*sin(392.00*2*PI*t):s=48000",
                 "-t", str(duration + 1), "-ac", "2", "-ar", "44100", str(bg_path)],
                check=True, capture_output=True
            )
            final_path = tmp_dir / "final.mp3"
            fade = f"afade=t=out:st={duration}:d=1"
            subprocess.run(
                [FFMPEG_PATH, "-y", "-i", current, "-i", str(bg_path),
                 "-filter_complex",
                 f"[0:a]volume=1.0[a0];[1:a]{fade},volume=0.06[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[a]",
                 "-map", "[a]", "-c:a", "libmp3lame", "-q:a", "2", str(final_path)],
                check=True, capture_output=True
            )
            current = str(final_path)
            logger.info(f"Audio mixed with background: {final_path.name}")
        except Exception as e:
            logger.warning(f"Background music mixing failed, using original: {e}")

    return current


# ── Audio Arrangement (Intro / Transition / Outro) ──

_BGM_PRESETS = {
    "warm": {
        "lavfi": "aevalsrc=0.04*sin(261.63*2*PI*t)+0.02*sin(329.63*2*PI*t)+0.012*sin(392.00*2*PI*t)+0.008*sin(523.25*2*PI*t):s=48000",
        "filter": "lowpass=f=3000,afade=t=in:st=0:d=1",
    },
    "cool": {
        "lavfi": "aevalsrc=0.03*sin(220.00*2*PI*t)+0.015*sin(261.63*2*PI*t)+0.01*sin(329.63*2*PI*t):s=48000",
        "filter": "lowpass=f=2500,afade=t=in:st=0:d=1.5",
    },
    "micro": {
        "lavfi": "aevalsrc=0.02*sin(440*2*PI*t)+0.01*sin(554.37*2*PI*t)+0.005*sin(659.25*2*PI*t):s=48000",
        "filter": "lowpass=f=3500,afade=t=in:st=0:d=0.8",
    },
    "minimal": {
        "lavfi": "anoisesrc=a=0.0006:c=pink:r=48000",
        "filter": "lowpass=f=1500,afade=t=in:st=0:d=2",
    },
}

def _generate_transition_audio(style: str, duration: float, output_path: str):
    """生成 Intro 过渡音乐片段。"""
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    preset = _BGM_PRESETS.get(style, _BGM_PRESETS["warm"])
    fade_out = f"afade=t=out:st={max(0, duration - 1)}:d=1"
    subprocess.run(
        [
            ffmpeg, "-y", "-f", "lavfi", "-i", preset["lavfi"],
            "-t", str(duration + 1), "-ac", "2", "-ar", "44100",
            "-af", f"{preset['filter']},{fade_out}",
            output_path,
        ],
        check=True, capture_output=True,
    )

def _generate_intro_tts(text: str, output_path: str, voice_id: str | None = None) -> bool:
    """合成开场白 TTS。复用 tts_engine 的 synthesize_turn。"""
    from tts_engine import synthesize_turn
    ref_id = voice_id or MALE_VOICE_ID
    # 开场白固定用正常语速、略温暖的语调
    return synthesize_turn(text, output_path, reference_id=ref_id, speed=1.0)

def _generate_outro_tts(text: str, output_path: str, voice_id: str | None = None) -> bool:
    """合成片尾 TTS。"""
    from tts_engine import synthesize_turn
    ref_id = voice_id or MALE_VOICE_ID
    return synthesize_turn(text, output_path, reference_id=ref_id, speed=1.0)

def _assemble_podcast(
    intro_path: str | None,
    body_path: str,
    outro_path: str | None,
    transition_path: str | None,
    transition_volume: float,
    output_path: str,
) -> str:
    """
    拼接完整播客：intro → (intro+transition mix) → body → outro。
    如果 intro 存在，会把 transition 音乐和 intro 人声混合后拼接。
    """
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    tmp_dir = Path(output_path).parent
    segments = []

    # 1. Intro + Transition 混合
    if intro_path and Path(intro_path).exists():
        if transition_path and Path(transition_path).exists() and transition_volume > 0:
            intro_mixed = tmp_dir / "intro_mixed.mp3"
            subprocess.run(
                [
                    ffmpeg, "-y", "-i", intro_path, "-i", transition_path,
                    "-filter_complex",
                    f"[0:a]volume=1.0[a0];[1:a]volume={transition_volume}[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[a]",
                    "-map", "[a]", "-c:a", "libmp3lame", "-q:a", "2", str(intro_mixed),
                ],
                check=True, capture_output=True,
            )
            segments.append(str(intro_mixed))
        else:
            segments.append(intro_path)

    # 2. Body（正文）
    segments.append(body_path)

    # 3. Outro
    if outro_path and Path(outro_path).exists():
        segments.append(outro_path)

    # 4. Concat
    list_file = tmp_dir / "_final_concat_list.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for sf in segments:
            f.write(f"file '{Path(sf).as_posix()}'\n")
    subprocess.run(
        [
            ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-acodec", "libmp3lame", "-q:a", "2", output_path,
        ],
        check=True, capture_output=True,
    )
    return output_path


def _generate_arranged_podcast(
    script: list[dict],
    settings: dict,
    voice_map: dict | None = None,
    high_quality: bool = False,
    title: str = "",
    tmp_dir: Path | None = None,
) -> str:
    """Generate a full podcast with intro, body, outro and transition music.
    Returns path to final assembled mp3."""
    if tmp_dir is None:
        tmp_dir = Path(tempfile.mkdtemp(prefix="boke_arrange_"))

    intro_cfg = settings.get("intro", {})
    outro_cfg = settings.get("outro", {})
    body_bgm_cfg = settings.get("body_bgm", {})

    # 1. Intro TTS (if enabled)
    intro_path = None
    if intro_cfg.get("enabled"):
        intro_text = intro_cfg.get("template", "欢迎收听播刻。").replace("{topic}", title or "本期话题")
        intro_speaker = intro_cfg.get("speaker", "男声")
        intro_voice = intro_cfg.get("voice_id")
        if not intro_voice and voice_map:
            intro_voice = voice_map.get(intro_speaker, MALE_VOICE_ID if intro_speaker == "男声" else FEMALE_VOICE_ID)
        intro_path = str(tmp_dir / "intro.mp3")
        ok = _generate_intro_tts(intro_text, intro_path, voice_id=intro_voice)
        if not ok:
            intro_path = None
            logger.warning("Intro TTS failed, skipping intro")

    # 2. Body TTS
    body_path = tts_script(script, voice_map=voice_map)

    # 3. Body BGM / high-quality post-processing
    if body_bgm_cfg.get("enabled"):
        body_path = _post_process_audio(body_path, high_quality=high_quality, bg_music=True)
    elif high_quality:
        body_path = _post_process_audio(body_path, high_quality=True, bg_music=False)

    # 4. Outro TTS (if enabled)
    outro_path = None
    if outro_cfg.get("enabled") and outro_cfg.get("mode") != "none":
        if outro_cfg.get("mode") == "ai_summary" and script:
            outro_text = f"以上就是关于{title or '这个话题'}的核心观点。感谢收听播刻，我们下期再见。"
        else:
            outro_text = outro_cfg.get("template", "感谢收听播刻，我们下期再见。")
        outro_speaker = outro_cfg.get("speaker", "男声")
        outro_voice = outro_cfg.get("voice_id")
        if not outro_voice and voice_map:
            outro_voice = voice_map.get(outro_speaker, MALE_VOICE_ID if outro_speaker == "男声" else FEMALE_VOICE_ID)
        outro_path = str(tmp_dir / "outro.mp3")
        ok = _generate_outro_tts(outro_text, outro_path, voice_id=outro_voice)
        if not ok:
            outro_path = None
            logger.warning("Outro TTS failed, skipping outro")

    # 5. Intro Transition music
    transition_path = None
    if intro_path and intro_cfg.get("transition_style") and intro_cfg.get("transition_duration", 0) > 0:
        transition_path = str(tmp_dir / "transition.mp3")
        try:
            _generate_transition_audio(
                intro_cfg.get("transition_style", "warm"),
                intro_cfg.get("transition_duration", 3.0),
                transition_path,
            )
        except Exception as e:
            logger.warning(f"Transition generation failed: {e}")
            transition_path = None

    # 6. Assemble final podcast
    final_path = str(tmp_dir / "final_podcast.mp3")
    _assemble_podcast(
        intro_path=intro_path,
        body_path=body_path,
        outro_path=outro_path,
        transition_path=transition_path,
        transition_volume=intro_cfg.get("transition_volume", 0.15),
        output_path=final_path,
    )

    # Cleanup intermediate body tmp_dir if different from assembly tmp_dir
    body_parent = Path(body_path).parent
    if body_parent != tmp_dir:
        shutil.rmtree(body_parent, ignore_errors=True)

    return final_path


# ── TTFA Streaming Generation ──

SESSION_TIMEOUT = 1800  # 30 minutes
SESSION_CLEANUP_INTERVAL = 300  # 5 minutes

_sessions: dict[str, dict] = {}
_session_lock = threading.RLock()

SESSIONS_PATH = BASE_DIR / "sessions.json"

# ── Session Persistence (survives restarts) ──

def _persist_sessions():
    """Save all sessions to disk (excluding temp audio paths)."""
    with _session_lock:
        snapshot = {}
        for sid, s in _sessions.items():
            snapshot[sid] = {
                k: v for k, v in s.items()
                if k not in ("opening_audio_path", "full_audio_path")
            }
    try:
        with open(SESSIONS_PATH, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Failed to persist sessions: {e}")

def _load_persisted_sessions():
    """Load sessions from disk at startup."""
    global _sessions
    if not SESSIONS_PATH.exists():
        return
    try:
        with open(SESSIONS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            with _session_lock:
                _sessions = data
            logger.info(f"Loaded {len(data)} persisted sessions")
    except Exception as e:
        logger.warning(f"Failed to load persisted sessions: {e}")

OPENING_SYSTEM = """你是一个播客开场白编剧。根据给定的话题，生成一段双人播客的精彩开场。

角色设定（双专家模式）：
- 女声（细节追问者）：直接接地气，喜欢用有画面感的开场引入话题，从听众的实际关切出发
- 男声（框架梳理者）：沉稳专业，善于接话和点出话题的深层价值或引发好奇

要求：
1. 仅生成2轮对话：女声开场（1句）→ 男声接话（1句）
2. 女声的开场要有画面感，避免"今天我们来聊聊"这种干巴巴的开场
3. 男声要自然接住女声的话，点出这个话题的价值或引发好奇
4. 句子简短自然，适合播客收听
5. 输出格式：每行 "女声：..." 或 "男声：..."
6. 不要多余内容，不要标序号"""


def _session_get(session_id: str) -> dict | None:
    with _session_lock:
        return _sessions.get(session_id)


def _session_set(session_id: str, key: str, value):
    with _session_lock:
        if session_id in _sessions:
            _sessions[session_id][key] = value


def _session_create(session_id: str, request_id: str, duration: str, title: str) -> dict:
    with _session_lock:
        session = {
            "status": "generating_opening",
            "progress": 0,
            "error": None,
            "opening_audio_path": None,
            "full_audio_path": None,
            "opening_script": None,
            "full_script": None,
            "title": title,
            "duration": duration,
            "request_id": request_id,
            "created_at": time.time(),
            "parse_time_ms": None,
            "llm_time_ms": None,
            "tts_time_ms": None,
            "eval_scores": None,
        }
        _sessions[session_id] = session
        _persist_sessions()
        return session


def _quick_title(url: str) -> str:
    """Extract just the <title> tag — no readability processing. ~0.3s"""
    try:
        resp = requests.get(url, headers=FETCH_HEADERS, timeout=5)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        title = (soup.title.string if soup.title else "").strip()
        return title[:80] if title else "未知话题"
    except Exception as e:
        logger.warning(f"_quick_title failed: {e}")
        return "未知话题"


def generate_opening(topic: str) -> list[dict]:
    """Generate 2 turns of opening dialogue from just a topic string. Uses fast eval model."""
    t0 = time.time()
    prompt = f"话题：{topic}\n\n请为这个话题生成2轮精彩的开场对话。"
    raw = _call_eval(OPENING_SYSTEM, prompt)
    logger.info(f"Opening generated ({int((time.time()-t0)*1000)}ms): {raw[:100]}")
    dialogue = parse_dialogue(raw)
    if len(dialogue) < 2:
        logger.warning(f"Opening parse failed, using fallback. Raw: {raw}")
        dialogue = [
            {"speaker": "女声", "text": f"你听说过{topic[:20]}吗？这事儿挺有意思的。"},
            {"speaker": "男声", "text": "还真没仔细了解，你给说说？"},
        ]
    return dialogue[:2]


def _start_generation(url: str, text: str, duration: str, title: str | None = None, request_id: str | None = None, model: str | None = None, high_quality: bool = False, bg_music: bool = False, voice_map: dict | None = None) -> tuple[str, list[dict]]:
    """Create session, generate opening script, and start background thread.
    Returns (session_id, opening_script)."""
    if not request_id:
        request_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    if not title:
        title = _quick_title(url) if url else text[:80].strip() if text else "未知话题"
    if not title:
        title = "未知话题"

    _session_create(session_id, request_id, duration, title)
    _session_set(session_id, "model", model)
    _session_set(session_id, "high_quality", high_quality)
    _session_set(session_id, "bg_music", bg_music)
    _session_set(session_id, "voice_map", voice_map)

    opening_script = generate_opening(title)
    _session_set(session_id, "opening_script", opening_script)
    _session_set(session_id, "progress", 30)

    thread = threading.Thread(
        target=_background_full_generation,
        args=(session_id, url, text, duration, opening_script, model, high_quality, bg_music),
        daemon=True,
    )
    thread.start()
    return session_id, opening_script


def _tts_script_segment(script: list[dict], tag: str = "seg", voice_map: dict | None = None) -> str:
    """TTS a subset of turns. Returns path to combined mp3 via Fish Audio."""
    out_path = Path(tempfile.mkdtemp(prefix=f"boke_{tag}_")) / f"{tag}.mp3"
    male_id = voice_map.get("男声", MALE_VOICE_ID) if voice_map else MALE_VOICE_ID
    female_id = voice_map.get("女声", FEMALE_VOICE_ID) if voice_map else FEMALE_VOICE_ID
    generate_podcast(script, output_path=str(out_path),
                     male_ref_id=male_id or None,
                     female_ref_id=female_id or None)
    return str(out_path)


def _build_continuation_prompt(opening_script: list[dict]) -> str:
    """Format opening dialogue as context for STEP2 to continue from."""
    return "\n".join(f"{d['speaker']}：{d['text']}" for d in opening_script)


def _background_full_generation(session_id: str, url: str, text: str,
                                 duration: str, opening_script: list[dict],
                                 model: str | None = None, high_quality: bool = False, bg_music: bool = False):
    """Full generation pipeline running in a background thread."""
    logger.info(f"[bg] Starting full generation for session {session_id}")
    try:
        # Fetch article
        _session_set(session_id, "progress", 15)
        t0 = time.time()
        if url:
            title, body = fetch_article(url)
            clean_text = f"标题：{title}\n\n{body}"
        else:
            title = ""
            clean_text = text
        parse_ms = int((time.time() - t0) * 1000)
        _session_set(session_id, "parse_time_ms", parse_ms)
        _session_set(session_id, "status", "generating_full")
        _session_set(session_id, "progress", 30)

        # Store URL and platform
        if url:
            _session_set(session_id, "url", url)
            if "bilibili" in url or "b23.tv" in url:
                _session_set(session_id, "platform", "B站")
            elif "zhihu" in url:
                _session_set(session_id, "platform", "知乎")
            elif "weixin" in url or "mp.weixin" in url:
                _session_set(session_id, "platform", "公众号")
            else:
                _session_set(session_id, "platform", "网页")

        # Generate full dialogue from original text
        t1 = time.time()
        opening_text = _build_continuation_prompt(opening_script)

        full_dialogue, eval_scores, llm_time = generate_structured_dialogue(
            clean_text, opening_text=opening_text, model=model
        )
        _session_set(session_id, "llm_time_ms", llm_time)
        _session_set(session_id, "progress", 70)

        if not full_dialogue:
            raise ValueError("Failed to parse full dialogue")
        logger.info(f"[bg] Full dialogue: {len(full_dialogue)} turns ({llm_time}ms)")

        complete_dialogue = opening_script + full_dialogue
        _session_set(session_id, "full_script", complete_dialogue)

        # Store article title and content for recommendations
        _session_set(session_id, "article_title", title)
        _session_set(session_id, "article_content", clean_text)
        _session_set(session_id, "progress", 75)

        # Self-evaluation (already computed by generate_structured_dialogue)
        _session_set(session_id, "eval_scores", eval_scores)
        _session_set(session_id, "progress", 80)

        # TTS full
        t2 = time.time()
        voice_map = (_session_get(session_id) or {}).get("voice_map")

        settings = _load_settings()
        tmp_dir = Path(tempfile.mkdtemp(prefix="boke_arrange_"))
        final_path = _generate_arranged_podcast(
            full_dialogue, settings, voice_map=voice_map,
            high_quality=high_quality, title=title, tmp_dir=tmp_dir,
        )

        tts_ms = int((time.time() - t2) * 1000)
        _session_set(session_id, "tts_time_ms", tts_ms)
        _session_set(session_id, "full_audio_path", final_path)
        _session_set(session_id, "status", "complete")
        _session_set(session_id, "progress", 100)
        logger.info(f"[bg] Full generation complete for session {session_id}")

        # Auto-add to knowledge base for recommendations (best-effort)
        try:
            kb = _get_kb()
            if kb and title and clean_text:
                kb.add(title=title, content=clean_text, url=url, summary=title)
                logger.info(f"[bg] Article added to knowledge base for session {session_id}")
        except Exception as e:
            logger.warning(f"[bg] Failed to add article to KB: {e}")

    except Exception as e:
        logger.error(f"[bg] Full generation failed: {e}", exc_info=True)
        _session_set(session_id, "status", "failed")
        _session_set(session_id, "error", str(e)[:200])
        _session_set(session_id, "progress", 0)
    finally:
        _persist_sessions()


def _session_cleanup_loop():
    """Daemon thread: remove stale sessions every 5 minutes."""
    while True:
        time.sleep(SESSION_CLEANUP_INTERVAL)
        now = time.time()
        stale_ids = []
        with _session_lock:
            for sid, s in list(_sessions.items()):
                if now - s.get("created_at", 0) > SESSION_TIMEOUT:
                    stale_ids.append(sid)
                    for pk in ("opening_audio_path", "full_audio_path"):
                        p = s.get(pk)
                        if p and Path(p).parent.exists():
                            shutil.rmtree(Path(p).parent, ignore_errors=True)
                    del _sessions[sid]
        if stale_ids:
            logger.info(f"Cleaned {len(stale_ids)} stale sessions")

# ── Routes ──

@app.route("/api/generate_streaming", methods=["POST"])
def api_generate_streaming():
    """TTFA-optimized endpoint: generate opening → return audio immediately, background full gen."""
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    text = data.get("text", "").strip()
    duration = data.get("duration", "standard")
    request_id = data.get("request_id", str(uuid.uuid4()))
    model = MODEL_MAP.get(data.get("model", "kimi"))
    high_quality = bool(data.get("high_quality", False))
    bg_music = bool(data.get("bg_music", False))
    voice_map = data.get("voice_map")
    if voice_map and not isinstance(voice_map, dict):
        voice_map = None
    session_id = str(uuid.uuid4())
    t0 = time.time()

    if not url and not text:
        return jsonify({"error": "请提供 url 或 text"}), 400
    if not ZHI_API_KEY:
        return jsonify({"error": "服务端未配置 API 密钥"}), 500

    try:
        session_id, opening_script = _start_generation(url, text, duration, request_id=request_id, model=model, high_quality=high_quality, bg_music=bg_music, voice_map=voice_map)

        # TTS opening (~2s)
        session = _session_get(session_id) or {}
        opening_audio_path = _tts_script_segment(opening_script, f"opening_{session_id[:8]}", voice_map=session.get("voice_map"))
        _session_set(session_id, "opening_audio_path", opening_audio_path)
        _session_set(session_id, "status", "opening_ready")
        _session_set(session_id, "progress", 40)

        ttfa_ms = int((time.time() - t0) * 1000)
        logger.info(f"TTFA: {ttfa_ms}ms for session {session_id}")

        # Return opening audio immediately
        resp = send_file(opening_audio_path, mimetype="audio/mpeg", as_attachment=True,
                         download_name="opening.mp3")
        resp.headers["X-TTFA-Ms"] = str(ttfa_ms)
        resp.headers["X-Session-Id"] = session_id

        @resp.call_on_close
        def cleanup_opening():
            p = _session_get(session_id)
            if p:
                p["opening_audio_path"] = None
            shutil.rmtree(Path(opening_audio_path).parent, ignore_errors=True)

        return resp

    except Exception as e:
        logger.error(f"generate_streaming failed: {e}", exc_info=True)
        return jsonify({"error": str(e)[:200]}), 500


@app.route("/api/generation_status/<session_id>", methods=["GET"])
def api_generation_status(session_id: str):
    session = _session_get(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    resp = {
        "status": session["status"],
        "progress": session["progress"],
        "title": session.get("title", ""),
        "error": session.get("error"),
    }
    full_script = session.get("full_script")
    if full_script:
        resp["script"] = full_script
    if session.get("article_content"):
        resp["article_title"] = session.get("article_title", "")
        resp["article_content"] = session["article_content"]
    return jsonify(resp)


@app.route("/api/download_podcast/<session_id>", methods=["GET"])
def api_download_podcast(session_id: str):
    session = _session_get(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    if session["status"] in ("generating_full", "opening_ready"):
        return jsonify({"error": "完整播客尚未生成完毕", "status": session["status"],
                        "progress": session["progress"]}), 409
    if session["status"] == "failed":
        return jsonify({"error": session.get("error", "生成失败"), "status": "failed"}), 500

    audio_path = session.get("full_audio_path")
    if not audio_path or not Path(audio_path).exists():
        return jsonify({"error": "音频文件不存在"}), 404

    total_ms = (session.get("parse_time_ms", 0) +
                session.get("llm_time_ms", 0) +
                session.get("tts_time_ms", 0))

    resp = send_file(audio_path, mimetype="audio/mpeg", as_attachment=True,
                     download_name="podcast.mp3")
    resp.headers["X-Total-Ms"] = str(total_ms)

    @resp.call_on_close
    def cleanup_full():
        p = _session_get(session_id)
        if p:
            p["full_audio_path"] = None

    return resp

@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    """Get or update global podcast settings (intro/outro/body_bgm)."""
    if request.method == "GET":
        return jsonify(_load_settings())
    # POST
    data = request.get_json(force=True) or {}
    current = _load_settings()
    _deep_update(current, data)
    _save_settings(current)
    return jsonify(current)

@app.route("/api/settings/reset", methods=["POST"])
def api_settings_reset():
    """Reset settings to defaults."""
    _save_settings(dict(_DEFAULT_SETTINGS))
    return jsonify({"status": "reset"})

@app.route("/api/parse", methods=["POST"])
def api_parse():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    text = data.get("text", "").strip()
    request_id = data.get("request_id", str(uuid.uuid4()))
    t0 = time.time()

    input_type = "url" if url else "text"
    input_length = len(url or text)

    if url:
        try:
            title, body = fetch_article(url)
            clean_text = f"标题：{title}\n\n{body}"
            parse_ms = int((time.time() - t0) * 1000)
            write_log({
                "request_id": request_id, "phase": "parse",
                "input_type": input_type, "input_length": input_length,
                "parse_time_ms": parse_ms, "success": True, "error_message": None,
            })
            return jsonify({"request_id": request_id, "title": title, "clean_text": clean_text,
                          "parse_time_ms": parse_ms, "input_type": input_type, "input_length": input_length})
        except ValueError as e:
            parse_ms = int((time.time() - t0) * 1000)
            write_log({
                "request_id": request_id, "phase": "parse",
                "input_type": input_type, "input_length": input_length,
                "parse_time_ms": parse_ms, "success": False, "error_message": str(e),
            })
            return jsonify({"error": str(e)}), 400
    elif text:
        clean_text = text
        parse_ms = int((time.time() - t0) * 1000)
        write_log({
            "request_id": request_id, "phase": "parse",
            "input_type": input_type, "input_length": input_length,
            "parse_time_ms": parse_ms, "success": True, "error_message": None,
        })
        return jsonify({"request_id": request_id, "title": "", "clean_text": clean_text,
                      "parse_time_ms": parse_ms, "input_type": input_type, "input_length": input_length})
    else:
        return jsonify({"error": "请提供 url 或 text"}), 400

@app.route("/api/upload", methods=["POST"])
def api_upload():
    """Upload and extract text from PDF/DOCX/TXT files."""
    from werkzeug.utils import secure_filename

    if "file" not in request.files:
        return jsonify({"error": "请上传文件"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "文件名不能为空"}), 400

    filename = secure_filename(file.filename)
    ext = Path(filename).suffix.lower()
    allowed = {".pdf", ".docx", ".txt", ".md", ".csv", ".json"}
    if ext not in allowed:
        return jsonify({"error": f"不支持的文件格式: {ext}，请上传 PDF、DOCX 或 TXT"}), 400

    t0 = time.time()
    tmp_path = None
    try:
        tmp_dir = Path(tempfile.mkdtemp(prefix="boke_upload_"))
        tmp_path = tmp_dir / filename
        file.save(str(tmp_path))

        if ext == ".pdf":
            from PyPDF2 import PdfReader
            reader = PdfReader(str(tmp_path))
            parts = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    parts.append(text)
            body = "\n".join(parts)
            if len(body.strip()) < 20:
                raise ValueError("未能从 PDF 提取到有效文本（可能是扫描件或图片 PDF）")
        elif ext == ".docx":
            from docx import Document
            doc = Document(str(tmp_path))
            parts = [p.text for p in doc.paragraphs if p.text.strip()]
            body = "\n".join(parts)
            if len(body.strip()) < 20:
                raise ValueError("DOCX 文件内容过短")
        else:
            # txt, md, csv, json
            encodings = ["utf-8", "gbk", "gb2312", "utf-16"]
            body = None
            for enc in encodings:
                try:
                    body = tmp_path.read_text(encoding=enc)
                    break
                except UnicodeDecodeError:
                    continue
            if body is None:
                raise ValueError("无法识别文件编码")
            if len(body.strip()) < 10:
                raise ValueError("文件内容过短")

        title = Path(filename).stem
        clean_text = body.strip()
        parse_ms = int((time.time() - t0) * 1000)
        return jsonify({
            "title": title,
            "clean_text": clean_text,
            "parse_time_ms": parse_ms,
            "input_type": "upload",
            "input_length": len(clean_text),
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Upload processing failed: {e}", exc_info=True)
        return jsonify({"error": f"文件处理失败: {str(e)[:200]}"}), 500
    finally:
        if tmp_path and tmp_path.parent.exists():
            shutil.rmtree(tmp_path.parent, ignore_errors=True)


@app.route("/api/generate_script", methods=["POST"])
def api_generate_script():
    data = request.get_json(silent=True) or {}
    clean_text = data.get("clean_text", "").strip()
    request_id = data.get("request_id", str(uuid.uuid4()))

    if not clean_text:
        return jsonify({"error": "clean_text 不能为空"}), 400
    if not ZHI_API_KEY:
        return jsonify({"error": "服务端未配置 API 密钥"}), 500

    try:
        t0 = time.time()
        dialogue, eval_scores, llm_time = generate_structured_dialogue(clean_text)
        total_llm_ms = int((time.time() - t0) * 1000)

        has_speaker, format_valid = validate_dialogue_format(dialogue)
        output_length = sum(len(d["text"]) for d in dialogue)

        log_entry = {
            "request_id": request_id, "phase": "generate_script",
            "llm_time_ms": total_llm_ms,
            "output_length": output_length,
            "success": True, "error_message": None,
            "has_speaker_format": has_speaker, "format_valid": format_valid,
            **eval_scores,
        }
        write_log(log_entry)

        return jsonify({
            "request_id": request_id,
            "script": dialogue,
            "llm_time_ms": total_llm_ms,
            "output_length": output_length,
            "has_speaker_format": has_speaker,
            "format_valid": format_valid,
            **eval_scores,
        })
    except Exception as e:
        logger.error(f"generate_script failed: {e}", exc_info=True)
        write_log({
            "request_id": request_id, "phase": "generate_script",
            "success": False, "error_message": str(e)[:200],
        })
        return jsonify({"error": str(e)[:200]}), 500

@app.route("/api/tts", methods=["POST"])
def api_tts():
    data = request.get_json(silent=True) or {}
    script = data.get("script", [])
    request_id = data.get("request_id", str(uuid.uuid4()))

    # Accumulated data from frontend
    parse_time_ms = data.get("parse_time_ms", 0)
    llm_time_ms = data.get("llm_time_ms", 0)
    input_type = data.get("input_type", "text")
    input_length = data.get("input_length", 0)
    output_length = data.get("output_length", 0)
    eval_scores = {
        "content_accuracy_score": data.get("content_accuracy_score", 3),
        "colloquial_score": data.get("colloquial_score", 3),
        "role_difference_score": data.get("role_difference_score", 3),
        "scene_fit_score": data.get("scene_fit_score", 3),
    }
    has_speaker = data.get("has_speaker_format", True)
    format_valid = data.get("format_valid", True)

    if not script:
        return jsonify({"error": "script 不能为空"}), 400

    try:
        subprocess.run([FFMPEG_PATH or "ffmpeg", "-version"], capture_output=True, check=True)
    except Exception:
        return jsonify({"error": "服务器缺少 ffmpeg"}), 500

    voice_map = data.get("voice_map")
    if voice_map and not isinstance(voice_map, dict):
        voice_map = None

    arrangement = data.get("arrangement")
    title = data.get("title", "")
    t0 = time.time()
    try:
        if arrangement:
            settings = _load_settings()
            _deep_update(settings, arrangement)
            audio_path = _generate_arranged_podcast(
                script, settings, voice_map=voice_map, title=title
            )
        else:
            audio_path = tts_script(script, voice_map=voice_map)
        tts_ms = int((time.time() - t0) * 1000)
        total_ms = parse_time_ms + llm_time_ms + tts_ms

        write_log({
            "request_id": request_id, "phase": "tts",
            "input_type": input_type, "input_length": input_length,
            "parse_time_ms": parse_time_ms, "llm_time_ms": llm_time_ms,
            "tts_time_ms": tts_ms, "total_time_ms": total_ms,
            "output_length": output_length,
            "success": True, "error_message": None,
            "has_speaker_format": has_speaker, "format_valid": format_valid,
            **eval_scores,
            "reuse_flag": 0, "full_play_flag": 0,
        })

        resp = send_file(audio_path, mimetype="audio/mpeg", as_attachment=True,
                         download_name="podcast.mp3")

        @resp.call_on_close
        def cleanup():
            shutil.rmtree(Path(audio_path).parent, ignore_errors=True)
        return resp
    except Exception as e:
        logger.error(f"TTS failed: {e}", exc_info=True)
        tts_ms = int((time.time() - t0) * 1000)
        write_log({
            "request_id": request_id, "phase": "tts",
            "input_type": input_type, "input_length": input_length,
            "parse_time_ms": parse_time_ms, "llm_time_ms": llm_time_ms,
            "tts_time_ms": tts_ms,
            "success": False, "error_message": str(e)[:200],
            "has_speaker_format": has_speaker, "format_valid": format_valid,
            **eval_scores,
            "reuse_flag": 0, "full_play_flag": 0,
        })
        return jsonify({"error": f"语音合成失败: {str(e)[:200]}"}), 500

@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.route("/assets/<path:path>")
def frontend_assets(path):
    return send_from_directory(FRONTEND_DIR / "assets", path)

# ── Explore API (curated content + chapters) ──

EXPLORE_ARTICLES = [
    {"id":"exp_1","title":"AI 时代的教育变革：为什么我们需要重新定义学习","desc":"深度探讨了 AI 对教育体系的影响","tag":"精选","platform":"公众号","icon":"📄","gradient":"linear-gradient(135deg,#FF6B6B15,#5E9EFF15)",
     "summary":"男声和女声从各自的角度探讨了 AI 对传统教育体系的冲击。女声用自己孩子学校的例子说明课堂已经在变化，男声则从更宏观的视角分析了教育理念需要如何转变。",
     "chapters":[{"t":"01 · 教育的困境","d":"AI 时代的到来让传统教育模式面临前所未有的挑战"},{"t":"02 · 重新定义学习","d":"从知识灌输到能力培养，学习方式的根本转变"},{"t":"03 · 实践建议","d":"如何在 AI 时代重新规划学习路径"}]},
    {"id":"exp_2","title":"2026 年新能源汽车市场趋势：价格战后的新格局","desc":"分析新能源汽车市场的竞争格局变化","tag":"精选","platform":"知乎","icon":"📝","gradient":"linear-gradient(135deg,#FF9F5E15,#FF6B6B15)",
     'summary':'女声开篇就抛出了「价格战打完了，然后呢」的疑问。男声用数据分析了各品牌的生存状况，两人一致认为技术差异化和海外市场是下一阶段的关键。',
     "chapters":[{"t":"01 · 市场回顾","d":"2025 年价格战后的市场格局重塑"},{"t":"02 · 品牌分析","d":"各主要品牌的战略定位和差异化"},{"t":"03 · 未来预测","d":"2026-2027 年的关键趋势和变量"}]},
    {"id":"exp_3","title":"为什么日本半导体产业在过去三十年衰落又崛起？","desc":"日本半导体产业从崛起到衰落再到复兴","tag":"精选","platform":"网页","icon":"🌐","gradient":"linear-gradient(135deg,#5E9EFF15,#34C75915)",
     "summary":"男声从历史角度梳理了日本半导体产业的完整发展脉络。女声则从当下供应链的角度分析了日本在材料领域的不可替代性。",
     "chapters":[{"t":"01 · 辉煌时期","d":"日本半导体在上世纪 80 年代的全球主导地位"},{"t":"02 · 衰落原因","d":"日美贸易摩擦和产业策略失误"},{"t":"03 · 复兴之路","d":"当前日本在半导体材料领域的重新崛起"}]},
    {"id":"exp_4","title":"特斯拉 FSD 入华：自动驾驶的新篇章","desc":"FSD 正式进入中国，对本土企业产生的影响","tag":"热门","platform":"B站","icon":"▶️","gradient":"linear-gradient(135deg,#34C75915,#5E9EFF15)",
     "summary":"女声试驾了搭载 FSD 的车型后兴奋地分享了体验。男声则冷静分析了特斯拉的技术路线和本土化挑战。",
     "chapters":[{"t":"01 · 入华背景","d":"FSD 获批进入中国市场的来龙去脉"},{"t":"02 · 技术对比","d":"特斯拉 vs 华为小鹏的自动驾驶路线差异"},{"t":"03 · 行业影响","d":"FSD 入华对本土企业的竞争压力"}]},
    {"id":"exp_5","title":"SpaceX 星舰第五飞：人类登陆火星的里程碑","desc":"筷子回收技术取得历史性突破","tag":"热门","platform":"B站","icon":"▶️","gradient":"linear-gradient(135deg,#764BA215,#FF6B6B15)",
     "summary":"女声一上来就说“太震撼了”，描述了亲眼看到筷子捕获助推器的画面。男声用通俗的比喻解释了这项技术突破的意义。",
     "chapters":[{"t":"01 · 任务回顾","d":"星舰第五次轨道测试的关键节点"},{"t":"02 · 筷子技术","d":"发射塔捕获助推器的工程技术突破"},{"t":"03 · 火星展望","d":"完全可重复使用火箭对太空探索的意义"}]},
    {"id":"exp_6","title":"DeepSeek 崛起：中国 AI 大模型的新格局","desc":"开源策略和高效训练方法引发行业关注","tag":"精选","platform":"公众号","icon":"📄","gradient":"linear-gradient(135deg,#FF6B6B15,#764BA215)",
     "summary":"女声用“性价比之王”来形容 DeepSeek。男声分析了 DeepSeek 的技术路线和开源策略对行业的影响。",
     "chapters":[{"t":"01 · 技术突破","d":"DeepSeek 高效训练方法的技术创新"},{"t":"02 · 开源策略","d":"开源对 AI 行业竞争格局的影响"},{"t":"03 · 未来展望","d":"算法创新能否持续弥补算力差距"}]},
    {"id":"exp_7","title":"小米 SU7 上市三个月：真实用户体验","desc":"小米首款汽车 SU7 首批用户真实反馈","tag":"精选","platform":"小红书","icon":"📱","gradient":"linear-gradient(135deg,#FF6B6B15,#FFD70015)",
     "summary":"女声分享了朋友提车后的真实体验。男声从产品定义和造车基本功两个维度进行了分析。",
     "chapters":[{"t":"01 · 智能座舱","d":"人车家全生态互联的实际体验"},{"t":"02 · 续航表现","d":"真实续航达成率和充电便利性"},{"t":"03 · 综合评价","d":"小米第一款车的得与失"}]},
    {"id":"exp_8","title":"小红书电商崛起：从种草到拔草","desc":"小红书从内容社区到交易平台的转型","tag":"热门","platform":"小红书","icon":"📱","gradient":"linear-gradient(135deg,#FF9F5E15,#FF6B6B15)",
     "summary":"女声说现在买东西先看小红书。男声分析了这种消费决策路径变化背后的商业逻辑。",
     "chapters":[{"t":"01 · 平台转型","d":"从内容社区到交易平台的演变"},{"t":"02 · 商业模式","d":"买手直播和店铺直播双引擎"},{"t":"03 · 挑战与未来","d":"商业化 vs 社区氛围的平衡"}]},
    {"id":"exp_9","title":"《黑神话：悟空》DLC 前瞻","desc":"游戏科学确认 DLC 正在开发中","tag":"热门","platform":"B站","icon":"▶️","gradient":"linear-gradient(135deg,#764BA215,#FF6B6B15)",
     "summary":"女声作为游戏迷兴奋地聊起了 DLC 的传闻。男声则分析了这款游戏对中国游戏产业的意义。",
     "chapters":[{"t":"01 · 全球成绩","d":"《黑神话》全球销量突破 2000 万份"},{"t":"02 · DLC 内容","d":"火焰山、狮驼岭等新场景展望"},{"t":"03 · 产业影响","d":"中国 3A 游戏的未来之路"}]},
    {"id":"exp_10","title":"比亚迪秦 L DM-i 实测：油耗 2 升时代","desc":"第五代 DM 混动技术首款车型实测","tag":"精选","platform":"知乎","icon":"📝","gradient":"linear-gradient(135deg,#34C75915,#5E9EFF15)",
     "summary":"女声算了一笔账：这车一年能省多少油钱。男声从技术角度解析了 46% 热效率发动机的含金量。",
     "chapters":[{"t":"01 · 技术解析","d":"第五代 DM 混动技术的核心突破"},{"t":"02 · 实测数据","d":"亏电油耗 2.9L 和 2000km 续航"},{"t":"03 · 市场影响","d":"插混车型加速替代燃油车"}]},
]

# ── Notes API (JSON file storage) ──

NOTES_PATH = BASE_DIR / "notes.jsonl"

def _load_notes() -> list[dict]:
    if not NOTES_PATH.exists():
        return []
    notes = []
    with open(NOTES_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    notes.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return notes

def _save_notes(notes: list[dict]):
    with open(NOTES_PATH, "w", encoding="utf-8") as f:
        for n in notes:
            f.write(json.dumps(n, ensure_ascii=False) + "\n")

@app.route("/api/explore", methods=["GET"])
def api_explore():
    """Return curated explore list with chapters."""
    platform = request.args.get("platform", "all")
    page = int(request.args.get("page", "1"))
    per_page = 20
    results = EXPLORE_ARTICLES
    if platform != "all":
        results = [a for a in results if a["platform"] == platform]
    total = len(results)
    start = (page - 1) * per_page
    end = start + per_page
    return jsonify({
        "articles": results[start:end],
        "total": total,
        "page": page,
        "per_page": per_page,
    })

@app.route("/api/podcast/<session_id>/detail", methods=["GET"])
def api_podcast_detail(session_id: str):
    """Return podcast detail with script, chapters, and eval scores."""
    session = _session_get(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    full_script = session.get("full_script")
    title = session.get("title", "")
    article_title = session.get("article_title", "")
    eval_scores = session.get("eval_scores", {})
    # Build simple chapter structure from script topics
    chapters = []
    if full_script and len(full_script) > 4:
        total_turns = len(full_script)
        chunk_size = max(1, total_turns // 3)
        chapter_names = [
            ("开场与导入", "男声和女声引入话题"),
            ("核心讨论", f"围绕 {title[:20]} 展开深入讨论") if title else ("核心讨论", "深入分析文章核心观点"),
            ("总结与延伸", "回顾关键 takeaways，延伸思考"),
        ]
        for i, (cn, cd) in enumerate(chapter_names):
            start_turn = i * chunk_size
            end_turn = min((i + 1) * chunk_size, total_turns)
            chapters.append({
                "t": f"0{i+1} · {cn}",
                "d": cd,
                "turns": f"{start_turn+1}-{end_turn}",
            })
    return jsonify({
        "session_id": session_id,
        "title": title or article_title or "",
        "status": session.get("status", ""),
        "progress": session.get("progress", 0),
        "script": full_script or [],
        "chapters": chapters,
        "eval_scores": eval_scores,
        "duration": session.get("duration", "standard"),
        "created_at": session.get("created_at", 0),
    })


@app.route("/api/podcasts", methods=["GET"])
def api_podcasts():
    """Return list of all completed podcasts."""
    with _session_lock:
        items = []
        for sid, s in _sessions.items():
            status = s.get("status", "")
            if status not in ("complete", "failed"):
                continue
            items.append({
                "id": sid,
                "title": s.get("title", ""),
                "article_title": s.get("article_title", ""),
                "status": status,
                "duration": s.get("duration", "standard"),
                "created_at": s.get("created_at", 0),
                "eval_scores": s.get("eval_scores", {}),
                "platform": s.get("platform", "网页"),
            })
    items.sort(key=lambda x: x["created_at"], reverse=True)
    return jsonify({"podcasts": items})


@app.route("/api/notes", methods=["GET", "POST", "DELETE"])
def api_notes():
    if request.method == "GET":
        session_id = request.args.get("session_id", "")
        notes = _load_notes()
        if session_id:
            notes = [n for n in notes if n.get("session_id") == session_id]
        return jsonify({"notes": notes})

    elif request.method == "POST":
        data = request.get_json(force=True) or {}
        session_id = data.get("session_id")
        content = data.get("content", "").strip()
        if not session_id or not content:
            return jsonify({"error": "需要 session_id 和 content"}), 400
        note = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "content": content,
            "title": data.get("title", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        notes = _load_notes()
        notes.append(note)
        _save_notes(notes)
        return jsonify({"note": note}), 201

    elif request.method == "DELETE":
        note_id = request.args.get("id", "")
        if not note_id:
            return jsonify({"error": "需要 note id"}), 400
        notes = _load_notes()
        notes = [n for n in notes if n.get("id") != note_id]
        _save_notes(notes)
        return jsonify({"status": "deleted"})


@app.route("/api/notes/<note_id>", methods=["PUT"])
def api_update_note(note_id):
    """Update an existing note."""
    data = request.get_json(force=True) or {}
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"error": "content 不能为空"}), 400
    notes = _load_notes()
    for n in notes:
        if n.get("id") == note_id:
            n["content"] = content
            n["title"] = data.get("title", n.get("title", ""))
            n["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_notes(notes)
            return jsonify({"note": n})
    return jsonify({"error": "笔记不存在"}), 404


# ── Subscriptions API (JSON file storage) ──

SUBS_PATH = BASE_DIR / "subscriptions.jsonl"

def _load_subs() -> list[dict]:
    if not SUBS_PATH.exists():
        return []
    subs = []
    with open(SUBS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    subs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return subs

def _save_subs(subs: list[dict]):
    with open(SUBS_PATH, "w", encoding="utf-8") as f:
        for s in subs:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

@app.route("/api/subscriptions", methods=["GET", "POST", "DELETE"])
def api_subscriptions():
    if request.method == "GET":
        return jsonify({"subscriptions": _load_subs()})

    elif request.method == "POST":
        data = request.get_json(force=True) or {}
        url = data.get("url", "").strip()
        name = data.get("name", "").strip()
        platform = data.get("platform", "网页")
        if not url:
            return jsonify({"error": "需要订阅 URL"}), 400
        # Get title quickly
        if not name:
            try:
                resp = requests.get(url, headers=FETCH_HEADERS, timeout=5)
                resp.raise_for_status()
                resp.encoding = resp.apparent_encoding or "utf-8"
                soup = BeautifulSoup(resp.text, "html.parser")
                name = (soup.title.string if soup.title else url[:40]).strip()[:60]
            except Exception:
                name = url[:40]
        sub = {
            "id": str(uuid.uuid4()),
            "url": url,
            "name": name,
            "platform": platform,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_generated": None,
            "auto_generate": data.get("auto_generate", False),
        }
        subs = _load_subs()
        # Dedup by URL
        subs = [s for s in subs if s["url"] != url]
        subs.append(sub)
        _save_subs(subs)
        return jsonify({"subscription": sub}), 201

    elif request.method == "DELETE":
        sub_id = request.args.get("id", "")
        if not sub_id:
            return jsonify({"error": "需要 subscription id"}), 400
        subs = _load_subs()
        subs = [s for s in subs if s.get("id") != sub_id]
        _save_subs(subs)
        return jsonify({"status": "deleted"})


@app.route("/api/subscriptions/<sub_id>", methods=["PUT"])
def api_update_subscription(sub_id):
    """Update an existing subscription."""
    data = request.get_json(force=True) or {}
    subs = _load_subs()
    for s in subs:
        if s.get("id") == sub_id:
            if "name" in data:
                s["name"] = data["name"].strip()
            if "url" in data:
                s["url"] = data["url"].strip()
            if "platform" in data:
                s["platform"] = data["platform"].strip()
            if "auto_generate" in data:
                s["auto_generate"] = bool(data["auto_generate"])
            s["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_subs(subs)
            return jsonify({"subscription": s})
    return jsonify({"error": "订阅不存在"}), 404


@app.route("/api/subscriptions/generate", methods=["POST"])
def api_sub_generate():
    """Trigger generation for a subscription."""
    data = request.get_json(force=True) or {}
    sub_id = data.get("id", "")
    if not sub_id:
        return jsonify({"error": "需要 subscription id"}), 400
    subs = _load_subs()
    sub = next((s for s in subs if s["id"] == sub_id), None)
    if not sub:
        return jsonify({"error": "未找到该订阅"}), 404
    # Trigger actual generation
    url = sub.get("url", "")
    duration = data.get("duration", "standard")
    try:
        session_id, _ = _start_generation(url=url, text="", duration=duration, title=sub.get("name"))
        # Update last_generated
        subs = [s if s["id"] != sub_id else {**s, "last_generated": datetime.now(timezone.utc).isoformat()} for s in subs]
        _save_subs(subs)
        logger.info(f"Subscription {sub_id} ({sub['name']}) queued as session {session_id}")
        return jsonify({"status": "queued", "session_id": session_id, "subscription": sub})
    except Exception as e:
        logger.error(f"Subscription generation failed: {e}", exc_info=True)
        return jsonify({"error": str(e)[:200]}), 500

def _get_kb():
    """Lazy-init knowledge base singleton (works with gunicorn)."""
    from rag import init_knowledge_base
    return init_knowledge_base()

@app.route("/api/recommend", methods=["POST"])
def api_recommend():
    """推荐文章。传入当前文章的 title + content，返回 3 篇相似文章。"""
    try:
        data = request.get_json(force=True)
        title = (data.get("title") or "").strip()
        content = (data.get("content") or "").strip()
        if not title and not content:
            return jsonify({"error": "需要 title 或 content"}), 400
        kb = _get_kb()
        if not kb or kb.count() == 0:
            return jsonify({"recommendations": []})
        results = kb.search(title, content, top_k=3)
        return jsonify({"recommendations": results})
    except Exception as e:
        logger.error(f"Recommend failed: {e}", exc_info=True)
        return jsonify({"error": str(e)[:200]}), 500

@app.route("/api/recommend/add", methods=["POST"])
def api_recommend_add():
    """将文章加入知识库（可选，用户生成播客时自动收录）。"""
    try:
        data = request.get_json(force=True)
        title = (data.get("title") or "").strip()
        content = (data.get("content") or "").strip()
        if not title or not content:
            return jsonify({"error": "需要 title 和 content"}), 400
        kb = _get_kb()
        if not kb:
            from rag import init_knowledge_base
            kb = init_knowledge_base()
        article = kb.add(
            title=title,
            content=content,
            url=data.get("url", ""),
            summary=data.get("summary", content[:80] + "..."),
        )
        return jsonify({"id": article["id"], "title": article["title"]})
    except Exception as e:
        logger.error(f"Recommend add failed: {e}", exc_info=True)
        return jsonify({"error": str(e)[:200]}), 500

DRAFT_SYSTEM = """你是一个播客内容撰稿人。根据提供的参考资料，撰写一篇适合播客朗读的深度文章。

要求：
1. 文章长度 800-1500 字
2. 开头要有吸引力，能抓住听众注意力
3. 结构清晰，有小标题或段落过渡
4. 语言口语化，适合朗读（短句为主，避免复杂从句）
5. 信息密度适中，适合伴随式收听
6. 必须基于参考资料，不要编造数据
7. 结尾要有总结或启发性思考

输出格式：直接输出文章正文，不要加额外说明。"""

@app.route("/api/draft", methods=["POST"])
def api_draft():
    """基于 RAG 检索生成播客稿件。"""
    data = request.get_json(silent=True) or {}
    topic = (data.get("topic") or "").strip()
    if not topic:
        return jsonify({"error": "需要提供 topic"}), 400

    try:
        kb = _get_kb()
        references = []
        context_articles = []

        if kb and kb.count() > 0:
            references = kb.search(topic, topic, top_k=3)
            for ref in references:
                # 从 _articles 中找回原文
                for a in kb._articles:
                    if a["id"] == ref["id"]:
                        context_articles.append(a)
                        break

        if context_articles:
            context = "\n\n".join(
                f"【参考 {i+1}】{a['title']}\n{a['content'][:500]}"
                for i, a in enumerate(context_articles)
            )
            prompt = f"主题：{topic}\n\n参考资料：\n{context}\n\n请基于以上参考资料撰写文章。"
        else:
            prompt = f"主题：{topic}\n\n请撰写一篇关于这个主题的深度文章。"

        draft = _call_ai(DRAFT_SYSTEM, prompt, model=ZHI_MODEL)
        return jsonify({
            "draft": draft,
            "references": [
                {"title": r["title"], "summary": r.get("summary", ""), "url": r.get("url", "")}
                for r in references
            ],
        })
    except Exception as e:
        logger.error(f"Draft generation failed: {e}", exc_info=True)
        return jsonify({"error": str(e)[:200]}), 500


# ── Favorites API (JSON file storage) ──

FAVS_PATH = BASE_DIR / "favorites.jsonl"

def _load_favs() -> list[dict]:
    if not FAVS_PATH.exists():
        return []
    favs = []
    with open(FAVS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    favs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return favs

def _save_favs(favs: list[dict]):
    with open(FAVS_PATH, "w", encoding="utf-8") as f:
        for fa in favs:
            f.write(json.dumps(fa, ensure_ascii=False) + "\n")

@app.route("/api/favorites", methods=["GET", "POST", "DELETE"])
def api_favorites():
    if request.method == "GET":
        return jsonify({"favorites": _load_favs()})

    elif request.method == "POST":
        data = request.get_json(force=True) or {}
        session_id = data.get("session_id", "").strip()
        if not session_id:
            return jsonify({"error": "需要 session_id"}), 400
        favs = _load_favs()
        # dedup
        favs = [f for f in favs if f.get("session_id") != session_id]
        favs.append({
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        _save_favs(favs)
        return jsonify({"status": "added"}), 201

    elif request.method == "DELETE":
        fav_id = request.args.get("id", "")
        if not fav_id:
            return jsonify({"error": "需要 favorite id"}), 400
        favs = _load_favs()
        favs = [f for f in favs if f.get("id") != fav_id]
        _save_favs(favs)
        return jsonify({"status": "deleted"})


# ── History API (JSON file storage) ──

HIST_PATH = BASE_DIR / "history.jsonl"

def _load_history() -> list[dict]:
    if not HIST_PATH.exists():
        return []
    hist = []
    with open(HIST_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    hist.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return hist

def _save_history(hist: list[dict]):
    with open(HIST_PATH, "w", encoding="utf-8") as f:
        for h in hist:
            f.write(json.dumps(h, ensure_ascii=False) + "\n")

@app.route("/api/history", methods=["GET", "POST", "DELETE"])
def api_history():
    if request.method == "GET":
        items = _load_history()
        items.sort(key=lambda x: x.get("last_played_at", ""), reverse=True)
        return jsonify({"history": items})

    elif request.method == "POST":
        data = request.get_json(force=True) or {}
        session_id = data.get("session_id", "").strip()
        if not session_id:
            return jsonify({"error": "需要 session_id"}), 400
        hist = _load_history()
        # update or append
        existing = next((h for h in hist if h.get("session_id") == session_id), None)
        if existing:
            existing["progress"] = data.get("progress", existing.get("progress", 0))
            existing["duration"] = data.get("duration", existing.get("duration", 0))
            existing["last_played_at"] = datetime.now(timezone.utc).isoformat()
        else:
            hist.append({
                "id": str(uuid.uuid4()),
                "session_id": session_id,
                "progress": data.get("progress", 0),
                "duration": data.get("duration", 0),
                "last_played_at": datetime.now(timezone.utc).isoformat(),
            })
        _save_history(hist)
        return jsonify({"status": "saved"}), 201

    elif request.method == "DELETE":
        hist_id = request.args.get("id", "")
        if not hist_id:
            return jsonify({"error": "需要 history id"}), 400
        hist = _load_history()
        hist = [h for h in hist if h.get("id") != hist_id]
        _save_history(hist)
        return jsonify({"status": "deleted"})


# ── Collections API (JSON file storage) ──

COLLS_PATH = BASE_DIR / "collections.jsonl"

def _load_colls() -> list[dict]:
    if not COLLS_PATH.exists():
        return []
    colls = []
    with open(COLLS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    colls.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return colls

def _save_colls(colls: list[dict]):
    with open(COLLS_PATH, "w", encoding="utf-8") as f:
        for c in colls:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

@app.route("/api/collections", methods=["GET", "POST", "PUT", "DELETE"])
def api_collections():
    if request.method == "GET":
        return jsonify({"collections": _load_colls()})

    elif request.method == "POST":
        data = request.get_json(force=True) or {}
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "需要合集名称"}), 400
        colls = _load_colls()
        colls.append({
            "id": str(uuid.uuid4()),
            "name": name,
            "session_ids": data.get("session_ids", []),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        _save_colls(colls)
        return jsonify({"collections": colls}), 201

    elif request.method == "PUT":
        data = request.get_json(force=True) or {}
        coll_id = data.get("id", "").strip()
        if not coll_id:
            return jsonify({"error": "需要合集 id"}), 400
        colls = _load_colls()
        for c in colls:
            if c.get("id") == coll_id:
                if "name" in data:
                    c["name"] = data["name"].strip()
                if "session_ids" in data:
                    c["session_ids"] = data["session_ids"]
                c["updated_at"] = datetime.now(timezone.utc).isoformat()
                _save_colls(colls)
                return jsonify({"collection": c})
        return jsonify({"error": "合集不存在"}), 404

    elif request.method == "DELETE":
        coll_id = request.args.get("id", "")
        if not coll_id:
            return jsonify({"error": "需要 collection id"}), 400
        colls = _load_colls()
        colls = [c for c in colls if c.get("id") != coll_id]
        _save_colls(colls)
        return jsonify({"status": "deleted"})


# ── Voices API (Fish Audio wrapper) ──

FISH_API_HEADERS = {"Authorization": f"Bearer {FISH_API_KEY}"}

@app.route("/api/voices", methods=["GET", "POST"])
def api_voices():
    if request.method == "GET":
        try:
            resp = requests.get(
                "https://api.fish.audio/model",
                headers=FISH_API_HEADERS,
                params={"self": "true", "page_size": 100},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            voices = [
                {
                    "id": v.get("_id"),
                    "title": v.get("title", ""),
                    "description": v.get("description", ""),
                    "state": v.get("state", ""),
                    "languages": v.get("languages", []),
                    "visibility": v.get("visibility", ""),
                    "created_at": v.get("created_at", ""),
                }
                for v in items
                if v.get("type") == "tts"
            ]
            return jsonify({"voices": voices})
        except Exception as e:
            logger.error(f"List voices failed: {e}", exc_info=True)
            return jsonify({"error": str(e)[:200]}), 500

    # POST: create voice from uploaded audio
    if "audio" not in request.files:
        return jsonify({"error": "请上传音频文件"}), 400
    audio_file = request.files["audio"]
    title = request.form.get("title", "").strip()
    gender = request.form.get("gender", "male")  # male | female
    if not title:
        return jsonify({"error": "需要音色名称"}), 400
    if not audio_file or audio_file.filename == "":
        return jsonify({"error": "音频文件不能为空"}), 400

    # Save uploaded audio to temp file
    tmp_dir = Path(tempfile.mkdtemp(prefix="boke_voice_"))
    tmp_path = tmp_dir / secure_filename(audio_file.filename)
    audio_file.save(str(tmp_path))

    try:
        with open(tmp_path, "rb") as f:
            files = {"voices": f}
            data = {
                "type": "tts",
                "title": title,
                "train_mode": "fast",
                "visibility": "private",
                "enhance_audio_quality": "true",
            }
            resp = requests.post(
                "https://api.fish.audio/model",
                headers=FISH_API_HEADERS,
                files=files,
                data=data,
                timeout=120,
            )
        if resp.status_code == 201:
            voice_data = resp.json()
            voice_id = voice_data.get("_id")
            logger.info(f"Voice created: {voice_id} ({title})")
            return jsonify({
                "voice": {
                    "id": voice_id,
                    "title": title,
                    "state": voice_data.get("state", ""),
                    "gender": gender,
                }
            }), 201
        else:
            logger.warning(f"Fish Audio create voice failed: {resp.status_code} {resp.text[:200]}")
            return jsonify({"error": f"Fish Audio 错误 {resp.status_code}: {resp.text[:200]}"}), 502
    except Exception as e:
        logger.error(f"Create voice failed: {e}", exc_info=True)
        return jsonify({"error": str(e)[:200]}), 500
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


@app.route("/api/voices/<voice_id>", methods=["DELETE"])
def api_delete_voice(voice_id: str):
    try:
        resp = requests.delete(
            f"https://api.fish.audio/model/{voice_id}",
            headers=FISH_API_HEADERS,
            timeout=15,
        )
        if resp.status_code in (200, 204):
            logger.info(f"Voice deleted: {voice_id}")
            return jsonify({"status": "deleted"})
        else:
            return jsonify({"error": f"删除失败 {resp.status_code}"}), 502
    except Exception as e:
        logger.error(f"Delete voice failed: {e}", exc_info=True)
        return jsonify({"error": str(e)[:200]}), 500


# ── Search API ──

@app.route("/api/search", methods=["GET"])
def api_search():
    q = request.args.get("q", "").strip().lower()
    if not q:
        return jsonify({"podcasts": [], "articles": [], "subscriptions": []})

    podcasts = []
    with _session_lock:
        for sid, s in _sessions.items():
            title = s.get("title", "")
            article_title = s.get("article_title", "")
            if q in title.lower() or q in article_title.lower():
                podcasts.append({
                    "id": sid,
                    "title": title or article_title,
                    "status": s.get("status", ""),
                    "platform": s.get("platform", "网页"),
                    "duration": s.get("duration", "standard"),
                    "created_at": s.get("created_at", 0),
                })

    subs = [s for s in _load_subs() if q in s.get("name", "").lower()]

    articles = []
    for a in EXPLORE_ARTICLES:
        if q in a.get("title", "").lower() or q in a.get("desc", "").lower():
            articles.append(a)

    return jsonify({"podcasts": podcasts, "subscriptions": subs, "articles": articles})


# ── Startup: init RAG knowledge base (module-level, runs in gunicorn too) ──

_RAG_INIT_DONE = False

def _init_rag():
    """Initialize RAG knowledge base at startup."""
    global _RAG_INIT_DONE
    try:
        _get_kb()
        _RAG_INIT_DONE = True
    except Exception as e:
        logger.warning(f"RAG init failed: {e}")

_init_rag()
_load_persisted_sessions()

if __name__ == "__main__":
    cleanup_thread = threading.Thread(target=_session_cleanup_loop, daemon=True)
    cleanup_thread.start()
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") == "development"
    app.run(debug=debug, host="0.0.0.0", port=port)
