# -*- coding: utf-8 -*-
"""
TTS Engine: Fish Audio API 封装
- 支持默认内置音色（不传 reference）
- 支持声线克隆（传 reference_audio 路径）
- SSML 清洗 + Fish Speech 情感标签映射
- 音频拼接输出

用法：
    from tts_engine import generate_podcast
    generate_podcast(script, output_path="podcast.mp3")
"""
import os
import re
import shutil
import tempfile
import subprocess
import base64
import requests
from pathlib import Path

# ── 配置 ──
API_KEY = os.environ.get("FISH_API_KEY", "6797c57bffe4459dbfad51b01e20ab65")
API_URL = os.environ.get("FISH_API_URL", "https://api.fish.audio/v1/tts")
OUTPUT_DIR = Path(__file__).parent / "benchmark_output"

# ── 成本监控 ──
_tts_stats = {
    "total_calls": 0,
    "total_chars": 0,
    "total_success": 0,
    "total_fail": 0,
    "total_cost_usd": 0.0,   # 估算成本（按 $10/1M chars = $0.00001/char）
}


def _estimate_cost(char_count: int) -> float:
    """估算 Fish Audio TTS 成本（USD）。基于官方约 $10/百万字符。"""
    return char_count * 0.00001


def get_fish_balance() -> dict:
    """查询 Fish Audio 账户余额和套餐信息。"""
    if not API_KEY:
        return {"error": "FISH_API_KEY 未设置"}
    headers = {"Authorization": f"Bearer {API_KEY}"}
    try:
        # API Credit（美元余额）
        resp_credit = requests.get(
            "https://api.fish.audio/wallet/self/api-credit",
            headers=headers, timeout=10
        )
        credit_data = resp_credit.json() if resp_credit.status_code == 200 else {}
        # Package（套餐额度）
        resp_pkg = requests.get(
            "https://api.fish.audio/wallet/self/package",
            headers=headers, timeout=10
        )
        pkg_data = resp_pkg.json() if resp_pkg.status_code == 200 else {}
        return {
            "credit_usd": float(credit_data.get("credit", 0)),
            "package_balance": pkg_data.get("balance", 0),
            "package_total": pkg_data.get("total", 0),
            "package_type": pkg_data.get("type", "unknown"),
        }
    except Exception as e:
        return {"error": str(e)}


def _check_balance_warning():
    """余额不足时打印警告。"""
    try:
        bal = get_fish_balance()
        credit = bal.get("credit_usd", 0)
        if isinstance(credit, (int, float)) and credit < 0.1:
            print(f"[FishTTS] Warning: 余额不足 (${credit:.4f})，请及时充值")
    except Exception:
        pass

# 情绪映射：播刻情绪 / 主持预设 → Fish Speech 自然语言标签
# 支持 5 种核心标签 + 自由形式（不在表中的标签直接透传）
_EMOTION_MAP = {
    # 播客场景核心 5 种
    "正常": None,
    "兴奋": "excited",
    "磁性": "whispering",
    "放慢": "speaking slowly",
    "悲伤": "sad",
    # 兼容旧标签
    "平静": None,
    "疑问": None,
    "沉思": "speaking slowly",
    # 默认主持预设（兼容旧数据）
    "标准": None,
    "点评": None,
    "青年": "excited",
}

# 语速倍数（Fish Audio API prosody.speed 参数）
# 底线 0.95：避免过于拖沓，保持播客伴随式收听的节奏感
_EMOTION_SPEED = {
    # 核心 5 种
    "正常": 1.0,
    "兴奋": 1.1,
    "磁性": 1.0,      # 磁性是音色特质，不降速
    "放慢": 0.95,     # 仅轻微放慢，避免拖沓
    "悲伤": 0.95,     # 低沉但不拖沓
    # 兼容旧标签
    "平静": 1.0,
    "疑问": 1.0,
    "沉思": 0.95,     # 思考感，不降太多
    # 默认主持预设
    "标准": 1.0,
    "点评": 1.05,
    "青年": 1.1,
}


def _ensure_api_key():
    if not API_KEY:
        raise RuntimeError("环境变量 FISH_API_KEY 未设置")


def clean_ssml(text: str) -> str:
    """去掉所有 SSML 标签，返回纯文本。"""
    # 去掉 <break .../>
    text = re.sub(r'<break\s+[^>]*/?>', '', text)
    # 去掉 <emphasis>...</emphasis>
    text = re.sub(r'</?emphasis[^>]*>', '', text)
    # 去掉 <prosody ...>...</prosody>
    text = re.sub(r'</?prosody[^>]*>', '', text)
    # 去掉 <say-as ...>...</say-as>
    text = re.sub(r'</?say-as[^>]*>', '', text)
    # 去掉 <speak ...> 和 </speak>
    text = re.sub(r'</?speak[^>]*>', '', text)
    # 去掉 <voice ...> 和 </voice>
    text = re.sub(r'</?voice[^>]*>', '', text)
    # 去掉自定义节奏标记
    text = text.replace('[停顿]', '，')
    text = re.sub(r'\[轻声\](.+?)\[/轻声\]', r'\1', text)
    return text.strip()


def _polish_text(text: str) -> str:
    """Fish Audio 文本润色：断长句、清理连续标点。"""
    # 清理连续逗号/句号
    text = re.sub(r'，{2,}', '，', text)
    text = re.sub(r'。{2,}', '。', text)
    text = re.sub(r'，。', '。', text)
    # 超长句（>35字无标点）在中间插入逗号，帮助 Fish Audio 自然停顿
    # 在常见断句位置插入逗号："是""的""了"之后
    if len(text) > 35 and text.count('，') < 2:
        text = re.sub(r'(是|的|了)([^，。！？；])', r'\1，\2', text, count=1)
    return text.strip()


def emotion_to_fish_tag(emotion: str | None) -> str | None:
    """将播刻情绪标签转为 Fish Speech 自然语言标签。
    支持 5 种核心标签 + 自由形式（不在表中的标签直接透传）。
    """
    if not emotion:
        return None
    mapped = _EMOTION_MAP.get(emotion)
    if mapped is not None:
        return mapped
    # 自由形式：标签不在预定义表中，直接透传（如 [speaking softly]）
    return emotion


def _inject_emotion_tag(text: str, emotion: str | None) -> str:
    """在文本开头注入 Fish Speech 情感标签。"""
    tag = emotion_to_fish_tag(emotion)
    if tag:
        return f"[{tag}] {text}"
    return text


def synthesize_turn(
    text: str,
    output_path: str,
    reference_audio_path: str | None = None,
    reference_id: str | None = None,
    speed: float = 1.0,
) -> bool:
    """调用 Fish Audio API 合成单句语音。"""
    _ensure_api_key()

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "model": "s2-pro",
    }

    payload = {
        "text": text,
        "format": "mp3",
        "sample_rate": 44100,
        "temperature": 0.3,
        "top_p": 0.7,
        "prosody": {"speed": speed, "volume": 0, "normalize_loudness": True},
    }

    if reference_id:
        payload["reference_id"] = reference_id
    elif reference_audio_path and Path(reference_audio_path).exists():
        audio_bytes = Path(reference_audio_path).read_bytes()
        payload["reference_audio"] = base64.b64encode(audio_bytes).decode("utf-8")

    try:
        _tts_stats["total_calls"] += 1
        _tts_stats["total_chars"] += len(text)
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=120)
        if resp.status_code == 200:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(resp.content)
            _tts_stats["total_success"] += 1
            _tts_stats["total_cost_usd"] += _estimate_cost(len(text))
            return True
        else:
            print(f"[FishTTS] Error {resp.status_code}: {resp.text[:200]}")
            _tts_stats["total_fail"] += 1
            return False
    except Exception as e:
        print(f"[FishTTS] Exception: {e}")
        _tts_stats["total_fail"] += 1
        return False


def _generate_silence(duration: float, path: str):
    """生成静音片段（WAV 格式）。"""
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    subprocess.run(
        [
            ffmpeg, "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-t", str(duration), "-acodec", "pcm_s16le", "-ar", "24000", "-ac", "1",
            path,
        ],
        check=True, capture_output=True,
    )


def _generate_breath(path: str):
    """生成短促的呼吸声（模拟真实对话中的吸气）。"""
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    # 用快速衰减的正弦波模拟吸气声，低频+轻微噪声
    subprocess.run(
        [
            ffmpeg, "-y", "-f", "lavfi",
            "-i", "aevalsrc=0.25*sin(180*2*PI*t)*exp(-t*10)+0.05*random(0):s=24000",
            "-t", "0.25", "-af", "lowpass=f=400,afade=t=out:st=0.15:d=0.1",
            "-acodec", "pcm_s16le", "-ar", "24000", "-ac", "1",
            path,
        ],
        check=True, capture_output=True,
    )


def _generate_room_tone(duration: float, path: str):
    """生成轻微的环境底噪（模拟录音室/房间的 subtle noise floor）。"""
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    subprocess.run(
        [
            ffmpeg, "-y", "-f", "lavfi",
            "-i", "anoisesrc=a=0.0008:c=pink:r=48000",
            "-t", str(duration + 2),
            "-af", "lowpass=f=2000,afade=t=in:st=0:d=0.5,afade=t=out:st={}:d=1".format(duration),
            "-acodec", "pcm_s16le", "-ar", "24000", "-ac", "1",
            path,
        ],
        check=True, capture_output=True,
    )


def _merge_consecutive_turns(script: list[dict]) -> list[dict]:
    """合并连续同 speaker 且同 emotion 的段落，提升韵律连贯性。"""
    if not script:
        return []
    merged = []
    current = {
        "speaker": script[0].get("speaker", "主持"),
        "text": script[0].get("text", ""),
        "emotion": script[0].get("emotion"),
    }
    for turn in script[1:]:
        speaker = turn.get("speaker", "主持")
        text = turn.get("text", "")
        emotion = turn.get("emotion")
        if speaker == current["speaker"] and emotion == current["emotion"]:
            sep = ""
            if current["text"] and not current["text"].endswith(("。", "？", "！", "…", ",", "，", ":", "：")):
                sep = "。"
            current["text"] = current["text"] + sep + text
        else:
            merged.append(current)
            current = {"speaker": speaker, "text": text, "emotion": emotion}
    merged.append(current)
    return merged


def _compute_pause(text: str) -> float:
    """根据文本结尾计算停顿时长（已针对 Fish Audio 优化缩短）。"""
    t = text.strip()
    if not t:
        return 0.2
    if t[-1] in "？？" or t.endswith(("吗", "呢", "吧", "么", "如何", "为什么", "什么", "多少")):
        return 0.55
    if t[-1] in "！！":
        return 0.35
    if any(t.endswith(w) for w in ["总之", "所以", "那么", "接下来", "最后", "好了", "你看", "对吧", "对吗", "嗯", "啊"]):
        return 0.45
    if t[-1] in "。．.":
        return 0.3
    return 0.2


def concat_podcast(segments: list[str], output_path: str):
    """用 ffmpeg concat 拼接多段音频。"""
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    tmp_dir = Path(output_path).parent
    list_file = tmp_dir / "_concat_list.txt"
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


def _mix_room_tone(input_path: str, output_path: str):
    """为音频叠加轻微环境底噪，增加真实录音感。"""
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    tmp_dir = Path(output_path).parent
    # 获取输入音频时长
    try:
        dur_resp = subprocess.run(
            [ffmpeg, "-i", input_path, "-f", "null", "-"],
            capture_output=True, text=True,
        )
        # 从 stderr 解析时长
        m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", dur_resp.stderr)
        if m:
            h, mi, s = m.groups()
            duration = int(h) * 3600 + int(mi) * 60 + float(s)
        else:
            duration = 0
    except Exception:
        duration = 0

    if duration <= 0:
        shutil.copy(input_path, output_path)
        return

    room_path = tmp_dir / "_room_tone.wav"
    _generate_room_tone(duration, str(room_path))

    subprocess.run(
        [
            ffmpeg, "-y", "-i", input_path, "-i", str(room_path),
            "-filter_complex",
            "[0:a]volume=1.0[a0];[1:a]volume=1.0[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[a]",
            "-map", "[a]", "-acodec", "libmp3lame", "-q:a", "2", output_path,
        ],
        check=True, capture_output=True,
    )


def generate_podcast(
    script: list[dict],
    output_path: str | None = None,
    male_ref: str | None = None,
    female_ref: str | None = None,
    male_ref_id: str | None = None,
    female_ref_id: str | None = None,
    enable_room_tone: bool = True,
) -> str:
    """
    生成完整播客音频（含段落合并、呼吸声、环境底噪）。

    Args:
        script: 对话脚本，每项为 {"speaker": "主持"/"嘉宾", "text": "...", "emotion": "平静"/"兴奋"/...}
        output_path: 输出路径，默认 benchmark_output/fish_podcast.mp3
        male_ref: 主持参考音频路径（已弃用，优先使用 male_ref_id）
        female_ref: 嘉宾参考音频路径（已弃用，优先使用 female_ref_id）
        male_ref_id: 主持 Fish Audio Voice Model ID（推荐）
        female_ref_id: 嘉宾 Fish Audio Voice Model ID（推荐）
        enable_room_tone: 是否叠加环境底噪（默认 True）

    Returns:
        输出文件路径
    """
    _ensure_api_key()
    _check_balance_warning()
    out_path = Path(output_path) if output_path else OUTPUT_DIR / "fish_podcast.mp3"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_dir = Path(tempfile.mkdtemp(prefix="fish_"))
    segments = []
    call_chars = 0

    # Phase 2: 合并连续同 speaker 同 emotion 的段落
    merged_script = _merge_consecutive_turns(script)
    print(f"[FishTTS] Merged {len(script)} turns into {len(merged_script)} segments")

    for i, item in enumerate(merged_script):
        speaker = item.get("speaker", "主持")
        text = item.get("text", "")
        emotion = item.get("emotion")
        call_chars += len(text)

        # 1. 清洗 SSML
        text = clean_ssml(text)
        # 2. 文本润色（断长句、清理标点）
        text = _polish_text(text)
        # 3. 注入情感标签
        text = _inject_emotion_tag(text, emotion)

        # 4. 选择参考音频/ID 和语速
        ref = male_ref if speaker == "主持" else female_ref
        ref_id = male_ref_id if speaker == "主持" else female_ref_id
        speed = _EMOTION_SPEED.get(emotion, 1.0)

        # 5. 拆分超长文本（Fish Audio 单条建议不超过 500 字）
        MAX_CHUNK = 500
        if len(text) > MAX_CHUNK:
            chunks = []
            start = 0
            while start < len(text):
                end = start + MAX_CHUNK
                if end < len(text):
                    # 找最近的句号或逗号
                    for punct in "。，！？；":
                        p = text.rfind(punct, start, end)
                        if p != -1:
                            end = p + 1
                            break
                chunks.append(text[start:end])
                start = end
        else:
            chunks = [text]

        for cidx, chunk in enumerate(chunks):
            seg_path = tmp_dir / f"seg_{i:04d}_{cidx}.mp3"
            ok = synthesize_turn(chunk, str(seg_path), reference_audio_path=ref, reference_id=ref_id, speed=speed)
            if ok:
                segments.append(str(seg_path))
            else:
                print(f"[FishTTS] Warning: segment {i}-{cidx} failed, skipped")

        # 6. 添加句间停顿 + 呼吸声（Phase 3）
        if i < len(merged_script) - 1:
            pause = _compute_pause(item["text"])
            # 静音
            silence_path = tmp_dir / f"pause_{i:04d}.wav"
            _generate_silence(pause, str(silence_path))
            segments.append(str(silence_path))
            # 呼吸声（极短，增加真实感）
            breath_path = tmp_dir / f"breath_{i:04d}.wav"
            _generate_breath(str(breath_path))
            segments.append(str(breath_path))

    # 7. 拼接
    raw_path = tmp_dir / "_raw_concat.mp3"
    concat_podcast(segments, str(raw_path))

    # 8. 叠加环境底噪（Phase 3）
    if enable_room_tone:
        _mix_room_tone(str(raw_path), str(out_path))
        print(f"[FishTTS] Room tone mixed")
    else:
        shutil.copy(str(raw_path), str(out_path))

    est_cost = _estimate_cost(call_chars)
    print(f"[FishTTS] Done: {out_path} | 本次字符: {call_chars} | 估算成本: ${est_cost:.6f}")
    print(f"[FishTTS] 累计调用: {_tts_stats['total_calls']} 次 | 累计字符: {_tts_stats['total_chars']} | 估算总成本: ${_tts_stats['total_cost_usd']:.4f}")
    return str(out_path)
