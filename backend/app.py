import os, re, json, uuid, asyncio, tempfile, shutil, time, logging, threading
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
import edge_tts
from pydub import AudioSegment

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
FETCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
VOICE_MAP = {"小羊": "zh-CN-YunxiNeural", "小姜": "zh-CN-XiaoxiaoNeural"}

client = anthropic.Anthropic(api_key=ZHI_API_KEY or "dummy", base_url=ZHI_BASE_URL)

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

def _call_ai(system: str, content: str) -> str:
    resp = client.messages.create(
        model=ZHI_MODEL, max_tokens=4096,
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

async def _tts_one(text: str, voice: str, path: str):
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

    combined = AudioSegment.empty()
    for sf in segments:
        combined += AudioSegment.from_file(sf, format="mp3")
        os.unlink(sf)

    out_path = tmp_dir / "podcast.mp3"
    combined.export(str(out_path), format="mp3")
    logger.info(f"TTS done: {out_path} ({len(combined)/1000:.1f}s)")
    return str(out_path)

# ── TTFA Streaming Generation ──

SESSION_TIMEOUT = 1800  # 30 minutes
SESSION_CLEANUP_INTERVAL = 300  # 5 minutes

_sessions: dict[str, dict] = {}
_session_lock = threading.Lock()

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
    combined = AudioSegment.empty()
    for sf in segments:
        combined += AudioSegment.from_file(sf, format="mp3")
        os.unlink(sf)
    out_path = tmp_dir / f"{tag}.mp3"
    combined.export(str(out_path), format="mp3")
    return str(out_path)


def _build_continuation_prompt(opening_script: list[dict]) -> str:
    """Format opening dialogue as context for STEP2 to continue from."""
    return "\n".join(f"{d['speaker']}：{d['text']}" for d in opening_script)


def _background_full_generation(session_id: str, url: str, text: str,
                                 duration: str, opening_script: list[dict]):
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

        # STEP1: key points
        t1 = time.time()
        key_points_raw = _call_ai(STEP1_SYSTEM, f"请分析以下文章的核心观点：\n\n{clean_text}")
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
        dialogue_raw = _call_ai(STEP2_SYSTEM, step2_prompt)
        llm_time = int((time.time() - t1) * 1000)
        _session_set(session_id, "llm_time_ms", llm_time)
        _session_set(session_id, "progress", 70)

        full_dialogue = parse_dialogue(dialogue_raw)
        if not full_dialogue:
            raise ValueError("Failed to parse full dialogue")
        logger.info(f"[bg] Full dialogue: {len(full_dialogue)} turns ({llm_time}ms)")

        complete_dialogue = opening_script + full_dialogue
        _session_set(session_id, "full_script", complete_dialogue)
        _session_set(session_id, "progress", 75)

        # Self-evaluation
        eval_scores = evaluate_dialogue(clean_text, complete_dialogue)
        _session_set(session_id, "eval_scores", eval_scores)
        _session_set(session_id, "progress", 80)

        # TTS full
        t2 = time.time()
        audio_path = tts_script(complete_dialogue)
        tts_ms = int((time.time() - t2) * 1000)
        _session_set(session_id, "tts_time_ms", tts_ms)
        _session_set(session_id, "full_audio_path", audio_path)
        _session_set(session_id, "status", "complete")
        _session_set(session_id, "progress", 100)
        logger.info(f"[bg] Full generation complete for session {session_id}")

    except Exception as e:
        logger.error(f"[bg] Full generation failed: {e}", exc_info=True)
        _session_set(session_id, "status", "failed")
        _session_set(session_id, "error", str(e)[:200])
        _session_set(session_id, "progress", 0)


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
    session_id = str(uuid.uuid4())
    t0 = time.time()

    if not url and not text:
        return jsonify({"error": "请提供 url 或 text"}), 400
    if not ZHI_API_KEY:
        return jsonify({"error": "服务端未配置 API 密钥"}), 500

    try:
        # Quick title extraction
        title = _quick_title(url) if url else text[:80].strip()
        if not title:
            title = "未知话题"
        _session_create(session_id, request_id, duration, title)

        # Generate opening from title only (~5s)
        opening_script = generate_opening(title)
        _session_set(session_id, "opening_script", opening_script)
        _session_set(session_id, "progress", 30)

        # TTS opening (~2s)
        opening_audio_path = _tts_script_segment(opening_script, f"opening_{session_id[:8]}")
        _session_set(session_id, "opening_audio_path", opening_audio_path)
        _session_set(session_id, "status", "opening_ready")
        _session_set(session_id, "progress", 40)

        ttfa_ms = int((time.time() - t0) * 1000)
        logger.info(f"TTFA: {ttfa_ms}ms for session {session_id}")

        # Background full generation
        thread = threading.Thread(
            target=_background_full_generation,
            args=(session_id, url, text, duration, opening_script),
            daemon=True,
        )
        thread.start()

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
        AudioSegment.converter = shutil.which("ffmpeg") or "ffmpeg"
        AudioSegment.silent(duration=100)
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

if __name__ == "__main__":
    cleanup_thread = threading.Thread(target=_session_cleanup_loop, daemon=True)
    cleanup_thread.start()
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") == "development"
    app.run(debug=debug, host="0.0.0.0", port=port)
