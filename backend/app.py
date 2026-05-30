import os, re, json, uuid, asyncio, tempfile, shutil, time, logging, threading, subprocess, math
from pathlib import Path
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
from readability import Document
from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import jwt as pyjwt
import anthropic
from database import (
    init_db, migrate_from_json,
    session_create, session_get, session_set, session_list, session_delete,
    settings_load, settings_save, save_audio_file, get_audio_path,
    user_create, user_get_by_phone, user_get_by_id, session_claim_all,
)
load_dotenv()
app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("boke")

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR.parent / "frontend" / "dist"
LOGS_PATH = BASE_DIR / "logs.jsonl"
BGM_UPLOAD_DIR = BASE_DIR / "uploads" / "bgm"
BGM_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ── Metrics Storage ──
METRICS_INPUT_PATH = BASE_DIR / "metrics_input.jsonl"
METRICS_GENERATION_PATH = BASE_DIR / "metrics_generation.jsonl"
METRICS_PLAYBACK_PATH = BASE_DIR / "metrics_playback.jsonl"
METRICS_USER_ACTION_PATH = BASE_DIR / "metrics_user_action.jsonl"
EXPERIMENTS_PATH = BASE_DIR / "experiments.jsonl"
EXP_ASSIGNMENTS_PATH = BASE_DIR / "experiment_assignments.jsonl"

def _write_metrics(path: Path, entry: dict):
    """Append a metrics entry to a JSONL file."""
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        logger.warning(f"Failed to write metrics to {path.name}: {e}")

def _load_metrics(path: Path, days: int = 30) -> list[dict]:
    """Load metrics from JSONL, filtering to recent days and auto-cleanup."""
    if not path.exists():
        return []
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    entries = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    ts = entry.get("timestamp")
                    if ts:
                        # Parse ISO timestamp
                        try:
                            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            if t.timestamp() >= cutoff:
                                entries.append(entry)
                        except Exception:
                            entries.append(entry)
                    else:
                        entries.append(entry)
                except json.JSONDecodeError:
                    pass
    except Exception as e:
        logger.warning(f"Failed to load metrics from {path.name}: {e}")
    return entries

# ── Config ──
ZHI_API_KEY = os.environ.get("ZHI_API_KEY")
ZHI_BASE_URL = "https://api.zhizengzeng.com/anthropic"
JWT_SECRET = os.environ.get("JWT_SECRET") or ZHI_API_KEY or "boke-dev-secret"
ZHI_MODEL = "deepseek-v4-pro"
EVAL_MODEL = "gpt-4o-mini"
ZHI_API_BASE = "https://api.zhizengzeng.com/v1/chat/completions"

MODEL_MAP = {
    "deepseek-v4-pro":   {"id": "deepseek-v4-pro",   "label": "DeepSeek V4",         "provider": "DeepSeek",    "desc": "默认模型，深度推理，长文表现最佳"},
    "deepseek-v4-flash": {"id": "deepseek-v4-flash", "label": "DeepSeek V4 Flash",   "provider": "DeepSeek",    "desc": "轻量快速，适合短文本"},
    "gpt-4o":            {"id": "gpt-4o",            "label": "GPT-4o",               "provider": "OpenAI",      "desc": "创意丰富，对谈更生动"},
    "gpt-4o-mini":       {"id": "gpt-4o-mini",       "label": "GPT-4o Mini",          "provider": "OpenAI",      "desc": "轻量版，性价比高"},
    "claude-haiku-4-5":  {"id": "claude-haiku-4-5",  "label": "Claude Haiku 4.5",    "provider": "Anthropic",   "desc": "极速响应，适合简单任务"},
    "claude-sonnet-4-6": {"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6",   "provider": "Anthropic",   "desc": "质量/速度平衡，对话自然"},
    "claude-opus-4-7":   {"id": "claude-opus-4-7",   "label": "Claude Opus 4.7",     "provider": "Anthropic",   "desc": "最强推理，适合深度长文"},
    "qwen3-max":         {"id": "qwen3-max",         "label": "Qwen3 Max",           "provider": "阿里",         "desc": "中文顶级，性价比极高"},
    "qwen3-32b":         {"id": "qwen3-32b",         "label": "Qwen3 32B",           "provider": "阿里",         "desc": "轻量均衡，日常够用"},
    "gemini-2.5-pro":    {"id": "gemini-2.5-pro",    "label": "Gemini 2.5 Pro",      "provider": "Google",       "desc": "长上下文(1M)，适合超长文章"},
}

# 估算定价（美元/百万token，走代理可能有差异）
MODEL_PRICES = {
    "deepseek-v4-pro":   {"input": 0.27,  "output": 1.10},
    "deepseek-v4-flash": {"input": 0.14,  "output": 0.55},
    "gpt-4o":            {"input": 2.50,  "output": 10.00},
    "gpt-4o-mini":       {"input": 0.15,  "output": 0.60},
    "claude-haiku-4-5":  {"input": 0.80,  "output": 4.00},
    "claude-sonnet-4-6": {"input": 3.00,  "output": 15.00},
    "claude-opus-4-7":   {"input": 15.00, "output": 75.00},
    "qwen3-max":         {"input": 0.55,  "output": 1.10},
    "qwen3-32b":         {"input": 0.20,  "output": 0.40},
    "gemini-2.5-pro":    {"input": 1.25,  "output": 5.00},
}

# 用量日志（JSONL 格式）
USAGE_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "usage_log.jsonl")
os.makedirs(os.path.dirname(USAGE_LOG_PATH), exist_ok=True)

def _record_usage(model: str, prompt_tokens: int, completion_tokens: int, duration_ms: float):
    """Record API usage to JSONL log."""
    prices = MODEL_PRICES.get(model, {"input": 0, "output": 0})
    cost = (prompt_tokens / 1_000_000 * prices["input"] +
            completion_tokens / 1_000_000 * prices["output"])
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "cost_usd": round(cost, 6),
        "duration_ms": round(duration_ms),
    }
    with open(USAGE_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def _resolve_model(model_key: str) -> str:
    """Temporarily force deepseek-v4-flash for all requests regardless of user selection."""
    return "deepseek-v4-flash"

FETCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

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
        "speaker": "主持",  # "主持" | "嘉宾" | "双声"
        "voice_id": None,  # 覆盖默认男/嘉宾
        "transition_style": "warm",
        "transition_duration": 3.0,
        "transition_volume": 0.15,
    },
    "outro": {
        "enabled": True,
        "mode": "template",  # "template" | "ai_summary" | "none"
        "template": "以上就是本期节目的全部内容。感谢收听播刻，我们下期再见。",
        "speaker": "主持",
        "voice_id": None,
    },
    "body_bgm": {
        "enabled": False,
        "style": "minimal",
        "volume": 0.08,
        "custom_path": None,
    },
    "intro_presets": [
        {
            "id": "default",
            "name": "默认开场白",
            "template": "欢迎收听播刻。今天我们要聊的是——{topic}。",
            "speaker": "主持",
            "voice_id": None,
            "transition_style": "warm",
            "transition_duration": 3.0,
            "transition_volume": 0.15,
        }
    ],
    "outro_presets": [
        {
            "id": "default",
            "name": "默认片尾",
            "mode": "template",
            "template": "以上就是本期节目的全部内容。感谢收听播刻，我们下期再见。",
            "speaker": "主持",
            "voice_id": None,
        }
    ],
}

def _load_settings() -> dict:
    """Load settings from SQLite, with JSON file fallback for migration."""
    db_data = settings_load()
    if db_data:
        # db_data is already a merged dict from SQLite key-value store
        merged = dict(_DEFAULT_SETTINGS)
        _deep_update(merged, db_data)
        return merged
    # Fallback to JSON file
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = dict(_DEFAULT_SETTINGS)
            _deep_update(merged, data)
            return merged
        except Exception:
            pass
    return dict(_DEFAULT_SETTINGS)

def _save_settings(data: dict):
    """Save settings to SQLite."""
    settings_save(data)

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
    has_speaker = all(d.get("speaker") in ("主持", "嘉宾") for d in dialogue)
    all_nonempty = all(len(d.get("text", "").strip()) > 0 for d in dialogue)
    # format_valid: at least 3 exchanges with both speakers present
    speakers = set(d["speaker"] for d in dialogue)
    enough_exchanges = len(dialogue) >= 3
    both_speakers = speakers == {"主持", "嘉宾"}
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
        if speaker == "主持":
            if any(w in text for w in male_forbidden):
                male_violations += 1
        elif speaker == "嘉宾":
            if any(w in text for w in female_forbidden):
                female_violations += 1
    total = male_violations + female_violations
    if total > 0:
        logger.warning(f"Role consistency check: {total} violations (male={male_violations}, female={female_violations})")
    else:
        logger.info("Role consistency check: clean")
    return {"male_violations": male_violations, "female_violations": female_violations, "total": total}


def _compute_text_stats(dialogue: list[dict]) -> dict:
    """Compute first-tier text statistics for monitoring."""
    if not dialogue:
        return {}
    total_turns = len(dialogue)
    total_chars = sum(len(t.get("text", "")) for t in dialogue)
    question_count = sum(1 for t in dialogue if "?" in t.get("text", "") or "？" in t.get("text", ""))
    exclamation_count = sum(1 for t in dialogue if "!" in t.get("text", "") or "！" in t.get("text", ""))
    filler_words = ["嗯", "啊", "那个", "这个", "就是说", "说实话", "你看", "等一下", "讲真", "咱就是说"]
    filler_count = sum(t.get("text", "").count(w) for t in dialogue for w in filler_words)
    pause_count = sum(t.get("text", "").count("[停顿]") for t in dialogue)
    emotion_count = sum(1 for t in dialogue if t.get("emotion"))
    return {
        "avg_turn_length": round(total_chars / max(1, total_turns), 1),
        "question_ratio": round(question_count / max(1, total_turns), 4),
        "exclamation_ratio": round(exclamation_count / max(1, total_turns), 4),
        "filler_density": round(filler_count / max(1, total_chars), 4),
        "pause_density": round(pause_count / max(1, total_turns), 4),
        "emotion_tag_rate": round(emotion_count / max(1, total_turns), 4),
    }

# ── Structured Dialogue Generation ──

STEP2_SYSTEM = """你正在生成一段双人播客对话。

## 核心约束（必须遵守）
- **只基于原文生成**，不允许补充任何外部知识
- 如果原文没有提及某个细节，对话可以说"这一点原文没有明确说明"，不要强行编造
- 覆盖原文所有重要论点、关键数据、典型案例，不要遗漏
- 数据引用必须精确（原文说"30%"，对话不能说"不少"）
- 保持自然对话感，是两个人在聊这篇文章，不是两个人在念稿

## 角色分工

### 主持（框架梳理者）
- 职责：提炼核心观点、做结构性总结、建立逻辑连接
- 语言习惯："你看""换句话说""这里面有几个层面"
- 禁忌：不说反问句、"说实话""我有点好奇"

### 嘉宾（细节追问者）
- 职责：提出尖锐问题、追问细节、质疑逻辑漏洞
- 语言习惯："说实话""我有点好奇""那岂不是""等一下"
- 禁忌：不做长篇学术总结，不说"综上所述"

**角色锚点（不可违反）：**
1. 主持="总结+连接"，嘉宾="追问+质疑"，不可互换
2. 主持绝不说"说实话"；嘉宾绝不说"你看""换句话说"

## 追问框架（参考节奏，非强制）
- L1 事实层：这是什么？
- L2 原因层：为什么会这样？
- L3 影响层：这意味着什么？
- L4 行动层：那该怎么办？

## 对话结构
- 开场：嘉宾先开口（提问/观察引发兴趣），主持接话
- 结尾：主持收尾，包含总结词 + 正式结束语
- 每轮自然呼应上一轮的关键词
- 允许观点交锋，不要一味附和
- 首次出现专业术语时简单解释

## 情绪标签（每轮必须标注，必须轮换）
平静（默认，占 40-50%）| 兴奋（每 section 至少 1 次）| 疑问（每 section 至少 1 次）| 沉思（每 section 至少 1 次）
同一情绪禁止连续使用超过 2 轮

## 语言禁忌
- 禁止排比句、书面化长定语、新闻播报腔

## 输出格式
每行 "主持[情绪]：..." 或 "嘉宾[情绪]：..."
不要序号，不要额外说明文字"""

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
   主持和嘉宾的语气、风格是否有明显差异，是否符合各自的角色设定（主持框架梳理、嘉宾细节追问）。
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

def _call_ai(system: str, content: str, model: str | None = None, temperature: float = 0.7) -> str:
    """Call LLM via OpenAI-compatible endpoint with retry and robust error handling."""
    import requests as req
    import time as _time
    model_name = model or ZHI_MODEL
    last_error = None
    for attempt in range(3):
        payload = {
            "model": model_name,
            "max_tokens": 4096,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
        }
        t_start = _time.time()
        try:
            resp = req.post(
                ZHI_API_BASE,
                json=payload,
                headers={
                    "Authorization": f"Bearer {ZHI_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=120,
            )
        except req.exceptions.Timeout:
            last_error = f"请求超时（模型={model_name}，第{attempt+1}次）"
            logger.warning(f"{last_error}，即将重试...")
            _time.sleep(2 ** attempt)
            continue
        except req.exceptions.ConnectionError as e:
            last_error = f"网络连接失败（模型={model_name}）：{e}"
            logger.error(last_error)
            _time.sleep(2 ** attempt)
            continue

        duration_ms = (_time.time() - t_start) * 1000

        # 检查 HTTP 状态码
        if resp.status_code != 200:
            body_preview = resp.text[:300] if resp.text else "(空响应)"
            last_error = f"API 返回 HTTP {resp.status_code}（模型={model_name}）：{body_preview}"
            logger.warning(f"{last_error}，第{attempt+1}次")
            _time.sleep(2 ** attempt)
            continue

        # 尝试解析 JSON
        try:
            data = resp.json()
        except Exception as e:
            body_preview = resp.text[:300] if resp.text else "(空响应)"
            # 检测空响应——通常是 API 网关拦截请求（余额不足/密钥无效）
            if not resp.text or len(resp.text.strip()) == 0:
                last_error = (f"AI 服务返回空响应（HTTP 200），可能原因：API 密钥余额不足或已过期。"
                              f"请检查 ZHI_API_KEY 账户余额（模型={model_name}）")
            else:
                last_error = f"API 返回非 JSON 响应（模型={model_name}）：{e}。原文：{body_preview}"
            logger.error(last_error)
            _time.sleep(2 ** attempt)
            continue

        choices = data.get("choices", [])
        if choices and choices[0].get("message", {}).get("content"):
            # 记录用量
            usage = data.get("usage", {})
            if usage:
                try:
                    _record_usage(model_name,
                                  usage.get("prompt_tokens", 0),
                                  usage.get("completion_tokens", 0),
                                  duration_ms)
                except Exception:
                    pass  # 用量记录失败不影响主流程
            return choices[0]["message"]["content"]

        # 检查是否有 error 字段（OpenAI 格式的错误）
        error_info = data.get("error", {})
        if error_info:
            last_error = f"API 返回错误（模型={model_name}）：{error_info.get('message', error_info)}"
        else:
            last_error = f"AI 返回了空的 choices 数组（模型={model_name}）"
        logger.warning(f"{last_error}，第{attempt+1}次")
        _time.sleep(2 ** attempt)

    raise RuntimeError(f"AI 调用失败（已重试3次）：{last_error}")

def _call_eval(system: str, content: str) -> str:
    """Separate eval call using EVAL_MODEL via OpenAI-compatible endpoint."""
    import requests as req
    import time as _time
    last_error = None
    for attempt in range(2):
        payload = {
            "model": EVAL_MODEL,
            "max_tokens": 1024,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
        }
        try:
            resp = req.post(
                "https://api.zhizengzeng.com/v1/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {ZHI_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=60,
            )
        except Exception as e:
            last_error = str(e)
            _time.sleep(1)
            continue

        if resp.status_code != 200:
            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            _time.sleep(1)
            continue

        try:
            data = resp.json()
        except Exception as e:
            last_error = f"非JSON响应: {e}"
            continue

        choices = data.get("choices", [])
        if choices and choices[0].get("message", {}).get("content"):
            return choices[0]["message"]["content"]

        error_info = data.get("error", {})
        last_error = f"AI错误: {error_info.get('message', error_info)}"

    raise RuntimeError(f"Eval模型调用失败: {last_error}")


def parse_dialogue(text: str) -> list[dict]:
    lines = text.strip().split("\n")
    result = []
    pattern = re.compile(r"^(主持|嘉宾)(?:\[([^\]]+)\])?[：:]\s*(.+)")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = pattern.match(line)
        if m:
            text_ = re.sub(r'（出自原文第\d+段）', '', m.group(3).strip()).strip()
            if text_:
                item = {"speaker": m.group(1), "text": text_}
                if m.group(2):
                    item["emotion"] = m.group(2).strip()
                result.append(item)
    return result

# ── Objective Evaluation Metrics ──

def _distinct_n(texts: list[str], n: int = 2) -> float:
    """Compute Distinct-N: ratio of unique n-grams to total n-grams."""
    ngrams = set()
    total = 0
    for text in texts:
        chars = list(text)
        for i in range(len(chars) - n + 1):
            ngrams.add(tuple(chars[i:i + n]))
            total += 1
    return round(len(ngrams) / total, 4) if total > 0 else 0.0


def _info_density(texts: list[str]) -> float:
    """Compute Shannon entropy over character distribution."""
    from collections import Counter
    chars = []
    for text in texts:
        chars.extend(list(text))
    counter = Counter(chars)
    total = len(chars)
    if total == 0:
        return 0.0
    entropy = 0.0
    for count in counter.values():
        p = count / total
        entropy -= p * math.log2(p)
    return round(entropy, 4)


def _role_distinction(dialogue: list[dict]) -> float:
    """Compute role distinction using sentence embeddings (cosine distance)."""
    male_texts = [d["text"] for d in dialogue if d.get("speaker") == "主持"]
    female_texts = [d["text"] for d in dialogue if d.get("speaker") == "嘉宾"]
    if not male_texts or not female_texts:
        return 0.0

    male_emb = _get_embedding("\n".join(male_texts))
    female_emb = _get_embedding("\n".join(female_texts))
    if not male_emb or not female_emb:
        return 0.0

    sim = _cosine_similarity(male_emb, female_emb)
    return round(1.0 - sim, 4)


# ── Shared Embedding Utilities ──

def _get_embeddings_batch(texts: list[str], max_chars: int = 500) -> list[list[float]]:
    """Get embeddings for multiple texts in one API call via zhizengzeng proxy."""
    if not texts:
        return []
    try:
        truncated = [t[:max_chars] for t in texts]
        resp = requests.post(
            "https://api.zhizengzeng.com/v1/embeddings",
            json={"model": "text-embedding-3-small", "input": truncated},
            headers={"Authorization": f"Bearer {ZHI_API_KEY}", "Content-Type": "application/json"},
            timeout=60,
        )
        data = resp.json()
        return [d["embedding"] for d in data.get("data", [])]
    except Exception as e:
        logger.warning(f"Batch embedding API call failed: {e}")
        return []


def _get_embedding(text: str, max_chars: int = 500) -> list[float]:
    """Get embedding for a single text."""
    embs = _get_embeddings_batch([text], max_chars=max_chars)
    return embs[0] if embs else []


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors. Returns 0.0 if either is empty."""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _keyword_coverage(article: str, dialogue: list[dict]) -> float:
    """Compute keyword coverage: ratio of article keywords present in dialogue."""
    try:
        import jieba
    except ImportError:
        return 0.0
    dialogue_text = "".join(d["text"] for d in dialogue)
    article_words = set(w for w in jieba.cut(article) if len(w.strip()) >= 2)
    dialogue_words = set(w for w in jieba.cut(dialogue_text) if len(w.strip()) >= 2)
    if not article_words:
        return 0.0
    return round(len(article_words & dialogue_words) / len(article_words), 4)


def _keyword_coverage_semantic(article: str, dialogue: list[dict], topK: int = 50,
                                threshold: float = 0.6) -> dict:
    """Semantic keyword coverage: extract keywords via jieba TF-IDF, use embedding
    cosine similarity to detect semantically equivalent terms in dialogue.
    Returns dict with 'keyword_coverage_semantic' score and metadata."""
    import re as _re
    try:
        import jieba.analyse
    except ImportError:
        return {"keyword_coverage_semantic": 0.0, "keyword_coverage_method": "no_jieba"}
    try:
        keywords = jieba.analyse.extract_tags(article, topK=topK, withWeight=False)
    except Exception:
        return {"keyword_coverage_semantic": 0.0, "keyword_coverage_method": "tfidf_failed"}
    if not keywords:
        return {"keyword_coverage_semantic": 0.0, "keyword_coverage_method": "empty_keywords"}

    # Split dialogue into sentences
    dialogue_text = "".join(d["text"] for d in dialogue)
    sents = [s.strip() for s in _re.split(r'[。！？\n]+', dialogue_text) if len(s.strip()) >= 4]
    if not sents:
        return {"keyword_coverage_semantic": 0.0, "keyword_coverage_method": "no_sentences"}

    # Batch embedding calls (2 API calls total)
    kw_embs = _get_embeddings_batch(keywords, max_chars=100)
    sent_embs = _get_embeddings_batch(sents, max_chars=300)

    if not kw_embs or not sent_embs:
        return {"keyword_coverage_semantic": 0.0, "keyword_coverage_method": "embedding_failed"}

    # For each keyword, find max cosine similarity with any sentence
    covered = 0
    for kw_emb in kw_embs:
        max_sim = max(_cosine_similarity(kw_emb, s_emb) for s_emb in sent_embs)
        if max_sim >= threshold:
            covered += 1

    return {
        "keyword_coverage_semantic": round(covered / len(keywords), 4),
        "keyword_coverage_method": "semantic",
        "keyword_coverage_keywords": len(keywords),
        "keyword_coverage_sentences": len(sents),
        "keyword_coverage_threshold": threshold,
    }


# ── Second-tier Evaluation Metrics ──

def _numeric_hallucination(article: str, dialogue: list[dict]) -> float:
    """NER-style: extract numeric expressions (percentages, years, prices) from dialogue,
    verify each against article. Returns hallucination rate (0-1)."""
    num_pattern = re.compile(r'(\d+[\.\d]*\s*[%％倍万千百个年日月天小时分秒元美元欧元点版代号度]*)')
    article_nums = set(num_pattern.findall(article))
    dialogue_text = "".join(d["text"] for d in dialogue)
    dialogue_nums = set(num_pattern.findall(dialogue_text))
    if not dialogue_nums:
        return 0.0
    hallucinated = dialogue_nums - article_nums
    return round(len(hallucinated) / len(dialogue_nums), 4)


def _entity_hallucination(article: str, dialogue: list[dict]) -> float:
    """Extract named entities (people, places, orgs) from dialogue via jieba POS tagging,
    verify each against article. Returns hallucination rate (0-1)."""
    import jieba.posseg as pseg
    dialogue_text = "".join(d["text"] for d in dialogue)
    try:
        article_entities = set(w.word for w in pseg.cut(article)
                               if w.flag in ('nr', 'ns', 'nt', 'nz') and len(w.word) >= 2)
        dialogue_entities = set(w.word for w in pseg.cut(dialogue_text)
                                if w.flag in ('nr', 'ns', 'nt', 'nz') and len(w.word) >= 2)
    except Exception:
        return 0.0
    if not dialogue_entities:
        return 0.0
    hallucinated = dialogue_entities - article_entities
    return round(len(hallucinated) / len(dialogue_entities), 4)


def _keyword_omission(article: str, dialogue: list[dict]) -> float:
    """Extract top TF-IDF keywords from article (top 30), measure what fraction
    is missing from the dialogue. Returns omission rate (0-1)."""
    try:
        import jieba.analyse
    except ImportError:
        return 0.0
    dialogue_text = "".join(d["text"] for d in dialogue)
    keywords = jieba.analyse.extract_tags(article, topK=30, withWeight=False)
    if not keywords:
        return 0.0
    omitted = sum(1 for kw in keywords if kw not in dialogue_text)
    return round(omitted / len(keywords), 4)


def _turn_coherence(dialogue: list[dict]) -> dict:
    """Measure turn-to-turn lexical coherence using character Jaccard similarity.
    Coherent conversation about the same topic shares ~0.3-0.6 Jaccard.
    Too low (<0.15) = topic jumps; too high (>0.7) = repetition."""
    if len(dialogue) < 3:
        return {"coherence_score": 0.0, "coherence_std": 0.0}
    sims = []
    for i in range(len(dialogue) - 1):
        chars_i = set(dialogue[i].get("text", ""))
        chars_j = set(dialogue[i + 1].get("text", ""))
        if not chars_i or not chars_j:
            sims.append(0.0)
        else:
            sim = len(chars_i & chars_j) / len(chars_i | chars_j)
            sims.append(sim)
    avg = sum(sims) / len(sims)
    var = sum((s - avg) ** 2 for s in sims) / len(sims)
    return {
        "coherence_score": round(avg, 4),
        "coherence_std": round(math.sqrt(var), 4),
    }


def _turn_coherence_embedding(dialogue: list[dict]) -> dict:
    """Measure turn-to-turn coherence using embedding cosine similarity.
    More semantically meaningful than character-level Jaccard.
    Returns dict with 'coherence_score' and 'coherence_std'."""
    if len(dialogue) < 3:
        return {"coherence_score": 0.0, "coherence_std": 0.0}
    turns = [d.get("text", "") for d in dialogue]
    if not all(turns):
        return {"coherence_score": 0.0, "coherence_std": 0.0}

    embs = _get_embeddings_batch(turns, max_chars=500)
    if not embs or len(embs) < 2:
        return {"coherence_score": 0.0, "coherence_std": 0.0}

    sims = []
    for i in range(len(embs) - 1):
        sim = _cosine_similarity(embs[i], embs[i + 1])
        sims.append(sim)

    avg = sum(sims) / len(sims)
    var = sum((s - avg) ** 2 for s in sims) / len(sims)
    return {
        "coherence_score": round(avg, 4),
        "coherence_std": round(math.sqrt(var), 4),
    }


def _opening_closing_quality(dialogue: list[dict]) -> dict:
    """Evaluate opening and closing dialogue quality via rule-based checks.
    Opening: guest speaks first, host responds, has engagement hook.
    Closing: host summarizes, has formal ending."""
    result = {}
    n = len(dialogue)
    if n >= 2:
        result["opening_guest_first"] = dialogue[0].get("speaker") == "嘉宾"
        result["opening_host_second"] = dialogue[1].get("speaker") == "主持"
        result["opening_has_hook"] = any(c in dialogue[0].get("text", "") for c in "?!？！")
    else:
        result["opening_guest_first"] = False
        result["opening_host_second"] = False
        result["opening_has_hook"] = False
    if n >= 1:
        last = dialogue[-1]
        result["closing_host_last"] = last.get("speaker") == "主持"
        text = last.get("text", "")
        result["closing_has_summary"] = any(kw in text for kw in
                                            ["总结", "总之", "以上就是", "核心", "关键",
                                             "回顾", "所以说", "总而言之", "归结", "一言以蔽之"])
        result["closing_has_formal_ending"] = any(kw in text for kw in
                                                  ["感谢收听", "再见", "下期", "下次",
                                                   "以上就是", "我们下期"])
    else:
        result["closing_host_last"] = False
        result["closing_has_summary"] = False
        result["closing_has_formal_ending"] = False
    bool_scores = [v for k, v in result.items() if isinstance(v, bool)]
    result["opening_closing_score"] = round(sum(bool_scores) / len(bool_scores), 4) if bool_scores else 0.0
    return result


def _chunk_transition_score(chunks_dialogue: list[list[dict]]) -> float:
    """Evaluate transition quality between chunks using embedding cosine similarity.
    Measures how smoothly consecutive chunks connect semantically.
    Returns average cosine similarity (0-1)."""
    if len(chunks_dialogue) < 2:
        return 1.0
    texts = []
    for i in range(len(chunks_dialogue) - 1):
        if not chunks_dialogue[i] or not chunks_dialogue[i + 1]:
            continue
        last_turn = chunks_dialogue[i][-1].get("text", "")
        first_turn = chunks_dialogue[i + 1][0].get("text", "")
        if last_turn and first_turn:
            texts.append((last_turn, first_turn))
    if not texts:
        return 0.0

    # Batch all embedding calls
    all_texts = [t[0] for t in texts] + [t[1] for t in texts]
    embs = _get_embeddings_batch(all_texts, max_chars=500)
    if not embs or len(embs) != len(all_texts):
        return 0.0

    n = len(texts)
    scores = []
    for i in range(n):
        sim = _cosine_similarity(embs[i], embs[i + n])
        scores.append(sim)

    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 4)


def _sanitize_json(text: str) -> str:
    """Remove control characters that break json.loads while preserving \n, \r, \t."""
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    cleaned = re.sub(r'\n+', '\n', cleaned)
    return cleaned.strip()


# ── NLI Faithfulness ──

def _extract_claims(dialogue: list[dict]) -> list[str]:
    """Stage 1: LLM extracts atomic factual claims from dialogue (zero judgment)."""
    dialogue_texts = "\n".join(f"{d['speaker']}：{d['text']}" for d in dialogue)
    system = "你是一个事实性陈述提取专家。只提取包含可验证事实的原子陈述（claims）。不要提取寒暄、过渡语、修辞问句。每行一个陈述，不要编号。如果对话中没有事实性陈述，输出空行。"
    prompt = f"从以下播客对话中提取所有包含可验证事实的原子陈述：\n\n{dialogue_texts[:3000]}"
    try:
        raw = _call_eval(system, prompt)
        claims = [c.strip() for c in raw.strip().split("\n") if c.strip() and len(c.strip()) > 5]
        seen = set()
        unique = []
        for c in claims:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        return unique
    except Exception as e:
        logger.warning(f"Claim extraction failed: {e}")
        return []


def _nli_verify_claims(claims: list[str], article: str) -> dict:
    """Stage 2: Verify each claim against article.

    Primary: LLM-as-judge per claim (works for any language).
    Fallback: embedding cosine similarity (when LLM unavailable).
    """
    if not claims:
        return {"nli_supported": 0, "nli_total": 0, "nli_score": 0.5, "nli_results": [], "nli_method": "empty"}

    # Primary: LLM verifies each claim individually
    try:
        results = []
        for claim in claims:
            v_system = "你是一个事实一致性验证专家。判断陈述是否被原文支持。只回答「支持」「不支持」「无信息」三个词之一。"
            v_prompt = f"原文：\n{article[:2000]}\n\n陈述：{claim}\n该陈述是否被原文支持？"
            try:
                answer = _call_eval(v_system, v_prompt).strip()
                supported = "支持" in answer and "不" not in answer[:3]
                results.append(supported)
            except Exception:
                results.append(False)
        supported = sum(results)
        return {
            "nli_supported": supported,
            "nli_total": len(claims),
            "nli_score": round(supported / len(claims), 4),
            "nli_results": results,
            "nli_method": "llm_per_claim",
        }
    except Exception as e:
        logger.warning(f"LLM per-claim verification failed ({e}), trying embedding fallback...")

    # Fallback: embedding similarity
    try:
        claim_embs = _get_embeddings_batch(claims, max_chars=200)
        art_emb = _get_embedding(article[:1500])
        if claim_embs and art_emb:
            results = [_cosine_similarity(c_emb, art_emb) >= 0.75 for c_emb in claim_embs]
            supported = sum(results)
            return {
                "nli_supported": supported,
                "nli_total": len(claims),
                "nli_score": round(supported / len(claims), 4),
                "nli_results": results,
                "nli_method": "embedding_fallback",
            }
    except Exception:
        pass

    return {"nli_supported": 0, "nli_total": len(claims), "nli_score": 0.5, "nli_results": [], "nli_method": "all_failed"}


def _evaluate_faithfulness_nli(article: str, dialogue: list[dict]) -> dict:
    """Two-stage NLI faithfulness: extract claims, then verify each via NLI.
    For long texts (>3000 chars) uses segmented evaluation."""
    if len(article) <= 3000:
        claims = _extract_claims(dialogue)
        nli_result = _nli_verify_claims(claims, article)
        return {
            "faithfulness": nli_result.get("nli_score", 0.5),
            "faithfulness_method": nli_result.get("nli_method", "unknown"),
            "nli_claims": nli_result.get("nli_total", 0),
            "nli_supported": nli_result.get("nli_supported", 0),
        }

    n_segments = 3
    art_seg_size = len(article) // n_segments
    dlg_seg_size = max(1, len(dialogue) // n_segments)
    all_results = []

    for i in range(n_segments):
        art_start = i * art_seg_size
        art_end = art_start + art_seg_size + 500 if i < n_segments - 1 else len(article)
        art_frag = article[art_start:art_end]

        dlg_start = i * dlg_seg_size
        dlg_end = min(dlg_start + dlg_seg_size + 3, len(dialogue))
        dlg_frag = dialogue[dlg_start:dlg_end]

        claims = _extract_claims(dlg_frag)
        result = _nli_verify_claims(claims, art_frag)
        all_results.append(result)

    total_supported = sum(r["nli_supported"] for r in all_results)
    total_claims = sum(r["nli_total"] for r in all_results)
    methods = [r.get("nli_method", "unknown") for r in all_results]

    return {
        "faithfulness": round(total_supported / max(1, total_claims), 4),
        "faithfulness_method": methods[0] if methods else "unknown",
        "nli_claims": total_claims,
        "nli_supported": total_supported,
    }


def _evaluate_faithfulness_segment(article_fragment: str, dialogue_fragment: list[dict]) -> float:
    """Evaluate faithfulness for a single segment."""
    dialogue_text = "\n".join(f"{d['speaker']}：{d['text']}" for d in dialogue_fragment)
    system = "你是一个事实一致性评估专家。请从对话中提取事实性陈述，并判断每个陈述是否在原文中有依据。"
    prompt = f"""原文：
{article_fragment[:2500]}

对话：
{dialogue_text[:2500]}

请从对话中提取所有事实性陈述（claims），然后逐一判断每个陈述是否在原文中有依据。
输出格式（严格的JSON）：
{{"claims": ["claim1", "claim2"], "supported": [true, false], "faithfulness_score": 0.0-1.0}}
faithfulness_score = supported为true的数量 / claims总数"""

    try:
        raw = _call_eval(system, prompt)
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            json_text = _sanitize_json(match.group())
            data = json.loads(json_text)
            return round(data.get("faithfulness_score", 0.5), 4)
    except Exception as e:
        logger.warning(f"Faithfulness segment evaluation failed: {e}")
    return 0.5


def _evaluate_faithfulness(article: str, dialogue: list[dict]) -> float:
    """RAGAs-style faithfulness: ask LLM to judge if dialogue claims are supported by article.
    For long texts (>3000 chars), uses segmented evaluation to avoid only checking the first 2000 chars."""
    if len(article) <= 3000:
        return _evaluate_faithfulness_segment(article, dialogue)

    # Long text: split into 3 segments and evaluate separately
    n_segments = 3
    article_seg_size = len(article) // n_segments
    dialogue_seg_size = max(1, len(dialogue) // n_segments)
    scores = []

    for i in range(n_segments):
        art_start = i * article_seg_size
        art_end = art_start + article_seg_size + 500 if i < n_segments - 1 else len(article)
        art_fragment = article[art_start:art_end]

        dlg_start = i * dialogue_seg_size
        dlg_end = min(dlg_start + dialogue_seg_size + 3, len(dialogue))
        dlg_fragment = dialogue[dlg_start:dlg_end]

        score = _evaluate_faithfulness_segment(art_fragment, dlg_fragment)
        scores.append(score)

    return round(sum(scores) / len(scores), 4) if scores else 0.5


def _evaluate_q2(article: str, dialogue: list[dict]) -> float:
    """Q2 method (QG+QA+NLI) for factual consistency. Cost: ~15 LLM calls per dialogue."""
    dialogue_text = "\n".join(f"{d['speaker']}：{d['text']}" for d in dialogue)
    # Step 1: Generate questions from dialogue
    qg_system = "你是一个问题生成专家。请从对话中提取关键事实性问题。"
    qg_prompt = f"从以下对话中提取最多5个关键事实性问题（只输出问题，每行一个）：\n\n{dialogue_text[:1500]}"
    try:
        raw_q = _call_eval(qg_system, qg_prompt)
        questions = [q.strip() for q in raw_q.strip().split("\n") if q.strip() and len(q.strip()) > 5][:5]
    except Exception as e:
        logger.warning(f"Q2 question generation failed: {e}")
        return 0.5

    if not questions:
        return 0.5

    # Step 2: Answer each question from article
    qa_system = "你是一个问答专家。请根据原文简要回答问题。"
    nli_system = "你是一个自然语言推理专家。请判断'对话中的说法'是否与'原文回答'一致。只回答'是'或'否'。"
    correct = 0
    total = 0
    for q in questions:
        try:
            qa_prompt = f"原文：\n{article[:1500]}\n\n问题：{q}\n\n答案："
            answer = _call_eval(qa_system, qa_prompt).strip()

            nli_prompt = f"对话中的说法：{q}\n原文中的答案：{answer}\n\n两者是否一致？只回答'是'或'否'。"
            result = _call_eval(nli_system, nli_prompt).strip()
            total += 1
            if "是" in result:
                correct += 1
        except Exception as e:
            logger.warning(f"Q2 evaluation step failed for question '{q}': {e}")
            total += 1

    return round(correct / total, 4) if total > 0 else 0.5


def evaluate_dialogue(article: str, dialogue: list[dict], use_q2: bool = False) -> dict:
    """Comprehensive evaluation with first-tier + second-tier metrics."""
    texts = [d["text"] for d in dialogue]
    dialogue_text = "\n".join(f"{d['speaker']}：{d['text']}" for d in dialogue)

    # First-tier objective metrics (fast, zero LLM cost)
    distinct_1 = _distinct_n(texts, 1)
    distinct_2 = _distinct_n(texts, 2)
    info_dens = _info_density(texts)
    role_dist = _role_distinction(dialogue)
    coverage = _keyword_coverage(article, dialogue)

    # Second-tier metrics (fast, rule-based / local NLP)
    numeric_hall = _numeric_hallucination(article, dialogue)
    entity_hall = _entity_hallucination(article, dialogue)
    omission = _keyword_omission(article, dialogue)
    coherence = _turn_coherence(dialogue)
    oc_quality = _opening_closing_quality(dialogue)

    # LLM-based faithfulness (1 call)
    faithfulness = _evaluate_faithfulness(article, dialogue)

    # New NLI-based faithfulness (two-stage, more objective)
    faithfulness_nli = _evaluate_faithfulness_nli(article, dialogue)

    # New embedding-based coherence
    coherence_emb = _turn_coherence_embedding(dialogue)

    # New semantic keyword coverage
    coverage_semantic = _keyword_coverage_semantic(article, dialogue)

    # Deep Q2 evaluation (~15 calls, expensive, optional)
    q2_score = _evaluate_q2(article, dialogue) if use_q2 else None

    # Legacy LLM evaluation (backward compatibility)
    legacy_scores = {"content_accuracy_score": 3, "colloquial_score": 3,
                     "role_difference_score": 3, "scene_fit_score": 3}
    try:
        prompt = f"【原文】\n{article[:1000]}\n\n【对话】\n{dialogue_text}\n\n请评分。"
        raw = _call_eval(EVAL_SYSTEM, prompt)
        scores = json.loads(raw.strip())
        legacy_scores = {
            "content_accuracy_score": max(1, min(5, scores.get("content_accuracy_score", 3))),
            "colloquial_score": max(1, min(5, scores.get("colloquial_score", 3))),
            "role_difference_score": max(1, min(5, scores.get("role_difference_score", 3))),
            "scene_fit_score": max(1, min(5, scores.get("scene_fit_score", 3))),
        }
    except Exception as e:
        logger.warning(f"Legacy evaluation failed: {e}")

    result = {
        # Legacy scores (backward compatible)
        **legacy_scores,
        # First-tier objective metrics
        "distinct_1": distinct_1,
        "distinct_2": distinct_2,
        "info_density": info_dens,
        "role_distinction": role_dist,
        "keyword_coverage": coverage,
        "faithfulness": faithfulness,
        # Second-tier evaluation metrics
        "numeric_hallucination_rate": numeric_hall,
        "entity_hallucination_rate": entity_hall,
        "keyword_omission_rate": omission,
        "coherence_score": coherence.get("coherence_score", 0.0),
        "coherence_std": coherence.get("coherence_std", 0.0),
        "opening_closing_score": oc_quality.get("opening_closing_score", 0.0),
        "opening_guest_first": oc_quality.get("opening_guest_first", False),
        "closing_host_last": oc_quality.get("closing_host_last", False),
        "opening_has_hook": oc_quality.get("opening_has_hook", False),
        "closing_has_summary": oc_quality.get("closing_has_summary", False),
        "closing_has_formal_ending": oc_quality.get("closing_has_formal_ending", False),
        # New embedding-based metrics
        "coherence_embedding_score": coherence_emb.get("coherence_score", 0.0),
        "coherence_embedding_std": coherence_emb.get("coherence_std", 0.0),
        "keyword_coverage_semantic": coverage_semantic.get("keyword_coverage_semantic", 0.0),
        # New NLI-based faithfulness
        "faithfulness_nli": faithfulness_nli.get("faithfulness", 0.0),
        "faithfulness_method": faithfulness_nli.get("faithfulness_method", "unknown"),
        "nli_claims_total": faithfulness_nli.get("nli_claims", 0),
        "nli_claims_supported": faithfulness_nli.get("nli_supported", 0),
    }
    if q2_score is not None:
        result["q2_score"] = q2_score

    logger.info(f"Evaluation metrics: distinct_1={distinct_1}, distinct_2={distinct_2}, "
                f"info_density={info_dens}, role_distinction={role_dist}, "
                f"coverage={coverage}, faithfulness={faithfulness}"
                f" | T2: numeric_hall={numeric_hall}, entity_hall={entity_hall}, "
                f"omission={omission}, coherence={coherence.get('coherence_score')}, "
                f"oc_score={oc_quality.get('opening_closing_score')}"
                + (f", q2={q2_score}" if q2_score is not None else ""))
    return result

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

【主持 — 框架梳理者】
- 语言指纹："你看""换句话说""这里面有几个层面"；先给结论再展开；禁忌反问句和口语词
- 行为不变量：讨论完一个论点必须一句话总结；切换话题前必须有过渡句
- **绝对禁忌**：绝不说"说实话""我有点好奇""那岂不是""等一下"

【嘉宾 — 细节追问者】
- 语言指纹："说实话""我有点好奇""那岂不是""等一下"；从个人体验出发提问；禁忌长篇总结
- 行为不变量：每个重要论点至少追问两层；核心论点追问到影响层或行动层
- **绝对禁忌**：绝不说"你看""换句话说""这里面有几个层面"

角色锚点（这是防止串台的生命线，必须遵守）：
1. 主持的功能是"总结+连接"，嘉宾的功能是"质疑+追问"，两者不可互换
2. 如果主持开始质疑或嘉宾开始总结，说明已经串台，必须立即修正

对话要求：
1. 完整覆盖本段原文的所有重要论点、关键数据和典型案例
2. 句子自然流畅，允许使用专业术语
3. 嘉宾提出问题和质疑，主持分析总结并建立逻辑连接——功能不可互换
4. 情绪标注（必须执行）：为每轮对话标注情绪，格式 "主持[情绪]：..." 或 "嘉宾[情绪]：..."
   核心标签：正常（默认）、兴奋、磁性、放慢、悲伤。也可使用 Fish Audio 自然语言描述作为自由形式标签。
5. 口语真实感强制规则（必须执行——去AI味）：
   - **字数弹性**：根据原文信息量自然决定每轮字数。关键论点可充分展开，嘉宾每轮 15-40 字，主持每轮 30-80 字。不要因为担心篇幅而压缩内容。
   - **充分展开**：本段是长文的一部分，信息量大。遇到关键数据、典型案例、逻辑链条时，请逐层拆解，不要一句话带过。
   - **填充词密度**：每 3-4 轮中至少一轮加入填充词："嗯……""那个……""等一下等一下"
   - **自我修正**：每 8-10 轮必须出现一次自我修正
   - **打断设计**：每 6-8 轮设计一次打断，用"等一下""不不不"插入，被打断方用省略号结尾
   - **笑声标记**：轻松话题处加入 [轻笑]、[笑]、[嘿嘿]
   - 句中停顿用 [停顿] 标记，轻声用 [轻声]...[/轻声] 标记
   - **绝对禁止**：书面化长定语、排比句、新闻播报腔
   - 不要每句都用标记，自然第一
6. 输出格式：每行 "主持[情绪]：..." 或 "嘉宾[情绪]：..."
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


def _duration_hint(duration: str | None) -> str:
    """Return a Chinese duration constraint hint for the LLM prompt."""
    if duration == "short":
        return "对话总时长控制在 5-15 分钟左右，不要过于冗长，保持精悍紧凑。"
    if duration == "long":
        return "对话总时长控制在 15-30 分钟左右，允许充分展开论述，保持深度。"
    if duration == "extra_long":
        return "对话总时长控制在 30-60 分钟左右，每个论点都需要充分展开，加入具体案例、数据解读和自然的过渡衔接，保持深度但不冗长。"
    if duration == "ultra_long":
        return "对话总时长控制在 60 分钟以上，要求对每个论点进行极其深入的探讨，加入丰富的案例、数据解读、背景延伸和互动讨论，充分挖掘原文的每一个细节，允许适度的发散和联想。"
    return ""


_FORMAT_EXAMPLE = """\n【格式示例——必须严格模仿，这是防止解析失败的底线】
嘉宾[兴奋]：说实话，看到这个数据我有点惊讶——
主持[正常]：你看，这背后其实有两个层面。
嘉宾[疑问]：等一下，那普通人能参与吗？
主持[放慢]：这个问题问得好，我们先来看第一层……

绝对禁止：写成叙述文、段落、散文或带序号；每行必须以 "主持[" 或 "嘉宾[" 开头。"""


def _resolve_prompt_mode(length: int, prompt_mode: str) -> str:
    """Passthrough: only one prompt mode (STEP2_SYSTEM) is used."""
    return prompt_mode


def _select_system_prompt(prompt_mode: str, is_first: bool = True) -> str:
    """Select system prompt based on mode and whether it's the first chunk."""
    # Only one prompt mode: STEP2_SYSTEM for first, STEP2_CONTINUATION for continuation
    return STEP2_SYSTEM if is_first else STEP2_CONTINUATION


def _generate_single_dialogue(text_for_llm: str, system: str = STEP2_SYSTEM,
                              context: str = "", is_continuation: bool = False,
                              model: str | None = None, duration: str | None = None,
                              format_retry: bool = False,
                              prompt_mode: str = "original",
                              temperature: float = 0.7) -> str:
    """Generate raw dialogue text from a text chunk."""
    # Only one prompt mode: use the passed system (default STEP2_SYSTEM)

    duration_line = _duration_hint(duration)
    format_reminder = ""
    if format_retry:
        format_reminder = "\n\n【重试——上一次的输出格式不正确，未能解析为对话。请务必严格按照以下示例格式输出，每行以 主持[情绪]： 或 嘉宾[情绪]： 开头，绝不允许写成叙述文或段落。】"

    expansion_hint = ""
    if len(text_for_llm) > 3000:
        expansion_hint = "\n\n【展开要求】本段原文信息量丰富，请充分展开讨论。关键数据要逐层解读，典型案例要完整还原，逻辑链条要逐步拆解。不要急于总结，不要一句话带过。"

    citation_hint = ""
    if prompt_mode == "citation":
        citation_hint = "\n\n【引用强制】每句话后面必须标注出自原文的段落编号，格式为（出自原文第X段）。这个标注仅用于后续校对，不参与对话朗读。"

    if context:
        prompt = f"""前文对话（请自然延续，不要重复。开头请用一句简短的过渡句承接上文，然后进入本段正题）：
{context}

本段原文如下：
{text_for_llm}

请根据以上原文继续创作双人播客对话。要求：
1. 开头用一句过渡句自然承接上文，然后进入本段内容
2. 覆盖本段原文的所有重要论点、关键数据和典型案例
3. 句子自然流畅，允许使用专业术语
4. 嘉宾提出问题和质疑，主持分析总结
5. 输出格式：每行 "主持[情绪]：..." 或 "嘉宾[情绪]：..."
6. 不要序号，不要多余内容
7. 每行必须以 "主持[" 或 "嘉宾[" 开头，禁止叙述文或段落{_FORMAT_EXAMPLE}{f"\n8. {duration_line}" if duration_line else ""}{citation_hint}{expansion_hint}{format_reminder}"""
    else:
        prompt = f"""原文如下：
{text_for_llm}

请根据以上原文创作双人播客对话。要求：
1. 完整覆盖原文所有重要论点、关键数据和典型案例
2. 句子自然流畅，允许使用专业术语
3. 嘉宾提出问题和质疑，主持分析总结
4. 输出格式：每行 "主持[情绪]：..." 或 "嘉宾[情绪]：..."
5. 不要编号，不要多余内容
6. 每行必须以 "主持[" 或 "嘉宾[" 开头，禁止叙述文或段落{_FORMAT_EXAMPLE}{f"\n7. {duration_line}" if duration_line else ""}{citation_hint}{expansion_hint}{format_reminder}"""

    return _call_ai(system, prompt, model=model, temperature=temperature)


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


def _semantic_split_chunks(text: str, chunk_size: int = 4500, overlap: int = 600, api_key: str | None = None) -> list[str]:
    """Semantic chunking: split text at topic boundaries using sentence embeddings.
    Returns overlapping chunks aligned with semantic boundaries."""
    api_key = api_key or ZHI_API_KEY
    if not api_key:
        logger.warning("No API key for semantic splitting, falling back to text chunks")
        return _split_text_chunks(text, chunk_size=chunk_size, overlap=overlap)

    # 1. Split into sentences
    raw = re.split(r'([。！？\n])', text)
    sentences = []
    buf = ""
    for part in raw:
        buf += part
        if part in "。！？\n":
            s = buf.strip()
            if s:
                sentences.append(s)
            buf = ""
    if buf.strip():
        sentences.append(buf.strip())

    if not sentences:
        return [text]

    # 2. Get embeddings in batches using shared utility
    all_embeddings = []
    batch_size = 50
    for i in range(0, len(sentences), batch_size):
        batch = sentences[i:i+batch_size]
        embs = _get_embeddings_batch(batch)
        if not embs:
            return _split_text_chunks(text, chunk_size=chunk_size, overlap=overlap)
        all_embeddings.extend(embs)

    if len(all_embeddings) != len(sentences):
        return _split_text_chunks(text, chunk_size=chunk_size, overlap=overlap)

    # 3. Compute cosine similarities between adjacent sentences
    sims = [_cosine_similarity(all_embeddings[i], all_embeddings[i+1]) for i in range(len(all_embeddings)-1)]
    if not sims:
        return [text]

    # 4. Determine split points where similarity is low
    # Use a percentile-based threshold (bottom 25%)
    sorted_sims = sorted(sims)
    threshold = sorted_sims[max(0, len(sorted_sims)//4)] if len(sorted_sims) >= 4 else 0.5

    split_indices = [0]
    current_len = len(sentences[0])
    for i, sim in enumerate(sims):
        sent_len = len(sentences[i+1])
        # Force split if chunk is big enough and similarity is low
        if current_len >= chunk_size and sim <= threshold:
            split_indices.append(i+1)
            current_len = sent_len
        elif current_len >= chunk_size * 1.5:
            # Hard cap to avoid oversized chunks
            split_indices.append(i+1)
            current_len = sent_len
        else:
            current_len += sent_len

    split_indices.append(len(sentences))

    # 5. Build chunks with overlap
    chunks = []
    for i in range(len(split_indices)-1):
        start = split_indices[i]
        end = split_indices[i+1]
        # Back up for overlap
        if i > 0 and start > 0:
            overlap_start = max(0, start - 2)
            chunk_text = "".join(sentences[overlap_start:end])
        else:
            chunk_text = "".join(sentences[start:end])
        if chunk_text.strip():
            chunks.append(chunk_text.strip())

    return chunks if chunks else [text]


def _extract_native_headers(text: str) -> list[tuple[int, int, str]]:
    """Extract native section headers from original text.
    Returns list of (start_idx, end_idx, header_text) sorted by position."""
    headers = []
    # Markdown headers: ## Title
    for m in re.finditer(r'^#{2,4}\s+(.+)$', text, re.MULTILINE):
        headers.append((m.start(), m.end(), m.group(1).strip()))
    # Chinese numerals: 一、Title or （一）Title
    for m in re.finditer(r'^[一二三四五六七八九十]+[、．.]\s*(.+)$', text, re.MULTILINE):
        headers.append((m.start(), m.end(), m.group(1).strip()))
    for m in re.finditer(r'^（[一二三四五六七八九十]+）\s*(.+)$', text, re.MULTILINE):
        headers.append((m.start(), m.end(), m.group(1).strip()))
    # Arabic numerals: 1. Title or 1、Title
    for m in re.finditer(r'^\d+[、.．]\s*(.+)$', text, re.MULTILINE):
        headers.append((m.start(), m.end(), m.group(1).strip()))
    # Named keywords as standalone lines
    named_keywords = ["引言", "背景", "现状", "分析", "案例", "结论", "总结", "展望", "建议", "核心", "趋势", "数据", "影响", "观点", "原因", "结果"]
    for kw in named_keywords:
        for m in re.finditer(r'^(' + re.escape(kw) + r')\s*$', text, re.MULTILINE):
            headers.append((m.start(), m.end(), m.group(1).strip()))

    headers.sort(key=lambda x: x[0])
    # Remove overlaps (keep earliest)
    cleaned = []
    last_end = -1
    for start, end, title in headers:
        if start >= last_end:
            cleaned.append((start, end, title))
            last_end = end
    return cleaned


def _hybrid_split_chunks(text: str, chunk_size: int = 3500, overlap: int = 600) -> list[str]:
    """Hybrid chunking: semantic topic detection + recursive paragraph alignment.

    Process:
    1. Split text into paragraphs (same as recursive)
    2. Embed each paragraph → detect topic shifts via cosine similarity
    3. Form chunks at topic boundaries, but also respect chunk_size cap
    4. Apply overlap for context continuity

    This gives faithfulness of recursive (paragraph integrity) + coherence of
    semantic (topic-aligned boundaries).
    """
    if len(text) <= chunk_size:
        return [text]

    # 1. Split into paragraphs (by double newline)
    raw_paras = re.split(r'\n\s*\n', text)
    paragraphs = [p.strip() for p in raw_paras if p.strip()]
    if not paragraphs:
        return [text]

    # 2. Handle short texts with few paragraphs
    if len(paragraphs) <= 2:
        return _split_text_chunks(text, chunk_size=chunk_size, overlap=overlap)

    # 3. Get paragraph embeddings
    embs = _get_embeddings_batch(paragraphs, max_chars=300)
    if not embs or len(embs) != len(paragraphs):
        return _split_text_chunks(text, chunk_size=chunk_size, overlap=overlap)

    # 4. Detect topic shifts: low similarity between consecutive paragraphs
    sims = []
    for i in range(len(embs) - 1):
        sim = _cosine_similarity(embs[i], embs[i + 1])
        sims.append(sim)

    # Dynamic threshold: bottom 30th percentile, clamped to [0.3, 0.8]
    sorted_sims = sorted(sims)
    p30 = sorted_sims[max(0, int(len(sorted_sims) * 0.3))]
    shift_threshold = max(0.3, min(0.8, p30))

    # 5. Build chunks
    para_lens = [len(p) for p in paragraphs]
    chunks = []
    chunk_start = 0
    current_len = 0

    for i in range(len(paragraphs)):
        current_len += para_lens[i]
        is_last = (i == len(paragraphs) - 1)
        is_topic_shift = (i < len(sims) and sims[i] < shift_threshold)

        # Decision: should we cut at this paragraph boundary?
        should_cut = False
        if is_last:
            should_cut = True
        elif current_len >= chunk_size:
            # Past chunk_size: cut at this paragraph boundary.
            # Bonus if also a topic shift → even cleaner boundary.
            should_cut = True
        elif current_len >= chunk_size * 1.3:
            should_cut = True  # Hard safety cap

        if should_cut:
            # Build chunk from chunk_start to i (inclusive)
            chunk_text = "\n\n".join(paragraphs[chunk_start:i + 1])
            if chunk_text.strip():
                chunks.append(chunk_text.strip())

            # Next chunk starts here, but with overlap: include last paragraph
            if not is_last:
                overlap_start = max(chunk_start, i - 1)  # at least 1 paragraph overlap
                chunk_start = overlap_start
                current_len = sum(para_lens[overlap_start:i + 1])
            else:
                chunk_start = i + 1
                current_len = 0

    return chunks if chunks else [text]


def _has_clear_structure(text: str) -> bool:
    """Detect if text has clear section headers suitable for outline-first."""
    headers = _extract_native_headers(text)
    if len(headers) >= 3:
        return True
    # Fallback: check for repeated keywords in first 3000 chars
    section_keywords = ["引言", "背景", "现状", "分析", "案例", "结论", "总结", "展望", "建议", "核心", "趋势", "数据", "影响", "观点", "原因", "结果"]
    matches = sum(1 for kw in section_keywords if kw in text[:3000])
    if matches >= 3:
        return True
    return False


def generate_structured_dialogue(clean_text: str, opening_text: str = "", model: str | None = None, duration: str | None = None, split_strategy: str = "section", prompt_mode: str = "original") -> tuple[list[dict], dict, int, list[dict] | None]:
    t0 = time.time()
    length = len(clean_text)

    # Auto-select prompt_mode based on text length
    resolved_mode = _resolve_prompt_mode(length, prompt_mode)
    if resolved_mode != prompt_mode:
        logger.info(f"Auto-switched prompt_mode: {prompt_mode} -> {resolved_mode} for {length} chars")
        prompt_mode = resolved_mode

    # Strategy selection: section for >4000 (default), single-shot for shorter texts.
    strategy = "single-shot" if length <= 4000 else "chunked-fallback"
    logger.info(f"Generation strategy: {strategy} for {length} chars (duration={duration}, split={split_strategy}, prompt={prompt_mode})")

    # Phase 1: Section-based generation (Structure-first Hybrid RAG)
    # Only for long texts (>4000 chars); short texts keep single-shot.
    # Falls back to original chunking if section generation fails.
    if split_strategy == "section" and length > 4000:
        try:
            from section_generator import generate_by_section as _section_gen
            dialogue, scores, elapsed, section_meta = _section_gen(clean_text, model=model, duration=duration)
            return dialogue, scores, elapsed, section_meta
        except Exception as e:
            logger.warning(f"Section generation failed ({e}), falling back to original chunking")

    if length <= 4000:
        # Single-shot for short texts
        max_attempts = 2
        dialogue = []
        dialogue_raw = ""
        for attempt in range(1, max_attempts + 1):
            try:
                if opening_text:
                    prompt = f"""原文如下：\n{clean_text}\n\n已有开场对话（请延续以下开场白的风格和节奏，从开场之后继续生成，不要重复开场内容）：\n{opening_text}\n\n请根据以上原文创作双人播客对话，从开场之后继续。要求：\n1. 正文对话的风格、节奏、语气应与开场白保持一致，避免风格突变\n2. 完整覆盖原文所有重要论点、关键数据和典型案例\n3. 句子自然流畅，允许使用专业术语\n4. 嘉宾提出问题和质疑，主持分析总结\n5. 输出格式：每行 "主持[情绪]：..." 或 "嘉宾[情绪]：..."\n6. 不要编号，不要多余内容\n7. 每行必须以 "主持[" 或 "嘉宾[" 开头，禁止叙述文或段落{_FORMAT_EXAMPLE}{f"\n8. {_duration_hint(duration)}" if duration and duration != "free" else ""}{"\n\n【重试——上一次的输出格式不正确，请务必严格按照上述示例格式输出。】" if attempt > 1 else ""}"""
                    system = _select_system_prompt(prompt_mode, is_first=True)
                    raw = _call_ai(system, prompt, model=model, temperature=0.7)
                else:
                    raw = _generate_single_dialogue(clean_text, model=model, duration=duration, format_retry=(attempt > 1), prompt_mode=prompt_mode)
                dialogue = parse_dialogue(raw)
                has_speaker, format_valid = validate_dialogue_format(dialogue)
                if dialogue and len(dialogue) >= 3 and format_valid:
                    dialogue_raw = raw
                    break
                logger.warning(f"Single-shot attempt {attempt} produced invalid format ({len(dialogue)} turns, valid={format_valid}), retrying...")
            except Exception as e:
                logger.warning(f"Single-shot attempt {attempt} failed: {e}")
        if not dialogue or len(dialogue) < 3:
            raise ValueError("Failed to generate valid dialogue after retries")
        llm_time = int((time.time() - t0) * 1000)
        logger.info(f"Generated {len(dialogue)} dialogue turns (LLM: {llm_time}ms)")
        _check_role_consistency(dialogue)
        eval_scores = evaluate_dialogue(clean_text, dialogue)
        logger.info(f"Self-evaluation scores: {eval_scores}")

        # Write metrics for single-shot path too
        output_length = sum(len(d["text"]) for d in dialogue)
        text_stats = _compute_text_stats(dialogue)
        role_violations = _check_role_consistency(dialogue)
        _write_metrics(METRICS_GENERATION_PATH, {
            "request_id": str(uuid.uuid4()), "session_id": None,
            "model": model, "prompt_mode": prompt_mode, "split_strategy": "single-shot",
            "chunk_count": None,
            "total_turns": len(dialogue), "output_length_chars": output_length,
            "expansion_ratio": round(output_length / max(1, length), 4),
            "llm_time_ms": llm_time,
            "keyword_coverage": eval_scores.get("keyword_coverage"),
            "faithfulness": eval_scores.get("faithfulness"),
            "q2_score": eval_scores.get("q2_score"),
            "role_distinction": eval_scores.get("role_distinction"),
            "distinct_1": eval_scores.get("distinct_1"),
            "distinct_2": eval_scores.get("distinct_2"),
            "content_accuracy_score": eval_scores.get("content_accuracy_score"),
            "colloquial_score": eval_scores.get("colloquial_score"),
            "role_difference_score": eval_scores.get("role_difference_score"),
            "scene_fit_score": eval_scores.get("scene_fit_score"),
            "format_valid": True, "has_speaker_format": True,
            "role_violation_rate": round(role_violations["total"] / max(1, len(dialogue)), 4),
            "numeric_hallucination_rate": eval_scores.get("numeric_hallucination_rate"),
            "entity_hallucination_rate": eval_scores.get("entity_hallucination_rate"),
            "keyword_omission_rate": eval_scores.get("keyword_omission_rate"),
            "coherence_score": eval_scores.get("coherence_score"),
            "coherence_std": eval_scores.get("coherence_std"),
            "opening_closing_score": eval_scores.get("opening_closing_score"),
            "opening_guest_first": eval_scores.get("opening_guest_first"),
            "closing_host_last": eval_scores.get("closing_host_last"),
            **text_stats,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return dialogue, eval_scores, llm_time, None

    # Long texts (>4000): use fallback chunking directly (outline-first deprecated)
    chunk_size = 3500  # Balanced: enough context per chunk, more chunks for better coverage
    overlap = 600
    if split_strategy == "semantic":
        chunks = _semantic_split_chunks(clean_text, chunk_size=chunk_size, overlap=overlap)
    elif split_strategy == "hybrid":
        chunks = _hybrid_split_chunks(clean_text, chunk_size=chunk_size, overlap=overlap)
    else:
        chunks = _split_text_chunks(clean_text, chunk_size=chunk_size, overlap=overlap)
    logger.info(f"Long text ({len(clean_text)} chars) split into {len(chunks)} chunks")

    all_dialogue = []
    chunk_dialogues = []  # Track per-chunk dialogues for transition scoring
    prev_context = ""
    total_llm_time = 0

    for idx, chunk in enumerate(chunks):
        chunk_t0 = time.time()
        system = _select_system_prompt(prompt_mode, is_first=(idx == 0))
        chunk_dialogue = []
        for attempt in range(1, 3):
            try:
                raw = _generate_single_dialogue(chunk, system=system,
                                                 context=prev_context,
                                                 is_continuation=not (idx == 0),
                                                 duration=duration,
                                                 format_retry=(attempt > 1),
                                                 prompt_mode=prompt_mode)
                chunk_dialogue = parse_dialogue(raw)
                if chunk_dialogue:
                    break
                logger.warning(f"Chunk {idx + 1} attempt {attempt} produced no dialogue, retrying...")
            except Exception as e:
                logger.warning(f"Chunk {idx + 1} attempt {attempt} failed: {e}")
        chunk_time = int((time.time() - chunk_t0) * 1000)
        total_llm_time += chunk_time

        if not chunk_dialogue:
            logger.warning(f"Chunk {idx + 1} produced no dialogue after retries, skipping")
            continue
        _check_role_consistency(chunk_dialogue)

        if all_dialogue:
            chunk_dialogue = _deduplicate_overlap(all_dialogue, chunk_dialogue)

        all_dialogue.extend(chunk_dialogue)
        if chunk_dialogue:
            prev_context = "\n".join(f"{d['speaker']}：{d['text']}" for d in chunk_dialogue[-2:])
            chunk_dialogues.append(chunk_dialogue)  # Save for transition scoring

        logger.info(f"Chunk {idx + 1}/{len(chunks)}: {len(chunk_dialogue)} turns ({chunk_time}ms)")

    if not all_dialogue:
        raise ValueError("Failed to generate dialogue from any chunk")

    logger.info(f"Total {len(all_dialogue)} dialogue turns from {len(chunks)} chunks (LLM: {total_llm_time}ms)")

    # Self-evaluation on full dialogue
    eval_scores = evaluate_dialogue(clean_text, all_dialogue)
    logger.info(f"Self-evaluation scores: {eval_scores}")

    # Chunk transition score (only for multi-chunk generations)
    chunk_transition_score = None
    if len(chunk_dialogues) >= 2:
        chunk_transition_score = _chunk_transition_score(chunk_dialogues)
        logger.info(f"Chunk transition score: {chunk_transition_score}")

    output_length = sum(len(d["text"]) for d in all_dialogue)
    text_stats = _compute_text_stats(all_dialogue)
    role_violations = _check_role_consistency(all_dialogue)
    _write_metrics(METRICS_GENERATION_PATH, {
        "request_id": str(uuid.uuid4()), "session_id": None,
        "model": model, "prompt_mode": prompt_mode, "split_strategy": split_strategy,
        "chunk_count": len(chunks) if length > 4000 else None,
        "total_turns": len(all_dialogue), "output_length_chars": output_length,
        "expansion_ratio": round(output_length / max(1, length), 4),
        "llm_time_ms": total_llm_time,
        # First-tier
        "keyword_coverage": eval_scores.get("keyword_coverage"),
        "faithfulness": eval_scores.get("faithfulness"),
        "q2_score": eval_scores.get("q2_score"),
        "role_distinction": eval_scores.get("role_distinction"),
        "distinct_1": eval_scores.get("distinct_1"),
        "distinct_2": eval_scores.get("distinct_2"),
        "content_accuracy_score": eval_scores.get("content_accuracy_score"),
        "colloquial_score": eval_scores.get("colloquial_score"),
        "role_difference_score": eval_scores.get("role_difference_score"),
        "scene_fit_score": eval_scores.get("scene_fit_score"),
        "format_valid": True, "has_speaker_format": True,
        "role_violation_rate": round(role_violations["total"] / max(1, len(all_dialogue)), 4),
        # Second-tier
        "numeric_hallucination_rate": eval_scores.get("numeric_hallucination_rate"),
        "entity_hallucination_rate": eval_scores.get("entity_hallucination_rate"),
        "keyword_omission_rate": eval_scores.get("keyword_omission_rate"),
        "coherence_score": eval_scores.get("coherence_score"),
        "coherence_std": eval_scores.get("coherence_std"),
        "opening_closing_score": eval_scores.get("opening_closing_score"),
        "opening_guest_first": eval_scores.get("opening_guest_first"),
        "closing_host_last": eval_scores.get("closing_host_last"),
        "chunk_transition_score": chunk_transition_score,
        **text_stats,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return all_dialogue, eval_scores, total_llm_time, None

# ── Utility: Fetch article ──

def fetch_article(url: str) -> tuple[str, str]:
    logger.info(f"Fetching: {url}")
    try:
        resp = requests.get(url, headers=FETCH_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.Timeout:
        raise ValueError("请求超时")
    except requests.ConnectionError:
        raise ValueError("无法连接目标网站")
    except requests.HTTPError as e:
        if e.response.status_code == 403:
            raise ValueError("该链接无法访问（网站限制了自动抓取），请尝试使用「文本」模式手动粘贴内容")
        raise ValueError(f"HTTP {e.response.status_code}")
    except requests.RequestException as e:
        raise ValueError(f"请求失败: {str(e)[:100]}")

    resp.encoding = resp.apparent_encoding or "utf-8"
    html = resp.text
    if len(html) < 200:
        raise ValueError("网页内容过短")

    title, body = "", ""

    # Strategy 1: readability-lxml (fast, works on most blogs/articles)
    try:
        doc = Document(html)
        title = doc.title() or ""
        soup = BeautifulSoup(doc.summary(), "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "aside"]):
            tag.decompose()
        body = soup.get_text(separator="\n", strip=True)
    except Exception:
        pass

    # Strategy 2: trafilatura (handles more sites, better at extracting structured content)
    if len(body) < 50:
        try:
            import trafilatura
            extracted = trafilatura.extract(html, include_tables=False, include_images=False,
                                            include_links=False, favor_precision=True,
                                            no_fallback=False)
            if extracted and len(extracted) > len(body):
                body = extracted.strip()
            if not title:
                t = trafilatura.extract(html, output_format="json", favor_precision=True)
                if t:
                    import json
                    meta = json.loads(t)
                    title = meta.get("title", "") or ""
        except Exception:
            pass

    # Strategy 3: meta tags fallback (works on JS-rendered sites with og tags)
    if len(body) < 50:
        try:
            soup = BeautifulSoup(html, "html.parser")
            if not title:
                for mt in [soup.find("meta", property="og:title"),
                           soup.find("meta", attrs={"name": "twitter:title"}),
                           soup.find("h1")]:
                    if mt:
                        t = mt.get("content", "") if mt.name == "meta" else mt.get_text(strip=True)
                        if t:
                            title = t
                            break
            for mt in [soup.find("meta", property="og:description"),
                       soup.find("meta", attrs={"name": "description"}),
                       soup.find("meta", attrs={"name": "twitter:description"})]:
                if mt and mt.get("content"):
                    body = mt["content"].strip()
                    break
            # Also try <article> tag and common content classes
            if len(body) < 50:
                article = soup.find("article")
                if article:
                    for tag in article(["script", "style", "nav", "footer", "aside"]):
                        tag.decompose()
                    body = article.get_text(separator="\n", strip=True)
        except Exception:
            pass

    if len(body) < 50:
        raise ValueError("未能提取有效正文，请检查链接是否正确，或尝试使用「文本」模式手动粘贴内容")
    return title.strip(), body

# ── TTS ──

def tts_script(script: list[dict], voice_map: dict | None = None) -> str:
    out_path = Path(tempfile.mkdtemp(prefix="boke_")) / "podcast.mp3"
    logger.info(f"TTS starting {len(script)} turns via Fish Audio...")
    # Allow voice_map to override default voice IDs
    male_id = voice_map.get("主持", MALE_VOICE_ID) if voice_map else MALE_VOICE_ID
    female_id = voice_map.get("嘉宾", FEMALE_VOICE_ID) if voice_map else FEMALE_VOICE_ID
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
        duration_s = None
        logger.info(f"TTS done: {out_path}")

    # TTS metrics
    from collections import Counter
    emotions = [t.get("emotion") for t in script if t.get("emotion")]
    emotion_dist = dict(Counter(emotions))
    _write_metrics(METRICS_PLAYBACK_PATH, {
        "request_id": str(uuid.uuid4()), "session_id": None,
        "phase": "tts", "voice_map": voice_map,
        "emotion_distribution": emotion_dist,
        "total_turns": len(script), "tts_time_ms": None,
        "audio_duration_s": duration_s,
        "high_quality": False, "bg_music": False, "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return str(out_path)

def _post_process_audio(input_path: str, high_quality: bool = False, bg_music: bool = False, bgm_path: str | None = None) -> str:
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

    if bg_music or bgm_path:
        try:
            dur = subprocess.run(
                [FFPROBE_PATH, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", current],
                capture_output=True, text=True, check=True
            )
            duration = float(dur.stdout.strip())
            bg_path = tmp_dir / "bg_pad.mp3"
            if bgm_path and Path(bgm_path).exists():
                # Use uploaded custom BGM
                subprocess.run(
                    [FFMPEG_PATH, "-y", "-i", bgm_path,
                     "-t", str(duration + 1), "-ac", "2", "-ar", "44100",
                     "-af", "volume=0.3", str(bg_path)],
                    check=True, capture_output=True
                )
                bg_volume = 0.2
            else:
                # Generate a soft ambient pad (C major chord)
                subprocess.run(
                    [FFMPEG_PATH, "-y", "-f", "lavfi",
                     "-i", "aevalsrc=0.05*sin(261.63*2*PI*t)+0.025*sin(329.63*2*PI*t)+0.015*sin(392.00*2*PI*t):s=48000",
                     "-t", str(duration + 1), "-ac", "2", "-ar", "44100", str(bg_path)],
                    check=True, capture_output=True
                )
                bg_volume = 0.06
            final_path = tmp_dir / "final.mp3"
            fade = f"afade=t=out:st={duration}:d=1"
            subprocess.run(
                [FFMPEG_PATH, "-y", "-i", current, "-i", str(bg_path),
                 "-filter_complex",
                 f"[0:a]volume=1.0[a0];[1:a]{fade},volume={bg_volume}[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[a]",
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


def _resolve_preset(settings: dict, section: str, preset_key: str) -> dict:
    """Resolve preset config if preset_id is specified, otherwise return section config."""
    section_cfg = dict(settings.get(section, {}))
    preset_id = settings.get(preset_key)
    presets = settings.get(f"{section}_presets", [])
    if preset_id and presets:
        for p in presets:
            if p.get("id") == preset_id:
                # Keep enabled state from section_cfg, override everything else with preset
                enabled = section_cfg.get("enabled")
                section_cfg.update({k: v for k, v in p.items() if k not in ("id", "name")})
                if enabled is not None:
                    section_cfg["enabled"] = enabled
                break
    return section_cfg


def _compute_timings(script: list[dict], section_metadata: list[dict] | None = None) -> list[dict]:
    """Estimate per-turn timestamps based on text length (~4 chars/sec).

    Returns list of {turn_index, start, end, speaker, section_id}.
    """
    timings = []
    acc = 0.0
    for i, turn in enumerate(script):
        dur = max(1.5, len(turn.get("text", "")) / 4.0)
        section_id = None
        if section_metadata:
            for sec in section_metadata:
                if sec["turn_start"] <= i < sec["turn_end"]:
                    section_id = sec["section_id"]
                    break
        timings.append({
            "turn_index": i,
            "start": round(acc, 1),
            "end": round(acc + dur, 1),
            "speaker": turn.get("speaker", ""),
            "section_id": section_id,
        })
        acc += dur
    return timings


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

    intro_cfg = _resolve_preset(settings, "intro", "intro_preset_id")
    outro_cfg = _resolve_preset(settings, "outro", "outro_preset_id")
    body_bgm_cfg = settings.get("body_bgm", {})

    # 1. Intro TTS (if enabled)
    intro_path = None
    if intro_cfg.get("enabled"):
        intro_text = intro_cfg.get("template", "欢迎收听播刻。").replace("{topic}", title or "本期话题")
        intro_speaker = intro_cfg.get("speaker", "主持")
        intro_voice = intro_cfg.get("voice_id")
        if not intro_voice and voice_map:
            intro_voice = voice_map.get(intro_speaker, MALE_VOICE_ID if intro_speaker == "主持" else FEMALE_VOICE_ID)
        intro_path = str(tmp_dir / "intro.mp3")
        ok = _generate_intro_tts(intro_text, intro_path, voice_id=intro_voice)
        if not ok:
            intro_path = None
            logger.warning("Intro TTS failed, skipping intro")

    # 2. Body TTS
    body_path = tts_script(script, voice_map=voice_map)

    # 3. Body BGM / high-quality post-processing
    if body_bgm_cfg.get("enabled"):
        bgm_path = body_bgm_cfg.get("custom_path")
        if bgm_path and not Path(bgm_path).is_absolute():
            bgm_path = str(BGM_UPLOAD_DIR / bgm_path)
        body_path = _post_process_audio(
            body_path, high_quality=high_quality, bg_music=True,
            bgm_path=bgm_path,
        )
    elif high_quality:
        body_path = _post_process_audio(body_path, high_quality=True, bg_music=False)

    # 4. Outro TTS (if enabled)
    outro_path = None
    if outro_cfg.get("enabled") and outro_cfg.get("mode") != "none":
        if outro_cfg.get("mode") == "ai_summary" and script:
            outro_text = f"以上就是关于{title or '这个话题'}的核心观点。感谢收听播刻，我们下期再见。"
        else:
            outro_text = outro_cfg.get("template", "感谢收听播刻，我们下期再见。")
        outro_speaker = outro_cfg.get("speaker", "主持")
        outro_voice = outro_cfg.get("voice_id")
        if not outro_voice and voice_map:
            outro_voice = voice_map.get(outro_speaker, MALE_VOICE_ID if outro_speaker == "主持" else FEMALE_VOICE_ID)
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

    # TTS metrics
    from collections import Counter
    emotions = [t.get("emotion") for t in script if t.get("emotion")]
    emotion_dist = dict(Counter(emotions))
    _write_metrics(METRICS_PLAYBACK_PATH, {
        "request_id": str(uuid.uuid4()), "session_id": None,
        "phase": "tts_arranged", "voice_map": voice_map,
        "emotion_distribution": emotion_dist,
        "total_turns": len(script), "tts_time_ms": None,
        "audio_duration_s": None,
        "high_quality": high_quality, "bg_music": bool(body_bgm_cfg.get("enabled")),
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return final_path


# ── TTFA Streaming Generation ──

# ── Session Storage (uses SQLite via database.py) ──

def _session_create(session_id: str, request_id: str, duration: str, title: str, user_id: str | None = None) -> dict:
    return session_create(session_id, request_id, duration, title, user_id)

def _session_get(session_id: str) -> dict | None:
    return session_get(session_id)

def _session_set(session_id: str, key: str, value):
    session_set(session_id, key, value)

def _session_delete(session_id: str):
    session_delete(session_id)

OPENING_SYSTEM = """你是一个播客开场白编剧。根据给定的话题，生成一段双人播客的精彩开场。

角色设定（双专家模式）：
- 嘉宾（细节追问者）：直接接地气，喜欢用有画面感的开场引入话题，从听众的实际关切出发
- 主持（框架梳理者）：沉稳专业，善于接话和点出话题的深层价值或引发好奇

要求：
1. 仅生成2轮对话：嘉宾开场（1句）→ 主持接话（1句）
2. 嘉宾的开场要有画面感，避免"今天我们来聊聊"这种干巴巴的开场
3. 主持要自然接住嘉宾的话，点出这个话题的价值或引发好奇
4. 句子简短自然，适合播客收听
5. 输出格式：每行 "嘉宾：..." 或 "主持：..."
6. 不要多余内容，不要标序号"""

INTRO_VARIATIONS_SYSTEM = """你是一个播客开场白模板设计师。请为给定话题生成 {count} 种不同风格的开场白模板。

每种开场白模板要求：
1. **name**：简短的风格名称（2-6字），如"悬念式""数据震撼""故事引入"
2. **template**：1-2句开场白文本，使用 `{topic}` 作为话题占位符
3. **speaker**：开场发言人——"主持"或"嘉宾"或"双声"
4. **transition_style**：过渡音乐风格——"warm"（温暖）、"cool"（冷静）、"micro"（轻快）、"minimal"（极简）
5. **transition_duration**：过渡音乐时长（秒），2.0-5.0 之间
6. **transition_volume**：过渡音乐音量，0.05-0.30 之间

{count} 种风格要差异明显，覆盖不同的开场策略（如：悬念提问、数据震撼、场景带入、观点冲突、故事引入）。

输出严格 JSON 数组（不要任何额外文字）：
```json
[
  {
    "name": "悬念式",
    "template": "你有没有想过——{topic}？今天我们就来聊聊这个。",
    "speaker": "嘉宾",
    "transition_style": "micro",
    "transition_duration": 3.0,
    "transition_volume": 0.15
  }
]
```"""

OUTRO_VARIATIONS_SYSTEM = """你是一个播客片尾模板设计师。请为给定话题生成 {count} 种不同风格的片尾模板。

每种片尾模板要求：
1. **name**：简短的风格名称（2-6字），如"温情收尾""金句总结"
2. **template**：1-2句片尾文本，可包含 `{topic}` 作为话题占位符
3. **speaker**：发言人——"主持"或"嘉宾"
4. **mode**：固定为 "template"

{count} 种风格要差异明显，覆盖不同的收尾策略（如：总结式、启发式、温情式、行动号召、金句式）。

输出严格 JSON 数组（不要任何额外文字）：
```json
[
  {
    "name": "总结式",
    "template": "以上就是关于{topic}的全部内容。感谢收听播刻，我们下期再见。",
    "speaker": "主持",
    "mode": "template"
  }
]
```"""


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
    raw = _call_ai(OPENING_SYSTEM, prompt)
    logger.info(f"Opening generated ({int((time.time()-t0)*1000)}ms): {raw[:100]}")
    dialogue = parse_dialogue(raw)
    if len(dialogue) < 2:
        logger.warning(f"Opening parse failed, using fallback. Raw: {raw}")
        dialogue = [
            {"speaker": "嘉宾", "text": f"你听说过{topic[:20]}吗？这事儿挺有意思的。"},
            {"speaker": "主持", "text": "还真没仔细了解，你给说说？"},
        ]
    return dialogue[:2]


def _start_generation(url: str, text: str, duration: str, title: str | None = None, request_id: str | None = None, model: str | None = None, high_quality: bool = False, bg_music: bool = False, voice_map: dict | None = None, prompt_mode: str = "original", intro_preset_id: str | None = None, outro_preset_id: str | None = None, user_id: str | None = None) -> tuple[str, list[dict]]:
    """Create session, generate opening script, and start background thread.
    Returns (session_id, opening_script)."""
    if not request_id:
        request_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    if not title:
        title = _quick_title(url) if url else text[:80].strip() if text else "未知话题"
    if not title:
        title = "未知话题"

    _session_create(session_id, request_id, duration, title, getattr(g, 'user_id', None))
    _session_set(session_id, "model", model)
    _session_set(session_id, "high_quality", high_quality)
    _session_set(session_id, "bg_music", bg_music)
    _session_set(session_id, "voice_map", voice_map)
    _session_set(session_id, "prompt_mode", prompt_mode)
    if intro_preset_id:
        _session_set(session_id, "intro_preset_id", intro_preset_id)
    if outro_preset_id:
        _session_set(session_id, "outro_preset_id", outro_preset_id)

    # A/B experiment assignment
    input_length = len(url or text)
    exp_config = _assign_experiment(request_id, input_length)
    if exp_config:
        logger.info(f"Experiment assigned for request {request_id}: {exp_config}")
        if "prompt_mode" in exp_config:
            _session_set(session_id, "prompt_mode", exp_config["prompt_mode"])
        if "model" in exp_config:
            _session_set(session_id, "model", exp_config["model"])
        if "temperature" in exp_config:
            _session_set(session_id, "temperature", exp_config["temperature"])
        _session_set(session_id, "experiment_config", exp_config)

    opening_script = generate_opening(title)
    _session_set(session_id, "opening_script", opening_script)
    _session_set(session_id, "progress", 30)

    thread = threading.Thread(
        target=_background_full_generation,
        args=(session_id, url, text, duration, opening_script, model, high_quality, bg_music, intro_preset_id, outro_preset_id),
        daemon=True,
    )
    thread.start()
    return session_id, opening_script


def _tts_script_segment(script: list[dict], tag: str = "seg", voice_map: dict | None = None) -> str:
    """TTS a subset of turns. Returns path to combined mp3 via Fish Audio."""
    out_path = Path(tempfile.mkdtemp(prefix=f"boke_{tag}_")) / f"{tag}.mp3"
    male_id = voice_map.get("主持", MALE_VOICE_ID) if voice_map else MALE_VOICE_ID
    female_id = voice_map.get("嘉宾", FEMALE_VOICE_ID) if voice_map else FEMALE_VOICE_ID
    generate_podcast(script, output_path=str(out_path),
                     male_ref_id=male_id or None,
                     female_ref_id=female_id or None)
    return str(out_path)


def _build_continuation_prompt(opening_script: list[dict]) -> str:
    """Format opening dialogue as context for STEP2 to continue from."""
    return "\n".join(f"{d['speaker']}：{d['text']}" for d in opening_script)


def _background_full_generation(session_id: str, url: str, text: str,
                                 duration: str, opening_script: list[dict],
                                 model: str | None = None, high_quality: bool = False, bg_music: bool = False,
                                 intro_preset_id: str | None = None, outro_preset_id: str | None = None):
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

        session_prompt_mode = (_session_get(session_id) or {}).get("prompt_mode", "original")
        result = generate_structured_dialogue(
            clean_text, opening_text=opening_text, model=model, duration=duration, prompt_mode=session_prompt_mode
        )
        if len(result) == 4:
            full_dialogue, eval_scores, llm_time, section_metadata = result
        else:
            full_dialogue, eval_scores, llm_time = result
            section_metadata = None
        _session_set(session_id, "llm_time_ms", llm_time)
        _session_set(session_id, "section_metadata", section_metadata)
        _session_set(session_id, "progress", 70)

        if not full_dialogue:
            raise ValueError("Failed to parse full dialogue")
        logger.info(f"[bg] Full dialogue: {len(full_dialogue)} turns ({llm_time}ms)")

        complete_dialogue = opening_script + full_dialogue
        _session_set(session_id, "full_script", complete_dialogue)

        # Compute per-turn timestamps for chapter timeline
        if section_metadata:
            # Adjust section turn_start/turn_end to account for opening_script offset
            offset = len(opening_script)
            adjusted_metadata = []
            for sec in section_metadata:
                s = dict(sec)
                s["turn_start"] = sec["turn_start"] + offset
                s["turn_end"] = sec["turn_end"] + offset
                adjusted_metadata.append(s)
            timings = _compute_timings(complete_dialogue, adjusted_metadata)
        else:
            timings = _compute_timings(complete_dialogue)
            adjusted_metadata = None
        _session_set(session_id, "timings", timings)
        if adjusted_metadata:
            _session_set(session_id, "section_metadata", adjusted_metadata)

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
        if intro_preset_id:
            settings["intro_preset_id"] = intro_preset_id
        if outro_preset_id:
            settings["outro_preset_id"] = outro_preset_id
        tmp_dir = Path(tempfile.mkdtemp(prefix="boke_arrange_"))
        final_path = _generate_arranged_podcast(
            full_dialogue, settings, voice_map=voice_map,
            high_quality=high_quality, title=title, tmp_dir=tmp_dir,
        )

        tts_ms = int((time.time() - t2) * 1000)
        _session_set(session_id, "tts_time_ms", tts_ms)
        # Persist audio to stable recordings/ directory
        final_path = save_audio_file(final_path, session_id)
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


def _session_cleanup_loop():
    """Daemon thread: remove stale sessions every 30 minutes."""
    while True:
        time.sleep(1800)
        try:
            now = time.time()
            all_sessions = session_list()
            for s in all_sessions:
                if now - s.get("created_at", 0) > 86400:  # 24h timeout
                    session_delete(s.get("id", ""))
                    audio_path = s.get("full_audio_path")
                    if audio_path:
                        try:
                            p = Path(audio_path)
                            if p.exists():
                                p.unlink()
                        except Exception:
                            pass
        except Exception as e:
            logger.warning(f"Session cleanup error: {e}")


# ── Auth helpers ──

from flask import g

def _require_auth(f):
    """Decorator: require valid JWT. Sets g.user_id on success."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        token = auth.replace("Bearer ", "") if auth.startswith("Bearer ") else ""
        if not token:
            return jsonify({"error": "请先登录"}), 401
        try:
            payload = pyjwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            g.user_id = payload["user_id"]
        except pyjwt.ExpiredSignatureError:
            return jsonify({"error": "登录已过期，请重新登录"}), 401
        except Exception:
            return jsonify({"error": "无效的登录凭证"}), 401
        return f(*args, **kwargs)
    return decorated

def _optional_auth(f):
    """Decorator: attach g.user_id if valid JWT present, continue as anonymous otherwise."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        token = auth.replace("Bearer ", "") if auth.startswith("Bearer ") else ""
        g.user_id = None
        if token:
            try:
                payload = pyjwt.decode(token, JWT_SECRET, algorithms=["HS256"])
                g.user_id = payload["user_id"]
            except Exception:
                pass
        return f(*args, **kwargs)
    return decorated


# ── Auth Routes ──


@app.route("/api/auth/register", methods=["POST"])
def api_auth_register():
    data = request.get_json(silent=True) or {}
    phone = (data.get("phone") or "").strip()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    session_ids = data.get("session_ids") or []

    # Validate phone
    if not re.match(r"^\d{8,15}$", phone):
        return jsonify({"error": "手机号格式不正确（8-15位数字）"}), 400
    if len(password) < 6:
        return jsonify({"error": "密码至少6位"}), 400
    if not username:
        username = phone[-4:]  # Default username from last 4 digits

    try:
        password_hash = generate_password_hash(password)
        user_id = user_create(phone, username, password_hash)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    except Exception as e:
        logger.error(f"Register failed: {e}")
        return jsonify({"error": "注册失败"}), 500

    # Merge anonymous sessions if provided
    if session_ids:
        session_claim_all(session_ids, user_id)

    token = pyjwt.encode(
        {"user_id": user_id, "phone": phone, "exp": datetime.now(timezone.utc) + timedelta(days=30)},
        JWT_SECRET,
        algorithm="HS256",
    )
    return jsonify({"token": token, "user": {"id": user_id, "phone": phone, "username": username}})


@app.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    data = request.get_json(silent=True) or {}
    phone = (data.get("phone") or "").strip()
    password = data.get("password") or ""
    session_ids = data.get("session_ids") or []

    user = user_get_by_phone(phone)
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "手机号或密码错误"}), 401

    # Merge anonymous sessions if provided
    if session_ids:
        session_claim_all(session_ids, user["id"])

    token = pyjwt.encode(
        {"user_id": user["id"], "phone": user["phone"], "exp": datetime.now(timezone.utc) + timedelta(days=30)},
        JWT_SECRET,
        algorithm="HS256",
    )
    return jsonify({
        "token": token,
        "user": {"id": user["id"], "phone": user["phone"], "username": user["username"]},
    })


@app.route("/api/auth/me", methods=["GET"])
@_require_auth
def api_auth_me():
    user = user_get_by_id(g.user_id)
    if not user:
        return jsonify({"error": "用户不存在"}), 404
    return jsonify({
        "user": {"id": user["id"], "phone": user["phone"], "username": user["username"]},
    })

# ── Routes ──

@app.route("/api/generate_streaming", methods=["POST"])
@_optional_auth
def api_generate_streaming():
    """TTFA-optimized endpoint: generate opening → return audio immediately, background full gen."""
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    text = data.get("text", "").strip()
    duration = data.get("duration", "standard")
    request_id = data.get("request_id", str(uuid.uuid4()))
    model = _resolve_model(data.get("model", "deepseek"))
    high_quality = bool(data.get("high_quality", False))
    bg_music = bool(data.get("bg_music", False))
    voice_map = data.get("voice_map")
    if voice_map and not isinstance(voice_map, dict):
        voice_map = None
    prompt_mode = data.get("prompt_mode", "auto")
    intro_preset_id = data.get("intro_preset_id")
    outro_preset_id = data.get("outro_preset_id")
    session_id = str(uuid.uuid4())
    t0 = time.time()

    if not url and not text:
        return jsonify({"error": "请提供 url 或 text"}), 400
    if not ZHI_API_KEY:
        return jsonify({"error": "服务端未配置 API 密钥"}), 500

    try:
        session_id, opening_script = _start_generation(url, text, duration, request_id=request_id, model=model, high_quality=high_quality, bg_music=bg_music, voice_map=voice_map, prompt_mode=prompt_mode, intro_preset_id=intro_preset_id, outro_preset_id=outro_preset_id, user_id=getattr(g, 'user_id', None))

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
        err_msg = str(e)[:200]
        if "空响应" in err_msg or "余额" in err_msg:
            err_msg = "AI 服务异常（可能是账户余额不足），请检查 API 密钥配置或联系客服充值"
        return jsonify({"error": err_msg}), 500


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

    audio_path = get_audio_path(session_id)
    if not audio_path:
        return jsonify({"error": "音频文件不存在"}), 404

    total_ms = (session.get("parse_time_ms", 0) +
                session.get("llm_time_ms", 0) +
                session.get("tts_time_ms", 0))

    resp = send_file(audio_path, mimetype="audio/mpeg")
    resp.headers["X-Total-Ms"] = str(total_ms)

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


@app.route("/api/generate-intro-presets", methods=["POST"])
def api_generate_intro_presets():
    """Generate N variations of intro opening templates."""
    data = request.get_json(force=True) or {}
    topic = data.get("topic", "")
    count = min(int(data.get("count", 3)), 5)
    if not topic:
        return jsonify({"error": "请提供 topic"}), 400

    prompt = f"话题：{topic}\n\n请为这个话题生成 {count} 种不同风格的开场白模板。"
    raw = _call_ai(INTRO_VARIATIONS_SYSTEM.format(count=count), prompt, temperature=0.8)
    try:
        json_match = re.search(r'```(?:json)?\s*(\[[\s\S]*?\])\s*```', raw, re.DOTALL)
        if json_match:
            presets = json.loads(json_match.group(1))
        else:
            presets = json.loads(raw)
        if not isinstance(presets, list):
            raise ValueError("not a list")
        for p in presets:
            p["id"] = f"intro_{uuid.uuid4().hex[:8]}"
            p.setdefault("voice_id", None)
        return jsonify({"presets": presets[:count]})
    except Exception as e:
        logger.warning(f"Failed to parse intro presets: {e}, raw: {raw[:200]}")
        return jsonify({"error": "AI 返回格式异常，请重试"}), 500


@app.route("/api/generate-outro-presets", methods=["POST"])
def api_generate_outro_presets():
    """Generate N variations of outro/closing templates."""
    data = request.get_json(force=True) or {}
    topic = data.get("topic", "")
    count = min(int(data.get("count", 3)), 5)
    if not topic:
        return jsonify({"error": "请提供 topic"}), 400

    prompt = f"话题：{topic}\n\n请为这个话题生成 {count} 种不同风格的片尾模板。"
    raw = _call_ai(OUTRO_VARIATIONS_SYSTEM.format(count=count), prompt, temperature=0.8)
    try:
        json_match = re.search(r'```(?:json)?\s*(\[[\s\S]*?\])\s*```', raw, re.DOTALL)
        if json_match:
            presets = json.loads(json_match.group(1))
        else:
            presets = json.loads(raw)
        if not isinstance(presets, list):
            raise ValueError("not a list")
        for p in presets:
            p["id"] = f"outro_{uuid.uuid4().hex[:8]}"
            p.setdefault("voice_id", None)
        return jsonify({"presets": presets[:count]})
    except Exception as e:
        logger.warning(f"Failed to parse outro presets: {e}, raw: {raw[:200]}")
        return jsonify({"error": "AI 返回格式异常，请重试"}), 500


@app.route("/api/settings/presets", methods=["POST"])
def api_settings_presets():
    """Save AI-generated presets into settings (merge, dedup by ID)."""
    data = request.get_json(force=True) or {}
    current = _load_settings()
    for section in ("intro", "outro"):
        presets_key = f"{section}_presets"
        new_presets = data.get(presets_key, [])
        if not new_presets:
            continue
        existing_ids = {p["id"] for p in current.get(presets_key, []) if p.get("id")}
        for p in new_presets:
            if p.get("id") and p["id"] not in existing_ids:
                current.setdefault(presets_key, []).append(p)
                existing_ids.add(p["id"])
    _save_settings(current)
    return jsonify(current)


@app.route("/api/upload_bgm", methods=["POST"])
def api_upload_bgm():
    """Upload a custom background music file (MP3/WAV/M4A/OGG)."""
    if "file" not in request.files:
        return jsonify({"error": "请上传音频文件"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "文件名不能为空"}), 400
    filename = secure_filename(file.filename)
    ext = Path(filename).suffix.lower()
    if ext not in {".mp3", ".wav", ".m4a", ".ogg"}:
        return jsonify({"error": f"不支持的音频格式: {ext}，请上传 MP3、WAV、M4A 或 OGG"}), 400
    saved_name = f"{uuid.uuid4().hex}{ext}"
    save_path = BGM_UPLOAD_DIR / saved_name
    file.save(str(save_path))
    logger.info(f"BGM uploaded: {saved_name} ({filename})")
    return jsonify({
        "filename": filename,
        "saved_name": saved_name,
        "path": str(save_path),
    })


@app.route("/api/bgm", methods=["GET"])
def api_bgm():
    """List uploaded background music files."""
    files = []
    if BGM_UPLOAD_DIR.exists():
        for f in sorted(BGM_UPLOAD_DIR.iterdir()):
            if f.is_file():
                files.append({
                    "id": f.name,
                    "name": f.name,
                    "path": str(f),
                    "size": f.stat().st_size,
                })
    return jsonify({"files": files})


@app.route("/api/bgm/<file_id>", methods=["DELETE"])
def api_delete_bgm(file_id: str):
    """Delete an uploaded BGM file."""
    target = BGM_UPLOAD_DIR / secure_filename(file_id)
    try:
        if target.exists() and target.is_file():
            target.unlink()
            logger.info(f"BGM deleted: {file_id}")
            return jsonify({"status": "deleted"})
        return jsonify({"error": "文件不存在"}), 404
    except Exception as e:
        logger.error(f"Delete BGM failed: {e}")
        return jsonify({"error": str(e)[:200]}), 500


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
            _write_metrics(METRICS_INPUT_PATH, {
                "request_id": request_id, "input_source": "url", "platform": "网页",
                "article_length_chars": len(clean_text), "has_native_headers": False,
                "header_count": 0, "parse_success": True, "parse_time_ms": parse_ms,
                "extraction_compression_ratio": round(len(clean_text) / max(1, input_length), 4),
                "chunk_count": None, "split_strategy": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
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
            _write_metrics(METRICS_INPUT_PATH, {
                "request_id": request_id, "input_source": "url", "platform": "网页",
                "article_length_chars": 0, "has_native_headers": False,
                "header_count": 0, "parse_success": False, "parse_time_ms": parse_ms,
                "extraction_compression_ratio": 0, "chunk_count": None, "split_strategy": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
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
        _write_metrics(METRICS_INPUT_PATH, {
            "request_id": request_id, "input_source": "text", "platform": "网页",
            "article_length_chars": len(clean_text), "has_native_headers": False,
            "header_count": 0, "parse_success": True, "parse_time_ms": parse_ms,
            "extraction_compression_ratio": 1.0, "chunk_count": None, "split_strategy": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
        _write_metrics(METRICS_INPUT_PATH, {
            "request_id": str(uuid.uuid4()), "input_source": "upload", "platform": "网页",
            "article_length_chars": len(clean_text), "has_native_headers": False,
            "header_count": 0, "parse_success": True, "parse_time_ms": parse_ms,
            "extraction_compression_ratio": round(len(clean_text) / max(1, file.content_length or len(clean_text)), 4),
            "chunk_count": None, "split_strategy": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return jsonify({
            "title": title,
            "clean_text": clean_text,
            "parse_time_ms": parse_ms,
            "input_type": "upload",
            "input_length": len(clean_text),
        })
    except ValueError as e:
        _write_metrics(METRICS_INPUT_PATH, {
            "request_id": str(uuid.uuid4()), "input_source": "upload", "platform": "网页",
            "article_length_chars": 0, "has_native_headers": False,
            "header_count": 0, "parse_success": False, "parse_time_ms": int((time.time() - t0) * 1000),
            "extraction_compression_ratio": 0, "chunk_count": None, "split_strategy": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Upload processing failed: {e}", exc_info=True)
        _write_metrics(METRICS_INPUT_PATH, {
            "request_id": str(uuid.uuid4()), "input_source": "upload", "platform": "网页",
            "article_length_chars": 0, "has_native_headers": False,
            "header_count": 0, "parse_success": False, "parse_time_ms": int((time.time() - t0) * 1000),
            "extraction_compression_ratio": 0, "chunk_count": None, "split_strategy": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return jsonify({"error": f"文件处理失败: {str(e)[:200]}"}), 500
    finally:
        if tmp_path and tmp_path.parent.exists():
            shutil.rmtree(tmp_path.parent, ignore_errors=True)


@app.route("/api/generate_script", methods=["POST"])
def api_generate_script():
    data = request.get_json(silent=True) or {}
    clean_text = data.get("clean_text", "").strip()
    request_id = data.get("request_id", str(uuid.uuid4()))
    model = _resolve_model(data.get("model", "deepseek"))
    duration = data.get("duration", "free")
    prompt_mode = data.get("prompt_mode", "auto")

    if not clean_text:
        return jsonify({"error": "clean_text 不能为空"}), 400
    if not ZHI_API_KEY:
        return jsonify({"error": "服务端未配置 API 密钥"}), 500

    try:
        t0 = time.time()

        # A/B experiment assignment
        exp_config = _assign_experiment(request_id, len(clean_text))
        if exp_config:
            logger.info(f"Experiment assigned for request {request_id}: {exp_config}")
            if "prompt_mode" in exp_config:
                prompt_mode = exp_config["prompt_mode"]
            if "model" in exp_config:
                model = exp_config["model"]

        dialogue, eval_scores, llm_time, _section_meta = generate_structured_dialogue(clean_text, model=model, duration=duration, prompt_mode=prompt_mode)
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
        err_msg = str(e)[:200]
        if "空响应" in err_msg or "余额" in err_msg:
            err_msg = "AI 服务异常（可能是账户余额不足），请检查 API 密钥配置或联系客服充值"
        return jsonify({"error": err_msg}), 500


@app.route("/api/parse_script", methods=["POST"])
def api_parse_script():
    """Parse user-provided dialogue script from text, file, or image."""
    text = (request.get_json(silent=True) or {}).get("text", "").strip()
    if text:
        script = parse_dialogue(text)
        if not script:
            return jsonify({"error": "未能识别出有效的对话格式，请确保每行以「主持：」或「嘉宾：」开头"}), 400
        return jsonify({"script": script, "source": "text", "total_turns": len(script)})

    if "file" not in request.files:
        return jsonify({"error": "请提供文本内容或上传文件"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "文件名不能为空"}), 400

    from werkzeug.utils import secure_filename
    filename = secure_filename(file.filename)
    ext = Path(filename).suffix.lower()

    try:
        tmp_dir = Path(tempfile.mkdtemp(prefix="boke_script_"))
        tmp_path = tmp_dir / filename
        file.save(str(tmp_path))

        image_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        doc_exts = {".pdf", ".docx", ".txt", ".md"}

        if ext in image_exts:
            import base64
            img_data = tmp_path.read_bytes()
            b64 = base64.b64encode(img_data).decode("utf-8")
            mime = f"image/{ext.lstrip('.')}".replace("jpg", "jpeg")
            ocr_prompt = "请识别图片中的所有文字，原样输出。不要添加任何解释。"
            try:
                ocr_resp = req.post(
                    ZHI_API_BASE,
                    json={
                        "model": "deepseek-v4",
                        "messages": [
                            {"role": "user", "content": [
                                {"type": "text", "text": ocr_prompt},
                                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                            ]},
                        ],
                        "max_tokens": 4096,
                    },
                    headers={"Authorization": f"Bearer {ZHI_API_KEY}", "Content-Type": "application/json"},
                    timeout=60,
                )
                ocr_data = ocr_resp.json()
                extracted = (ocr_data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            except Exception as e:
                return jsonify({"error": f"图片文字识别失败: {str(e)[:100]}"}), 500

            script = parse_dialogue(extracted)
            if not script:
                return jsonify({
                    "error": "图片中未识别出对话格式，请确保证片上包含「主持：」「嘉宾：」格式的对话",
                    "raw_text": extracted[:500],
                }), 400
            return jsonify({"script": script, "source": "image_ocr", "total_turns": len(script), "raw_text": extracted})

        elif ext in doc_exts:
            if ext == ".pdf":
                from PyPDF2 import PdfReader
                reader = PdfReader(str(tmp_path))
                body = "\n".join(p.extract_text() for p in reader.pages if p.extract_text())
            elif ext == ".docx":
                from docx import Document
                doc = Document(str(tmp_path))
                body = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            else:
                encodings = ["utf-8", "gbk", "gb2312", "utf-16"]
                body = None
                for enc in encodings:
                    try:
                        body = tmp_path.read_text(encoding=enc)
                        break
                    except UnicodeDecodeError:
                        continue
                if body is None:
                    return jsonify({"error": "无法识别文件编码"}), 400

            script = parse_dialogue(body.strip())
            if not script:
                return jsonify({"error": "文件中未识别出对话格式，请确保内容以「主持：」「嘉宾：」格式编写"}), 400
            return jsonify({"script": script, "source": "file", "total_turns": len(script)})

        else:
            return jsonify({"error": f"不支持的文件格式: {ext}，请上传图片(PNG/JPG)、PDF、DOCX 或 TXT"}), 400

    finally:
        if tmp_path and tmp_path.parent.exists():
            import shutil
            shutil.rmtree(tmp_path.parent, ignore_errors=True)


@app.route("/api/tts", methods=["POST"])
@_optional_auth
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

    # ── Create a session so this podcast appears in "我的播客" ──
    session_id = str(uuid.uuid4())
    duration = data.get("duration", "free")
    _session_create(session_id, request_id, duration, title, getattr(g, 'user_id', None))
    _session_set(session_id, "full_script", script)
    _session_set(session_id, "voice_map", voice_map)
    _session_set(session_id, "platform", "网页")
    _session_set(session_id, "progress", 50)

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

        # Persist audio — copy to recordings/ stable directory
        audio_path = save_audio_file(audio_path, session_id)

        _session_set(session_id, "full_audio_path", audio_path)
        _session_set(session_id, "tts_time_ms", tts_ms)
        _session_set(session_id, "status", "complete")
        _session_set(session_id, "progress", 100)
        # Compute per-turn timings for chapter markers & transcript sync
        timings = _compute_timings(script)
        _session_set(session_id, "timings", timings)

        write_log({
            "request_id": request_id, "phase": "tts",
            "input_type": input_type, "input_length": input_length,
            "parse_time_ms": parse_time_ms, "llm_time_ms": llm_time_ms,
            "tts_time_ms": tts_ms, "total_time_ms": total_ms,
            "output_length": output_length,
            "success": True, "error_message": None,
            "has_speaker_format": has_speaker, "format_valid": format_valid,
            "session_id": session_id,
            **eval_scores,
            "reuse_flag": 0, "full_play_flag": 0,
        })

        resp = send_file(audio_path, mimetype="audio/mpeg")
        resp.headers["X-Session-Id"] = session_id
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
     "summary":"主持和嘉宾从各自的角度探讨了 AI 对传统教育体系的冲击。嘉宾用自己孩子学校的例子说明课堂已经在变化，主持则从更宏观的视角分析了教育理念需要如何转变。",
     "chapters":[{"t":"01 · 教育的困境","d":"AI 时代的到来让传统教育模式面临前所未有的挑战"},{"t":"02 · 重新定义学习","d":"从知识灌输到能力培养，学习方式的根本转变"},{"t":"03 · 实践建议","d":"如何在 AI 时代重新规划学习路径"}]},
    {"id":"exp_2","title":"2026 年新能源汽车市场趋势：价格战后的新格局","desc":"分析新能源汽车市场的竞争格局变化","tag":"精选","platform":"知乎","icon":"📝","gradient":"linear-gradient(135deg,#FF9F5E15,#FF6B6B15)",
     'summary':'嘉宾开篇就抛出了「价格战打完了，然后呢」的疑问。主持用数据分析了各品牌的生存状况，两人一致认为技术差异化和海外市场是下一阶段的关键。',
     "chapters":[{"t":"01 · 市场回顾","d":"2025 年价格战后的市场格局重塑"},{"t":"02 · 品牌分析","d":"各主要品牌的战略定位和差异化"},{"t":"03 · 未来预测","d":"2026-2027 年的关键趋势和变量"}]},
    {"id":"exp_3","title":"为什么日本半导体产业在过去三十年衰落又崛起？","desc":"日本半导体产业从崛起到衰落再到复兴","tag":"精选","platform":"网页","icon":"🌐","gradient":"linear-gradient(135deg,#5E9EFF15,#34C75915)",
     "summary":"主持从历史角度梳理了日本半导体产业的完整发展脉络。嘉宾则从当下供应链的角度分析了日本在材料领域的不可替代性。",
     "chapters":[{"t":"01 · 辉煌时期","d":"日本半导体在上世纪 80 年代的全球主导地位"},{"t":"02 · 衰落原因","d":"日美贸易摩擦和产业策略失误"},{"t":"03 · 复兴之路","d":"当前日本在半导体材料领域的重新崛起"}]},
    {"id":"exp_4","title":"特斯拉 FSD 入华：自动驾驶的新篇章","desc":"FSD 正式进入中国，对本土企业产生的影响","tag":"热门","platform":"B站","icon":"▶️","gradient":"linear-gradient(135deg,#34C75915,#5E9EFF15)",
     "summary":"嘉宾试驾了搭载 FSD 的车型后兴奋地分享了体验。主持则冷静分析了特斯拉的技术路线和本土化挑战。",
     "chapters":[{"t":"01 · 入华背景","d":"FSD 获批进入中国市场的来龙去脉"},{"t":"02 · 技术对比","d":"特斯拉 vs 华为小鹏的自动驾驶路线差异"},{"t":"03 · 行业影响","d":"FSD 入华对本土企业的竞争压力"}]},
    {"id":"exp_5","title":"SpaceX 星舰第五飞：人类登陆火星的里程碑","desc":"筷子回收技术取得历史性突破","tag":"热门","platform":"B站","icon":"▶️","gradient":"linear-gradient(135deg,#764BA215,#FF6B6B15)",
     "summary":"嘉宾一上来就说“太震撼了”，描述了亲眼看到筷子捕获助推器的画面。主持用通俗的比喻解释了这项技术突破的意义。",
     "chapters":[{"t":"01 · 任务回顾","d":"星舰第五次轨道测试的关键节点"},{"t":"02 · 筷子技术","d":"发射塔捕获助推器的工程技术突破"},{"t":"03 · 火星展望","d":"完全可重复使用火箭对太空探索的意义"}]},
    {"id":"exp_6","title":"DeepSeek 崛起：中国 AI 大模型的新格局","desc":"开源策略和高效训练方法引发行业关注","tag":"精选","platform":"公众号","icon":"📄","gradient":"linear-gradient(135deg,#FF6B6B15,#764BA215)",
     "summary":"嘉宾用“性价比之王”来形容 DeepSeek。主持分析了 DeepSeek 的技术路线和开源策略对行业的影响。",
     "chapters":[{"t":"01 · 技术突破","d":"DeepSeek 高效训练方法的技术创新"},{"t":"02 · 开源策略","d":"开源对 AI 行业竞争格局的影响"},{"t":"03 · 未来展望","d":"算法创新能否持续弥补算力差距"}]},
    {"id":"exp_7","title":"小米 SU7 上市三个月：真实用户体验","desc":"小米首款汽车 SU7 首批用户真实反馈","tag":"精选","platform":"小红书","icon":"📱","gradient":"linear-gradient(135deg,#FF6B6B15,#FFD70015)",
     "summary":"嘉宾分享了朋友提车后的真实体验。主持从产品定义和造车基本功两个维度进行了分析。",
     "chapters":[{"t":"01 · 智能座舱","d":"人车家全生态互联的实际体验"},{"t":"02 · 续航表现","d":"真实续航达成率和充电便利性"},{"t":"03 · 综合评价","d":"小米第一款车的得与失"}]},
    {"id":"exp_8","title":"小红书电商崛起：从种草到拔草","desc":"小红书从内容社区到交易平台的转型","tag":"热门","platform":"小红书","icon":"📱","gradient":"linear-gradient(135deg,#FF9F5E15,#FF6B6B15)",
     "summary":"嘉宾说现在买东西先看小红书。主持分析了这种消费决策路径变化背后的商业逻辑。",
     "chapters":[{"t":"01 · 平台转型","d":"从内容社区到交易平台的演变"},{"t":"02 · 商业模式","d":"买手直播和店铺直播双引擎"},{"t":"03 · 挑战与未来","d":"商业化 vs 社区氛围的平衡"}]},
    {"id":"exp_9","title":"《黑神话：悟空》DLC 前瞻","desc":"游戏科学确认 DLC 正在开发中","tag":"热门","platform":"B站","icon":"▶️","gradient":"linear-gradient(135deg,#764BA215,#FF6B6B15)",
     "summary":"嘉宾作为游戏迷兴奋地聊起了 DLC 的传闻。主持则分析了这款游戏对中国游戏产业的意义。",
     "chapters":[{"t":"01 · 全球成绩","d":"《黑神话》全球销量突破 2000 万份"},{"t":"02 · DLC 内容","d":"火焰山、狮驼岭等新场景展望"},{"t":"03 · 产业影响","d":"中国 3A 游戏的未来之路"}]},
    {"id":"exp_10","title":"比亚迪秦 L DM-i 实测：油耗 2 升时代","desc":"第五代 DM 混动技术首款车型实测","tag":"精选","platform":"知乎","icon":"📝","gradient":"linear-gradient(135deg,#34C75915,#5E9EFF15)",
     "summary":"嘉宾算了一笔账：这车一年能省多少油钱。主持从技术角度解析了 46% 热效率发动机的含金量。",
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
    """Return podcast detail with script, chapters, timings, and eval scores."""
    session = _session_get(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    full_script = session.get("full_script")
    title = session.get("title", "")
    article_title = session.get("article_title", "")
    eval_scores = session.get("eval_scores", {})
    section_metadata = session.get("section_metadata")
    timings = session.get("timings")
    # Build chapters from real section metadata or fall back to simple structure
    chapters = []
    if section_metadata and len(section_metadata) > 1:
        for sec in section_metadata:
            start_time = 0
            end_time = 0
            if timings and sec["turn_start"] < len(timings):
                start_time = timings[sec["turn_start"]]["start"]
                end_time = timings[min(sec["turn_end"] - 1, len(timings) - 1)]["end"]
            chapters.append({
                "id": sec["section_id"],
                "t": f"0{sec['section_id']} · {sec['title']}",
                "d": sec.get("summary", ""),
                "turns": f"{sec['turn_start']+1}-{sec['turn_end']}",
                "start_time": start_time,
                "end_time": end_time,
            })
    elif full_script and len(full_script) > 4:
        total_turns = len(full_script)
        chunk_size = max(1, total_turns // 3)
        chapter_names = [
            ("开场与导入", "主持和嘉宾引入话题"),
            ("核心讨论", f"围绕 {title[:20]} 展开深入讨论") if title else ("核心讨论", "深入分析文章核心观点"),
            ("总结与延伸", "回顾关键 takeaways，延伸思考"),
        ]
        for i, (cn, cd) in enumerate(chapter_names):
            start_turn = i * chunk_size
            end_turn = min((i + 1) * chunk_size, total_turns)
            start_time = timings[start_turn]["start"] if timings and start_turn < len(timings) else 0
            end_time = timings[end_turn - 1]["end"] if timings and end_turn - 1 < len(timings) else 0
            chapters.append({
                "id": i + 1,
                "t": f"0{i+1} · {cn}",
                "d": cd,
                "turns": f"{start_turn+1}-{end_turn}",
                "start_time": start_time,
                "end_time": end_time,
            })
    return jsonify({
        "session_id": session_id,
        "title": title or article_title or "",
        "status": session.get("status", ""),
        "progress": session.get("progress", 0),
        "script": full_script or [],
        "chapters": chapters,
        "timings": timings or [],
        "eval_scores": eval_scores,
        "duration": session.get("duration", "standard"),
        "created_at": session.get("created_at", 0),
    })


@app.route("/api/podcasts", methods=["GET"])
@_optional_auth
def api_podcasts():
    """Return list of completed podcasts, filtered by user if authenticated."""
    items = []
    for s in session_list(("complete", "failed"), user_id=g.user_id):
        items.append({
            "id": s.get("id", ""),
            "title": s.get("title", ""),
            "article_title": s.get("article_title", ""),
            "status": s.get("status", ""),
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


# ── Admin Dashboard (standalone HTML) ──

@app.route("/admin")
def admin_dashboard():
    """Serve standalone admin monitoring dashboard."""
    admin_path = BASE_DIR / "admin.html"
    if admin_path.exists():
        return send_file(str(admin_path), mimetype="text/html")
    return "Admin dashboard not found", 404


# ── Metrics APIs ──

@app.route("/api/metrics/playback_event", methods=["POST"])
def api_metrics_playback_event():
    """Report playback events (turn_start, turn_exit, pause, complete, exit)."""
    data = request.get_json(force=True) or {}
    entry = {
        "session_id": data.get("session_id"),
        "turn_index": data.get("turn_index"),
        "event_type": data.get("event_type"),
        "listen_duration_s": data.get("listen_duration_s"),
        "total_listen_time_s": data.get("total_listen_time_s"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _write_metrics(METRICS_PLAYBACK_PATH, entry)
    return jsonify({"status": "ok"})


@app.route("/api/metrics/dashboard", methods=["GET"])
def api_metrics_dashboard():
    """Aggregate monitoring data for the dashboard."""
    days = int(request.args.get("days", "7"))
    input_metrics = _load_metrics(METRICS_INPUT_PATH, days=days)
    generation_metrics = _load_metrics(METRICS_GENERATION_PATH, days=days)
    playback_metrics = _load_metrics(METRICS_PLAYBACK_PATH, days=days)

    # Input layer
    total_articles = len(input_metrics)
    source_dist = {}
    platform_dist = {}
    article_lengths = []
    parse_failures = 0
    has_native_headers_count = 0
    header_counts = []
    compression_ratios = []
    chunk_counts = []
    split_strategies = {}
    for m in input_metrics:
        src = m.get("input_source", "unknown")
        source_dist[src] = source_dist.get(src, 0) + 1
        plat = m.get("platform", "网页")
        platform_dist[plat] = platform_dist.get(plat, 0) + 1
        if m.get("article_length_chars"):
            article_lengths.append(m["article_length_chars"])
        if not m.get("parse_success"):
            parse_failures += 1
        if m.get("has_native_headers"):
            has_native_headers_count += 1
        if m.get("header_count") is not None:
            header_counts.append(m["header_count"])
        if m.get("extraction_compression_ratio") is not None:
            compression_ratios.append(m["extraction_compression_ratio"])
        if m.get("chunk_count") is not None:
            chunk_counts.append(m["chunk_count"])
        ss = m.get("split_strategy")
        if ss:
            split_strategies[ss] = split_strategies.get(ss, 0) + 1

    # Generation quality
    coverage_vals = [m.get("keyword_coverage") for m in generation_metrics if m.get("keyword_coverage") is not None]
    faith_vals = [m.get("faithfulness") for m in generation_metrics if m.get("faithfulness") is not None]
    role_dist_vals = [m.get("role_distinction") for m in generation_metrics if m.get("role_distinction") is not None]
    format_failures = sum(1 for m in generation_metrics if not m.get("format_valid"))
    model_dist = {}
    prompt_mode_dist = {}
    split_strategy_gen = {}
    output_lengths = []
    expansion_ratios = []
    llm_times = []
    distinct_1_vals = [m.get("distinct_1") for m in generation_metrics if m.get("distinct_1") is not None]
    distinct_2_vals = [m.get("distinct_2") for m in generation_metrics if m.get("distinct_2") is not None]
    content_scores = [m.get("content_accuracy_score") for m in generation_metrics if m.get("content_accuracy_score") is not None]
    colloquial_scores = [m.get("colloquial_score") for m in generation_metrics if m.get("colloquial_score") is not None]
    role_diff_scores = [m.get("role_difference_score") for m in generation_metrics if m.get("role_difference_score") is not None]
    scene_scores = [m.get("scene_fit_score") for m in generation_metrics if m.get("scene_fit_score") is not None]
    speaker_format_count = sum(1 for m in generation_metrics if m.get("has_speaker_format"))
    chunk_count_gen = []
    total_turns_list = []
    for m in generation_metrics:
        model = m.get("model") or "unknown"
        model_dist[model] = model_dist.get(model, 0) + 1
        pm = m.get("prompt_mode") or "unknown"
        prompt_mode_dist[pm] = prompt_mode_dist.get(pm, 0) + 1
        sg = m.get("split_strategy") or "unknown"
        split_strategy_gen[sg] = split_strategy_gen.get(sg, 0) + 1
        if m.get("output_length_chars"):
            output_lengths.append(m["output_length_chars"])
        if m.get("expansion_ratio") is not None:
            expansion_ratios.append(m["expansion_ratio"])
        if m.get("llm_time_ms"):
            llm_times.append(m["llm_time_ms"])
        if m.get("chunk_count") is not None:
            chunk_count_gen.append(m["chunk_count"])
        if m.get("total_turns"):
            total_turns_list.append(m["total_turns"])

    # Text stats (first-tier)
    avg_turn_lengths = [m.get("avg_turn_length") for m in generation_metrics if m.get("avg_turn_length") is not None]
    question_ratios = [m.get("question_ratio") for m in generation_metrics if m.get("question_ratio") is not None]
    exclamation_ratios = [m.get("exclamation_ratio") for m in generation_metrics if m.get("exclamation_ratio") is not None]
    filler_densities = [m.get("filler_density") for m in generation_metrics if m.get("filler_density") is not None]
    pause_densities = [m.get("pause_density") for m in generation_metrics if m.get("pause_density") is not None]
    emotion_tag_rates = [m.get("emotion_tag_rate") for m in generation_metrics if m.get("emotion_tag_rate") is not None]
    role_violation_rates = [m.get("role_violation_rate") for m in generation_metrics if m.get("role_violation_rate") is not None]

    # Q2 score (factual consistency, only present when use_q2=True)
    q2_scores = [m.get("q2_score") for m in generation_metrics if m.get("q2_score") is not None]

    # Second-tier metrics (tier-2 evaluation)
    numeric_hall_vals = [m.get("numeric_hallucination_rate") for m in generation_metrics if m.get("numeric_hallucination_rate") is not None]
    entity_hall_vals = [m.get("entity_hallucination_rate") for m in generation_metrics if m.get("entity_hallucination_rate") is not None]
    omission_vals = [m.get("keyword_omission_rate") for m in generation_metrics if m.get("keyword_omission_rate") is not None]
    coherence_vals = [m.get("coherence_score") for m in generation_metrics if m.get("coherence_score") is not None]
    coherence_std_vals = [m.get("coherence_std") for m in generation_metrics if m.get("coherence_std") is not None]
    oc_vals = [m.get("opening_closing_score") for m in generation_metrics if m.get("opening_closing_score") is not None]
    opening_guest_first_count = sum(1 for m in generation_metrics if m.get("opening_guest_first"))
    closing_host_last_count = sum(1 for m in generation_metrics if m.get("closing_host_last"))
    chunk_transition_vals = [m.get("chunk_transition_score") for m in generation_metrics if m.get("chunk_transition_score") is not None]

    # User actions (replay / regenerate / edit_generate)
    user_actions = _load_metrics(METRICS_USER_ACTION_PATH, days=days)
    user_action_counts = {}
    user_action_unique_sessions = {}
    for m in user_actions:
        at = m.get("action_type", "unknown")
        user_action_counts[at] = user_action_counts.get(at, 0) + 1
        sid = m.get("session_id")
        if sid:
            if at not in user_action_unique_sessions:
                user_action_unique_sessions[at] = set()
            user_action_unique_sessions[at].add(sid)
    total_user_actions = sum(user_action_counts.values())

    # Input layer strategy rates
    single_shot_count = sum(1 for m in input_metrics if m.get("split_strategy") == "single-shot")
    fallback_count = sum(1 for m in input_metrics if m.get("split_strategy") == "chunked-fallback")
    total_with_strategy = max(1, sum(1 for m in input_metrics if m.get("split_strategy")))
    chunk_lengths = []
    for m in input_metrics:
        alen = m.get("article_length_chars")
        ccnt = m.get("chunk_count")
        if alen and ccnt:
            chunk_lengths.append(alen / ccnt)

    def _avg(vals):
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    daily_trend = {}
    for m in generation_metrics:
        ts = m.get("timestamp", "")
        date = ts[:10] if ts else "unknown"
        if date not in daily_trend:
            daily_trend[date] = {"coverage": [], "faithfulness": [], "q2_score": [], "turns": [], "count": 0,
                                 "distinct_1": [], "distinct_2": [], "llm_time": []}
        if m.get("keyword_coverage") is not None:
            daily_trend[date]["coverage"].append(m["keyword_coverage"])
        if m.get("faithfulness") is not None:
            daily_trend[date]["faithfulness"].append(m["faithfulness"])
        if m.get("q2_score") is not None:
            daily_trend[date]["q2_score"].append(m["q2_score"])
        if m.get("total_turns"):
            daily_trend[date]["turns"].append(m["total_turns"])
        if m.get("distinct_1") is not None:
            daily_trend[date]["distinct_1"].append(m["distinct_1"])
        if m.get("distinct_2") is not None:
            daily_trend[date]["distinct_2"].append(m["distinct_2"])
        if m.get("llm_time_ms"):
            daily_trend[date]["llm_time"].append(m["llm_time_ms"])
        daily_trend[date]["count"] += 1

    daily_trend_list = []
    for date, vals in sorted(daily_trend.items()):
        daily_trend_list.append({
            "date": date,
            "coverage": round(sum(vals["coverage"]) / len(vals["coverage"]), 4) if vals["coverage"] else 0,
            "faithfulness": round(sum(vals["faithfulness"]) / len(vals["faithfulness"]), 4) if vals["faithfulness"] else 0,
            "turns": round(sum(vals["turns"]) / len(vals["turns"]), 1) if vals["turns"] else 0,
            "faithfulness": round(sum(vals["faithfulness"]) / len(vals["faithfulness"]), 4) if vals["faithfulness"] else 0,
            "q2_score": round(sum(vals["q2_score"]) / len(vals["q2_score"]), 4) if vals["q2_score"] else 0,
            "distinct_1": round(sum(vals["distinct_1"]) / len(vals["distinct_1"]), 4) if vals["distinct_1"] else 0,
            "distinct_2": round(sum(vals["distinct_2"]) / len(vals["distinct_2"]), 4) if vals["distinct_2"] else 0,
            "avg_llm_time_ms": round(sum(vals["llm_time"]) / len(vals["llm_time"])) if vals["llm_time"] else 0,
        })

    # TTS
    tts_sessions = [m for m in playback_metrics if m.get("phase") == "tts"]
    tts_arranged = [m for m in playback_metrics if m.get("phase") == "tts_arranged"]
    all_tts = tts_sessions + tts_arranged
    tts_failures = sum(1 for m in all_tts if not m.get("success"))
    emotion_dist = {}
    voice_dist = {}
    tts_times = []
    audio_durations = []
    hq_count = 0
    bgm_count = 0
    turn_counts = []
    for m in all_tts:
        for emo, count in (m.get("emotion_distribution") or {}).items():
            emotion_dist[emo] = emotion_dist.get(emo, 0) + count
        vm = m.get("voice_map") or {}
        for speaker, voice_id in vm.items():
            voice_dist[voice_id] = voice_dist.get(voice_id, 0) + 1
        if m.get("tts_time_ms"):
            tts_times.append(m["tts_time_ms"])
        if m.get("audio_duration_s"):
            audio_durations.append(m["audio_duration_s"])
        if m.get("high_quality"):
            hq_count += 1
        if m.get("bg_music"):
            bgm_count += 1
        if m.get("total_turns"):
            turn_counts.append(m["total_turns"])

    # Playback
    turn_events = {}
    session_listen_times = {}
    completions = 0
    total_sessions_playback = 0
    for m in playback_metrics:
        sid = m.get("session_id")
        if m.get("event_type") == "turn_exit" and m.get("turn_index") is not None:
            idx = m["turn_index"]
            if idx not in turn_events:
                turn_events[idx] = {"exit_count": 0, "total_listen": 0}
            turn_events[idx]["exit_count"] += 1
            if m.get("listen_duration_s"):
                turn_events[idx]["total_listen"] += m["listen_duration_s"]
        if sid and m.get("total_listen_time_s"):
            session_listen_times[sid] = max(session_listen_times.get(sid, 0), m["total_listen_time_s"])
        if m.get("event_type") == "complete":
            completions += 1
        if sid:
            total_sessions_playback = max(total_sessions_playback, len(set(session_listen_times.keys())))

    top_exit_turns = sorted(
        [{"turn_index": k, "exit_count": v["exit_count"],
          "avg_listen_duration_s": round(v["total_listen"] / max(1, v["exit_count"]), 2)} for k, v in turn_events.items()],
        key=lambda x: x["exit_count"], reverse=True
    )[:10]

    avg_listen_duration = round(sum(session_listen_times.values()) / max(1, len(session_listen_times)), 1)
    completion_rate = round(completions / max(1, len(session_listen_times)), 4)

    return jsonify({
        "input_layer": {
            "total_articles": total_articles,
            "source_distribution": source_dist,
            "avg_article_length": round(sum(article_lengths) / len(article_lengths)) if article_lengths else 0,
            "parse_failure_rate": round(parse_failures / max(1, total_articles), 4),
            "platform_distribution": platform_dist,
            "has_native_headers_rate": round(has_native_headers_count / max(1, total_articles), 4),
            "avg_header_count": round(sum(header_counts) / len(header_counts), 1) if header_counts else 0,
            "avg_compression_ratio": _avg(compression_ratios),
            "avg_chunk_count": round(sum(chunk_counts) / len(chunk_counts), 1) if chunk_counts else 0,
            "split_strategy_distribution": split_strategies,
            "single_shot_rate": round(single_shot_count / total_with_strategy, 4),
            "fallback_trigger_rate": round(fallback_count / total_with_strategy, 4),
            "avg_chunk_length": round(sum(chunk_lengths) / len(chunk_lengths)) if chunk_lengths else 0,
        },
        "generation_quality": {
            "avg_keyword_coverage": _avg(coverage_vals),
            "avg_faithfulness": _avg(faith_vals),
            "avg_q2_score": _avg(q2_scores),
            "avg_role_distinction": _avg(role_dist_vals),
            "format_failure_rate": round(format_failures / max(1, len(generation_metrics)), 4),
            "daily_trend": daily_trend_list,
            "model_distribution": model_dist,
            "prompt_mode_distribution": prompt_mode_dist,
            "split_strategy_distribution": split_strategy_gen,
            "avg_output_length_chars": round(sum(output_lengths) / len(output_lengths)) if output_lengths else 0,
            "avg_expansion_ratio": _avg(expansion_ratios),
            "avg_llm_time_ms": round(sum(llm_times) / len(llm_times)) if llm_times else 0,
            "avg_distinct_1": _avg(distinct_1_vals),
            "avg_distinct_2": _avg(distinct_2_vals),
            "avg_content_accuracy_score": _avg(content_scores),
            "avg_colloquial_score": _avg(colloquial_scores),
            "avg_role_difference_score": _avg(role_diff_scores),
            "avg_scene_fit_score": _avg(scene_scores),
            "speaker_format_rate": round(speaker_format_count / max(1, len(generation_metrics)), 4),
            "avg_chunk_count": round(sum(chunk_count_gen) / len(chunk_count_gen), 1) if chunk_count_gen else 0,
            "avg_total_turns": round(sum(total_turns_list) / len(total_turns_list), 1) if total_turns_list else 0,
            "avg_turn_length": _avg(avg_turn_lengths),
            "avg_question_ratio": _avg(question_ratios),
            "avg_exclamation_ratio": _avg(exclamation_ratios),
            "avg_filler_density": _avg(filler_densities),
            "avg_pause_density": _avg(pause_densities),
            "avg_emotion_tag_rate": _avg(emotion_tag_rates),
            "avg_role_violation_rate": _avg(role_violation_rates),
            # Second-tier metrics
            "avg_numeric_hallucination_rate": _avg(numeric_hall_vals),
            "avg_entity_hallucination_rate": _avg(entity_hall_vals),
            "avg_keyword_omission_rate": _avg(omission_vals),
            "avg_coherence_score": _avg(coherence_vals),
            "avg_coherence_std": _avg(coherence_std_vals),
            "avg_opening_closing_score": _avg(oc_vals),
            "opening_guest_first_rate": round(opening_guest_first_count / max(1, len(generation_metrics)), 4),
            "closing_host_last_rate": round(closing_host_last_count / max(1, len(generation_metrics)), 4),
            "avg_chunk_transition_score": _avg(chunk_transition_vals),
        },
        "tts": {
            "total_sessions": len(all_tts),
            "failure_rate": round(tts_failures / max(1, len(all_tts)), 4),
            "emotion_distribution": emotion_dist,
            "voice_distribution": voice_dist,
            "avg_tts_time_ms": round(sum(tts_times) / len(tts_times)) if tts_times else 0,
            "avg_audio_duration_s": round(sum(audio_durations) / len(audio_durations), 1) if audio_durations else 0,
            "high_quality_rate": round(hq_count / max(1, len(all_tts)), 4),
            "bg_music_rate": round(bgm_count / max(1, len(all_tts)), 4),
            "avg_total_turns": round(sum(turn_counts) / len(turn_counts), 1) if turn_counts else 0,
        },
        "playback": {
            "avg_completion_rate": completion_rate,
            "avg_listen_duration_s": avg_listen_duration,
            "top_exit_turns": top_exit_turns,
            "total_sessions": len(session_listen_times),
        },
        "user_actions": {
            "total": total_user_actions,
            "replay": user_action_counts.get("replay", 0),
            "regenerate": user_action_counts.get("regenerate", 0),
            "edit_generate": user_action_counts.get("edit_generate", 0),
        },
    })


@app.route("/api/metrics/user_action", methods=["POST"])
def api_metrics_user_action():
    """Report user actions: replay, regenerate, edit_generate."""
    data = request.get_json(force=True) or {}
    entry = {
        "session_id": data.get("session_id"),
        "action_type": data.get("action_type"),  # replay | regenerate | edit_generate
        "article_title": data.get("article_title", ""),
        "platform": data.get("platform", ""),
        "input_type": data.get("input_type", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _write_metrics(METRICS_USER_ACTION_PATH, entry)
    return jsonify({"status": "ok"})


# ── API 用量统计 ──

@app.route("/api/usage/models", methods=["GET"])
def api_usage_models():
    """返回可用模型列表（含标签、厂商、定价信息）。"""
    models = []
    for key, meta in MODEL_MAP.items():
        prices = MODEL_PRICES.get(key, {"input": 0, "output": 0})
        models.append({
            "id": key,
            "label": meta["label"],
            "provider": meta["provider"],
            "desc": meta["desc"],
            "price_input_per_m": prices["input"],
            "price_output_per_m": prices["output"],
        })
    return jsonify({"models": models})


@app.route("/api/usage/stats", methods=["GET"])
def api_usage_stats():
    """Aggregate API usage from JSONL log."""
    days = int(request.args.get("days", "30"))
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    total_requests = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_cost = 0.0
    model_stats = {}
    daily_stats = {}

    if not os.path.exists(USAGE_LOG_PATH):
        return jsonify({"total_requests": 0, "total_cost": 0, "model_stats": {}, "daily_stats": [], "days": days})

    with open(USAGE_LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = entry.get("timestamp", "")
            if ts < cutoff:
                continue

            total_requests += 1
            pt = entry.get("prompt_tokens", 0)
            ct = entry.get("completion_tokens", 0)
            cost = entry.get("cost_usd", 0)
            total_prompt_tokens += pt
            total_completion_tokens += ct
            total_cost += cost

            model = entry.get("model", "unknown")
            if model not in model_stats:
                model_stats[model] = {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0}
            model_stats[model]["requests"] += 1
            model_stats[model]["prompt_tokens"] += pt
            model_stats[model]["completion_tokens"] += ct
            model_stats[model]["cost"] += cost

            day = ts[:10]  # YYYY-MM-DD
            if day not in daily_stats:
                daily_stats[day] = {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0}
            daily_stats[day]["requests"] += 1
            daily_stats[day]["prompt_tokens"] += pt
            daily_stats[day]["completion_tokens"] += ct
            daily_stats[day]["cost"] += cost

    # Round costs
    for m in model_stats.values():
        m["cost"] = round(m["cost"], 6)
    for d in daily_stats.values():
        d["cost"] = round(d["cost"], 6)

    return jsonify({
        "total_requests": total_requests,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_cost": round(total_cost, 6),
        "model_stats": model_stats,
        "daily_stats": [{"date": k, **v} for k, v in sorted(daily_stats.items())],
        "days": days,
    })


@app.route("/api/metrics/heatmap/<session_id>", methods=["GET"])
def api_metrics_heatmap(session_id: str):
    """Return per-turn playback stats for a single session."""
    playback_metrics = _load_metrics(METRICS_PLAYBACK_PATH, days=30)
    session_events = [m for m in playback_metrics if m.get("session_id") == session_id]

    session = _session_get(session_id)
    script = session.get("full_script", []) if session else []

    turn_stats = {}
    for m in session_events:
        idx = m.get("turn_index")
        if idx is None:
            continue
        if idx not in turn_stats:
            turn_stats[idx] = {"listen_count": 0, "exit_count": 0, "total_listen": 0}
        if m.get("event_type") == "turn_start":
            turn_stats[idx]["listen_count"] += 1
        elif m.get("event_type") == "turn_exit":
            turn_stats[idx]["exit_count"] += 1
            if m.get("listen_duration_s"):
                turn_stats[idx]["total_listen"] += m["listen_duration_s"]

    turns = []
    for i, turn in enumerate(script):
        stats = turn_stats.get(i, {"listen_count": 0, "exit_count": 0, "total_listen": 0})
        exits = stats["exit_count"]
        turns.append({
            "index": i,
            "speaker": turn.get("speaker", ""),
            "text": turn.get("text", "")[:60],
            "listen_count": stats["listen_count"],
            "exit_count": exits,
            "avg_listen_duration_s": round(stats["total_listen"] / max(1, exits), 2) if exits > 0 else 0,
        })

    return jsonify({
        "session_id": session_id,
        "total_turns": len(script),
        "turns": turns,
    })


# ── Significance Testing (no external deps) ──

def _normal_cdf(x: float) -> float:
    """Standard normal CDF using math.erf (built-in)."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def _z_test_proportions(count1: int, n1: int, count2: int, n2: int) -> dict:
    """Two-proportion z-test. Returns {z, p_value, significant}."""
    if n1 == 0 or n2 == 0:
        return {"z": 0, "p_value": 1.0, "significant": False}
    p1 = count1 / n1
    p2 = count2 / n2
    p_pool = (count1 + count2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1/n1 + 1/n2))
    if se == 0:
        return {"z": 0, "p_value": 1.0, "significant": False}
    z = (p1 - p2) / se
    p_value = 2 * (1 - _normal_cdf(abs(z)))
    return {"z": round(z, 4), "p_value": round(p_value, 4), "significant": p_value < 0.05}

def _t_test_independent(mean1: float, var1: float, n1: int, mean2: float, var2: float, n2: int) -> dict:
    """Welch's t-test for independent samples. Returns {t, p_value, significant}."""
    if n1 < 2 or n2 < 2:
        return {"t": 0, "p_value": 1.0, "significant": False}
    se = math.sqrt(var1/n1 + var2/n2)
    if se == 0:
        return {"t": 0, "p_value": 1.0, "significant": False}
    t = (mean1 - mean2) / se
    num = (var1/n1 + var2/n2)**2
    den = (var1/n1)**2/(n1-1) + (var2/n2)**2/(n2-1)
    df = num / den if den > 0 else min(n1, n2) - 1
    p_value = 2 * (1 - _normal_cdf(abs(t)))
    return {"t": round(t, 4), "df": round(df, 2), "p_value": round(p_value, 4), "significant": p_value < 0.05}


# ── Experiments API ──

def _load_experiments() -> list[dict]:
    if not EXPERIMENTS_PATH.exists():
        return []
    experiments = []
    with open(EXPERIMENTS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    experiments.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return experiments

def _save_experiments(experiments: list[dict]):
    with open(EXPERIMENTS_PATH, "w", encoding="utf-8") as f:
        for e in experiments:
            f.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")

def _load_running_experiments() -> list[dict]:
    return [e for e in _load_experiments() if e.get("status") == "running"]

def _record_assignment(request_id: str, experiment_id: str, variant_name: str, input_length: int):
    entry = {
        "request_id": request_id,
        "experiment_id": experiment_id,
        "variant_name": variant_name,
        "input_length": input_length,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _write_metrics(EXP_ASSIGNMENTS_PATH, entry)

import hashlib

def _assign_experiment(request_id: str, input_length: int) -> dict | None:
    """Check running experiments and assign variant. Returns config override or None."""
    experiments = _load_running_experiments()
    for exp in experiments:
        hash_val = int(hashlib.md5(f"{exp['id']}:{request_id}".encode()).hexdigest(), 16)
        total_weight = sum(v["weight"] for v in exp["variants"])
        threshold = (hash_val % 1000) / 1000 * total_weight
        cumsum = 0
        for variant in exp["variants"]:
            cumsum += variant["weight"]
            if threshold <= cumsum:
                _record_assignment(request_id, exp["id"], variant["name"], input_length)
                return variant["config"]
    return None


@app.route("/api/experiments", methods=["GET", "POST"])
def api_experiments():
    if request.method == "GET":
        return jsonify({"experiments": _load_experiments()})

    data = request.get_json(force=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "需要实验名称"}), 400
    exp = {
        "id": f"exp_{uuid.uuid4().hex[:8]}",
        "name": name,
        "description": data.get("description", ""),
        "status": data.get("status", "running"),
        "start_date": data.get("start_date", datetime.now(timezone.utc).isoformat()[:10]),
        "end_date": data.get("end_date"),
        "traffic_ratio": data.get("traffic_ratio", 0.5),
        "variants": data.get("variants", []),
        "target_metrics": data.get("target_metrics", []),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    experiments = _load_experiments()
    experiments.append(exp)
    _save_experiments(experiments)
    return jsonify({"experiment": exp}), 201


@app.route("/api/experiments/<exp_id>/results", methods=["GET"])
def api_experiment_results(exp_id: str):
    """Aggregate experiment results with significance testing."""
    experiments = _load_experiments()
    exp = next((e for e in experiments if e.get("id") == exp_id), None)
    if not exp:
        return jsonify({"error": "Experiment not found"}), 404

    assignments = []
    if EXP_ASSIGNMENTS_PATH.exists():
        with open(EXP_ASSIGNMENTS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        a = json.loads(line)
                        if a.get("experiment_id") == exp_id:
                            assignments.append(a)
                    except json.JSONDecodeError:
                        pass

    generation_metrics = _load_metrics(METRICS_GENERATION_PATH, days=30)

    # Group metrics by variant via request_id matching
    variant_data = {v["name"]: {"faithfulness": [], "keyword_coverage": [],
                                "distinct_1": [], "distinct_2": [],
                                "turns": []}
                    for v in exp.get("variants", [])}

    for a in assignments:
        vn = a.get("variant_name")
        if vn not in variant_data:
            continue
        rid = a.get("request_id", "")
        for m in generation_metrics:
            if m.get("request_id") == rid:
                if m.get("faithfulness") is not None:
                    variant_data[vn]["faithfulness"].append(m["faithfulness"])
                if m.get("keyword_coverage") is not None:
                    variant_data[vn]["keyword_coverage"].append(m["keyword_coverage"])
                if m.get("distinct_1") is not None:
                    variant_data[vn]["distinct_1"].append(m["distinct_1"])
                if m.get("distinct_2") is not None:
                    variant_data[vn]["distinct_2"].append(m["distinct_2"])
                if m.get("total_turns"):
                    variant_data[vn]["turns"].append(m["total_turns"])
                break

    def _avg(vals):
        return sum(vals) / len(vals) if vals else 0.0
    def _var(vals):
        if len(vals) < 2:
            return 0.0
        a = _avg(vals)
        return sum((x - a) ** 2 for x in vals) / (len(vals) - 1)

    variant_stats = {}
    for vn, data in variant_data.items():
        variant_stats[vn] = {
            "sample_size": len(data.get("faithfulness", [])),
            "avg_faithfulness": round(_avg(data["faithfulness"]), 4),
            "avg_coverage": round(_avg(data["keyword_coverage"]), 4),
            "avg_distinct_1": round(_avg(data["distinct_1"]), 4),
            "avg_distinct_2": round(_avg(data["distinct_2"]), 4),
            "avg_turns": round(_avg(data["turns"]), 1),
        }

    # Significance tests (each treatment vs first variant as control)
    variants = exp.get("variants", [])
    significant_diffs = []
    if len(variants) >= 2:
        control_name = variants[0]["name"]
        control = variant_data.get(control_name)
        if control and len(control.get("faithfulness", [])) >= 2:
            for v in variants[1:]:
                treatment = variant_data.get(v["name"])
                if not treatment or len(treatment.get("faithfulness", [])) < 2:
                    continue
                for metric in ["faithfulness", "distinct_1"]:
                    cv = control.get(metric, [])
                    tv = treatment.get(metric, [])
                    if len(cv) < 2 or len(tv) < 2:
                        continue
                    t_res = _t_test_independent(_avg(cv), _var(cv), len(cv), _avg(tv), _var(tv), len(tv))
                    lift = (_avg(tv) - _avg(cv)) / max(0.001, _avg(cv))
                    significant_diffs.append({
                        "metric": metric,
                        "control_value": round(_avg(cv), 4),
                        "treatment_value": round(_avg(tv), 4),
                        "lift": f"+{lift*100:.1f}%" if lift >= 0 else f"{lift*100:.1f}%",
                        "p_value": t_res["p_value"],
                        "significant": t_res["significant"],
                    })

    return jsonify({
        "experiment_id": exp_id,
        "variant_stats": variant_stats,
        "significant_diffs": significant_diffs,
    })


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
init_db()
migrate_from_json()

# ── SPA catch-all: serve index.html for any non-API, non-asset route ──
@app.route("/<path:path>")
def _spa_fallback(path):
    # Only catch non-API, non-asset routes
    if path.startswith("api/") or path.startswith("assets/"):
        return jsonify({"error": "Not found"}), 404
    return send_from_directory(FRONTEND_DIR, "index.html")


# ── Error Handlers (return JSON, not HTML, so Vite proxy doesn't choke) ──
@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(405)
@app.errorhandler(500)
def _json_error(err):
    code = getattr(err, "code", 500)
    msg = getattr(err, "description", str(err))
    logger.error(f"HTTP {code}: {msg}")
    return jsonify({"error": msg}), code

@app.errorhandler(Exception)
def _catchall_error(err):
    logger.exception(f"Unhandled exception: {err}")
    return jsonify({"error": str(err) or "服务器内部错误"}), 500

if __name__ == "__main__":
    cleanup_thread = threading.Thread(target=_session_cleanup_loop, daemon=True)
    cleanup_thread.start()
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") == "development"
    app.run(debug=debug, host="0.0.0.0", port=port)
