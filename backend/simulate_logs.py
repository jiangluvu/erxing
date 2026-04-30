"""Generate 30 simulated log entries with new evaluation dimension keys and interaction_flag."""
import json, random, uuid
from pathlib import Path
from datetime import datetime, timezone

random.seed(42)
BASE_DIR = Path(__file__).parent
LOGS_PATH = BASE_DIR / "logs.jsonl"

entries = []

for i in range(30):
    rid = str(uuid.uuid4())
    success = random.random() < 0.87
    parse_ms = int(random.gauss(1000, 300))
    llm_ms = int(random.gauss(9500, 2500))
    tts_ms = int(random.gauss(8500, 2000))
    total_ms = parse_ms + llm_ms + tts_ms

    content_acc = random.choices([2,3,4,5], weights=[1,3,4,2])[0]
    colloquial = random.choices([2,3,4,5], weights=[2,3,4,1])[0]
    role_diff = random.choices([2,3,4,5], weights=[1,3,4,2])[0]
    scene_fit = random.choices([2,3,4,5], weights=[2,3,3,2])[0]

    format_valid = random.random() < 0.90
    has_speaker = random.random() < 0.88
    reuse = 1 if random.random() < 0.25 else 0
    full_play = 1 if random.random() < 0.35 else 0
    interaction = 1 if random.random() < 0.20 else 0

    ts = datetime(2026, 4, 29, random.randint(8, 22), random.randint(0, 59),
                  tzinfo=timezone.utc).isoformat()

    entry = {
        "request_id": rid, "phase": "tts",
        "input_type": random.choice(["url", "text"]),
        "input_length": random.randint(500, 5000),
        "timestamp": ts,
        "parse_time_ms": parse_ms, "llm_time_ms": llm_ms,
        "tts_time_ms": tts_ms, "total_time_ms": total_ms,
        "output_length": random.randint(200, 1500),
        "success": success,
        "error_message": None if success else "模拟失败",
        "has_speaker_format": has_speaker, "format_valid": format_valid,
        "content_accuracy_score": content_acc,
        "colloquial_score": colloquial,
        "role_difference_score": role_diff,
        "scene_fit_score": scene_fit,
        "reuse_flag": reuse, "full_play_flag": full_play,
        "interaction_flag": interaction,
    }
    entries.append(entry)

    parse_entry = {
        "request_id": rid, "phase": "parse",
        "timestamp": ts,
        "input_type": entry["input_type"], "input_length": entry["input_length"],
        "parse_time_ms": parse_ms, "success": True, "error_message": None,
    }
    gen_entry = {
        "request_id": rid, "phase": "generate_script",
        "timestamp": ts,
        "llm_time_ms": llm_ms, "output_length": entry["output_length"],
        "success": True, "error_message": None,
        "has_speaker_format": has_speaker, "format_valid": format_valid,
        "content_accuracy_score": content_acc,
        "colloquial_score": colloquial,
        "role_difference_score": role_diff,
        "scene_fit_score": scene_fit,
    }
    entries.extend([parse_entry, gen_entry])

with open(LOGS_PATH, "w", encoding="utf-8") as f:
    for e in entries:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")

print(f"Generated {len(entries)} log entries ({len(entries)//3} complete requests)")
