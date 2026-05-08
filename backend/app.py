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
import anthropic
load_dotenv()
app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("erxing")

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
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
VOICE_MAP = {"小羊": "zh-CN-YunxiNeural", "小姜": "zh-CN-XiaoxiaoNeural"}

client = anthropic.Anthropic(api_key=ZHI_API_KEY or "dummy", base_url=ZHI_BASE_URL)

FFMPEG_PATH = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE_PATH = shutil.which("ffprobe") or "ffprobe"

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
    has_speaker = all(d.get("speaker") in ("小羊", "小姜") for d in dialogue)
    all_nonempty = all(len(d.get("text", "").strip()) > 0 for d in dialogue)
    # format_valid: at least 3 exchanges with both speakers present
    speakers = set(d["speaker"] for d in dialogue)
    enough_exchanges = len(dialogue) >= 3
    both_speakers = speakers == {"小羊", "小姜"}
    return has_speaker, all_nonempty and enough_exchanges and both_speakers

# ── Structured Dialogue Generation ──

STEP1_SYSTEM = """你是一个文章分析器。请提取文章的核心观点，输出格式要求：
每行一个观点，格式为 "关键词：一句话总结"
输出3-5个核心观点，不要多余内容。"""

STEP2_SYSTEM = """你是一个播客对话编剧。根据文章核心观点创作一段双人播客对话。

角色设定：
- 小羊（主持人）：沉稳温和，善于引导话题、总结观点。说话有条理，带点幽默感。
- 小姜（嘉宾）：性格直爽，从实用角度出发思考问题。说话接地气，喜欢用自己的生活经历或身边见闻来佐证观点。也喜欢反问和追问来推进话题。偶尔会打断小羊的总结来补充不同视角。

对话要求：

1. 开场要有吸引力：
   - 最好由小姜用一句有画面感的开场引入话题
   - 避免"今天我们来聊聊""最近有一个新闻"这种干巴巴的开场
   - 开场要自然融入对话，听起来像真人聊天的第一句话

2. 自然口语化：
   - 使用语气词：嗯、啊、对吧、就是说、其实吧、那
   - 短句为主，单句尽量不超过20个字
   - 表达方式要多样自然，避免固定话术反复出现

3. 对话节奏：
   - 不要固定"总结→质疑→回应"的结构，让对话自然流动
   - 小姜的表达应多样化：有时用经历佐证，有时反问质疑，有时简单附和
   - 允许插话和附和（"对"、"没错"、"还真是"）
   - 话题之间要有自然过渡

4. 车载场景适配：
   - 句子简短，一听就懂
   - 信息密度适中，不要堆砌数字和术语
   - 节奏有松有紧，听完不累

5. 角色差异化：
   - 小羊：稳重，句子完整，带知识性
   - 小姜：直接接地气，从"我"的视角出发

输出格式：每行 "小羊：..." 或 "小姜：..."，不要多余内容。
总对话轮数：{round_count}轮。"""

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
   小羊和小姜的语气、风格是否有明显差异，是否符合各自的角色设定。
   5分=两个角色区分鲜明，性格特点突出
   3分=有一定差异但偶尔混淆
   1分=两个角色几乎没有区别

4. scene_fit_score（场景适配性）：
   对话是否适合车载通勤场景收听——句子是否简短易懂，信息密度是否适中。
   5分=非常适合开车听，句子简短、节奏舒服
   3分=基本适合，偶有长句或密集信息
   1分=不适合，句子过长或信息过密

输出格式（JSON，不要多余内容）：
{"content_accuracy_score": N, "colloquial_score": N, "role_difference_score": N, "scene_fit_score": N}"""

DURATION_MAP = {"short": 5, "standard": 10, "long": 15}

def _call_ai(system: str, content: str, model: str | None = None) -> str:
    resp = client.messages.create(
        model=model or ZHI_MODEL, max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": content}],
    )
    for block in resp.content:
        if hasattr(block, "text"):
            return block.text
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
    pattern = re.compile(r"^(小羊|小姜)[：:]\s*(.+)")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = pattern.match(line)
        if m:
            text_ = m.group(2).strip()
            if text_:
                result.append({"speaker": m.group(1), "text": text_})
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

def generate_structured_dialogue(clean_text: str, duration: str = "standard") -> tuple[list[dict], dict]:
    t0 = time.time()
    key_points_raw = _call_ai(STEP1_SYSTEM, f"请分析以下文章的核心观点：\n\n{clean_text}")
    logger.info(f"Key points: {key_points_raw[:200]}")

    round_count = DURATION_MAP.get(duration, 10)
    prompt = f"""文章核心观点：
{key_points_raw}

要求：生成约{round_count}轮对话。严格按照对话结构：开场→逐条讨论观点→结尾。"""
    dialogue_raw = _call_ai(STEP2_SYSTEM, prompt)
    llm_time = int((time.time() - t0) * 1000)

    dialogue = parse_dialogue(dialogue_raw)
    if not dialogue:
        raise ValueError("Failed to parse dialogue from AI response")
    logger.info(f"Generated {len(dialogue)} dialogue turns (LLM: {llm_time}ms)")

    # Self-evaluation
    eval_scores = evaluate_dialogue(clean_text, dialogue)
    logger.info(f"Self-evaluation scores: {eval_scores}")

    return dialogue, eval_scores, llm_time

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

async def _tts_one(text: str, voice: str, path: str):
    import edge_tts
    await edge_tts.Communicate(text, voice).save(path)

def tts_script(script: list[dict]) -> str:
    tmp_dir = Path(tempfile.mkdtemp(prefix="erxing_"))
    segments = []
    for i, item in enumerate(script):
        voice = VOICE_MAP.get(item["speaker"], "zh-CN-XiaoxiaoNeural")
        out = tmp_dir / f"seg_{i:04d}.mp3"
        logger.info(f"TTS [{i+1}/{len(script)}] {item['speaker']}")
        asyncio.run(_tts_one(item["text"], voice, str(out)))
        segments.append(str(out))

    out_path = tmp_dir / "podcast.mp3"
    _concat_mp3(segments, str(out_path))
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

角色设定：
- 小姜（嘉宾）：直接接地气，喜欢用有画面感的开场引入话题
- 小羊（主持人）：沉稳温和，善于接话和点出话题价值

要求：
1. 仅生成2轮对话：小姜开场（1句）→ 小羊接话（1句）
2. 小姜的开场要有画面感，避免"今天我们来聊聊"这种干巴巴的开场
3. 小羊要自然接住小姜的话，点出这个话题的价值或引发好奇
4. 句子简短自然，适合车载收听
5. 输出格式：每行 "小姜：..." 或 "小羊：..."
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
            {"speaker": "小姜", "text": f"你听说过{topic[:20]}吗？这事儿挺有意思的。"},
            {"speaker": "小羊", "text": "还真没仔细了解，你给说说？"},
        ]
    return dialogue[:2]


def _start_generation(url: str, text: str, duration: str, title: str | None = None, request_id: str | None = None, model: str | None = None, high_quality: bool = False, bg_music: bool = False) -> tuple[str, list[dict]]:
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


def _tts_script_segment(script: list[dict], tag: str = "seg") -> str:
    """TTS a subset of turns. Returns path to combined mp3. Parallelizes TTS calls."""
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"erxing_{tag}_"))
    segments = [None] * len(script)
    def _do_tts(i, item):
        voice = VOICE_MAP.get(item["speaker"], "zh-CN-XiaoxiaoNeural")
        out = tmp_dir / f"seg_{i:04d}.mp3"
        asyncio.run(_tts_one(item["text"], voice, str(out)))
        return i, str(out)
    with ThreadPoolExecutor(max_workers=min(len(script), 4)) as pool:
        futures = [pool.submit(_do_tts, i, item) for i, item in enumerate(script)]
        for f in as_completed(futures):
            i, path = f.result()
            segments[i] = path
    out_path = tmp_dir / f"{tag}.mp3"
    _concat_mp3(segments, str(out_path))
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

        # STEP1: key points
        t1 = time.time()
        key_points_raw = _call_ai(STEP1_SYSTEM, f"请分析以下文章的核心观点：\n\n{clean_text}", model=model)
        _session_set(session_id, "progress", 50)

        # STEP2: full dialogue continuing from opening
        round_count = DURATION_MAP.get(duration, 10)
        opening_text = _build_continuation_prompt(opening_script)
        step2_prompt = f"""文章核心观点：
{key_points_raw}

要求：生成约{round_count}轮对话。严格按照对话结构：开场→逐条讨论观点→结尾。

已有开场对话（请从开场之后继续生成，不要重复开场）：
{opening_text}

请直接从第一轮讨论开始，自然地延续上面的开场。"""
        dialogue_raw = _call_ai(STEP2_SYSTEM, step2_prompt, model=model)
        llm_time = int((time.time() - t1) * 1000)
        _session_set(session_id, "llm_time_ms", llm_time)
        _session_set(session_id, "progress", 70)

        full_dialogue = parse_dialogue(dialogue_raw)
        if not full_dialogue:
            raise ValueError("Failed to parse full dialogue")
        logger.info(f"[bg] Full dialogue: {len(full_dialogue)} turns ({llm_time}ms)")

        complete_dialogue = opening_script + full_dialogue
        _session_set(session_id, "full_script", complete_dialogue)

        # Store article title and content for recommendations
        _session_set(session_id, "article_title", title)
        _session_set(session_id, "article_content", clean_text)
        _session_set(session_id, "progress", 75)

        # Self-evaluation
        eval_scores = evaluate_dialogue(clean_text, complete_dialogue)
        _session_set(session_id, "eval_scores", eval_scores)
        _session_set(session_id, "progress", 80)

        # TTS full
        t2 = time.time()
        audio_path = tts_script(complete_dialogue)
        # Audio post-processing
        audio_path = _post_process_audio(audio_path, high_quality=high_quality, bg_music=bg_music)
        tts_ms = int((time.time() - t2) * 1000)
        _session_set(session_id, "tts_time_ms", tts_ms)
        _session_set(session_id, "full_audio_path", audio_path)
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
    session_id = str(uuid.uuid4())
    t0 = time.time()

    if not url and not text:
        return jsonify({"error": "请提供 url 或 text"}), 400
    if not ZHI_API_KEY:
        return jsonify({"error": "服务端未配置 API 密钥"}), 500

    try:
        session_id, opening_script = _start_generation(url, text, duration, request_id=request_id, model=model, high_quality=high_quality, bg_music=bg_music)

        # TTS opening (~2s)
        opening_audio_path = _tts_script_segment(opening_script, f"opening_{session_id[:8]}")
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

@app.route("/api/generate_script", methods=["POST"])
def api_generate_script():
    data = request.get_json(silent=True) or {}
    clean_text = data.get("clean_text", "").strip()
    duration = data.get("duration", "standard")
    request_id = data.get("request_id", str(uuid.uuid4()))

    if not clean_text:
        return jsonify({"error": "clean_text 不能为空"}), 400
    if not ZHI_API_KEY:
        return jsonify({"error": "服务端未配置 API 密钥"}), 500

    try:
        t0 = time.time()
        dialogue, eval_scores, llm_time = generate_structured_dialogue(clean_text, duration)
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

    t0 = time.time()
    try:
        audio_path = tts_script(script)
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
     "summary":"小羊和小姜从各自的角度探讨了 AI 对传统教育体系的冲击。小姜用自己孩子学校的例子说明课堂已经在变化，小羊则从更宏观的视角分析了教育理念需要如何转变。",
     "chapters":[{"t":"01 · 教育的困境","d":"AI 时代的到来让传统教育模式面临前所未有的挑战"},{"t":"02 · 重新定义学习","d":"从知识灌输到能力培养，学习方式的根本转变"},{"t":"03 · 实践建议","d":"如何在 AI 时代重新规划学习路径"}]},
    {"id":"exp_2","title":"2026 年新能源汽车市场趋势：价格战后的新格局","desc":"分析新能源汽车市场的竞争格局变化","tag":"精选","platform":"知乎","icon":"📝","gradient":"linear-gradient(135deg,#FF9F5E15,#FF6B6B15)",
     'summary':'小姜开篇就抛出了「价格战打完了，然后呢」的疑问。小羊用数据分析了各品牌的生存状况，两人一致认为技术差异化和海外市场是下一阶段的关键。',
     "chapters":[{"t":"01 · 市场回顾","d":"2025 年价格战后的市场格局重塑"},{"t":"02 · 品牌分析","d":"各主要品牌的战略定位和差异化"},{"t":"03 · 未来预测","d":"2026-2027 年的关键趋势和变量"}]},
    {"id":"exp_3","title":"为什么日本半导体产业在过去三十年衰落又崛起？","desc":"日本半导体产业从崛起到衰落再到复兴","tag":"精选","platform":"网页","icon":"🌐","gradient":"linear-gradient(135deg,#5E9EFF15,#34C75915)",
     "summary":"小羊从历史角度梳理了日本半导体产业的完整发展脉络。小姜则从当下供应链的角度分析了日本在材料领域的不可替代性。",
     "chapters":[{"t":"01 · 辉煌时期","d":"日本半导体在上世纪 80 年代的全球主导地位"},{"t":"02 · 衰落原因","d":"日美贸易摩擦和产业策略失误"},{"t":"03 · 复兴之路","d":"当前日本在半导体材料领域的重新崛起"}]},
    {"id":"exp_4","title":"特斯拉 FSD 入华：自动驾驶的新篇章","desc":"FSD 正式进入中国，对本土企业产生的影响","tag":"热门","platform":"B站","icon":"▶️","gradient":"linear-gradient(135deg,#34C75915,#5E9EFF15)",
     "summary":"小姜试驾了搭载 FSD 的车型后兴奋地分享了体验。小羊则冷静分析了特斯拉的技术路线和本土化挑战。",
     "chapters":[{"t":"01 · 入华背景","d":"FSD 获批进入中国市场的来龙去脉"},{"t":"02 · 技术对比","d":"特斯拉 vs 华为小鹏的自动驾驶路线差异"},{"t":"03 · 行业影响","d":"FSD 入华对本土企业的竞争压力"}]},
    {"id":"exp_5","title":"SpaceX 星舰第五飞：人类登陆火星的里程碑","desc":"筷子回收技术取得历史性突破","tag":"热门","platform":"B站","icon":"▶️","gradient":"linear-gradient(135deg,#764BA215,#FF6B6B15)",
     "summary":"小姜一上来就说“太震撼了”，描述了亲眼看到筷子捕获助推器的画面。小羊用通俗的比喻解释了这项技术突破的意义。",
     "chapters":[{"t":"01 · 任务回顾","d":"星舰第五次轨道测试的关键节点"},{"t":"02 · 筷子技术","d":"发射塔捕获助推器的工程技术突破"},{"t":"03 · 火星展望","d":"完全可重复使用火箭对太空探索的意义"}]},
    {"id":"exp_6","title":"DeepSeek 崛起：中国 AI 大模型的新格局","desc":"开源策略和高效训练方法引发行业关注","tag":"精选","platform":"公众号","icon":"📄","gradient":"linear-gradient(135deg,#FF6B6B15,#764BA215)",
     "summary":"小姜用“性价比之王”来形容 DeepSeek。小羊分析了 DeepSeek 的技术路线和开源策略对行业的影响。",
     "chapters":[{"t":"01 · 技术突破","d":"DeepSeek 高效训练方法的技术创新"},{"t":"02 · 开源策略","d":"开源对 AI 行业竞争格局的影响"},{"t":"03 · 未来展望","d":"算法创新能否持续弥补算力差距"}]},
    {"id":"exp_7","title":"小米 SU7 上市三个月：真实用户体验","desc":"小米首款汽车 SU7 首批用户真实反馈","tag":"精选","platform":"小红书","icon":"📱","gradient":"linear-gradient(135deg,#FF6B6B15,#FFD70015)",
     "summary":"小姜分享了朋友提车后的真实体验。小羊从产品定义和造车基本功两个维度进行了分析。",
     "chapters":[{"t":"01 · 智能座舱","d":"人车家全生态互联的实际体验"},{"t":"02 · 续航表现","d":"真实续航达成率和充电便利性"},{"t":"03 · 综合评价","d":"小米第一款车的得与失"}]},
    {"id":"exp_8","title":"小红书电商崛起：从种草到拔草","desc":"小红书从内容社区到交易平台的转型","tag":"热门","platform":"小红书","icon":"📱","gradient":"linear-gradient(135deg,#FF9F5E15,#FF6B6B15)",
     "summary":"小姜说现在买东西先看小红书。小羊分析了这种消费决策路径变化背后的商业逻辑。",
     "chapters":[{"t":"01 · 平台转型","d":"从内容社区到交易平台的演变"},{"t":"02 · 商业模式","d":"买手直播和店铺直播双引擎"},{"t":"03 · 挑战与未来","d":"商业化 vs 社区氛围的平衡"}]},
    {"id":"exp_9","title":"《黑神话：悟空》DLC 前瞻","desc":"游戏科学确认 DLC 正在开发中","tag":"热门","platform":"B站","icon":"▶️","gradient":"linear-gradient(135deg,#764BA215,#FF6B6B15)",
     "summary":"小姜作为游戏迷兴奋地聊起了 DLC 的传闻。小羊则分析了这款游戏对中国游戏产业的意义。",
     "chapters":[{"t":"01 · 全球成绩","d":"《黑神话》全球销量突破 2000 万份"},{"t":"02 · DLC 内容","d":"火焰山、狮驼岭等新场景展望"},{"t":"03 · 产业影响","d":"中国 3A 游戏的未来之路"}]},
    {"id":"exp_10","title":"比亚迪秦 L DM-i 实测：油耗 2 升时代","desc":"第五代 DM 混动技术首款车型实测","tag":"精选","platform":"知乎","icon":"📝","gradient":"linear-gradient(135deg,#34C75915,#5E9EFF15)",
     "summary":"小姜算了一笔账：这车一年能省多少油钱。小羊从技术角度解析了 46% 热效率发动机的含金量。",
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
            ("开场与导入", "小羊和小姜引入话题"),
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
    """Skip RAG init at startup to avoid import hangs. RAG is lazy-initialized on first use."""
    global _RAG_INIT_DONE
    _RAG_INIT_DONE = True

_init_rag()
_load_persisted_sessions()

if __name__ == "__main__":
    cleanup_thread = threading.Thread(target=_session_cleanup_loop, daemon=True)
    cleanup_thread.start()
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") == "development"
    app.run(debug=debug, host="0.0.0.0", port=port)
