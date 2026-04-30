"""版本化结果存储 + 跨版本对比。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from evaluation.config import RESULTS_DIR


def _version_dir(version: str) -> Path:
    path = RESULTS_DIR / version
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_version_result(version: str, data: dict, meta: Optional[dict] = None):
    """保存版本结果到 results/<version>/ 目录。"""
    vdir = _version_dir(version)

    # 元信息
    metadata = {
        "version": version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        ** (meta or {}),
    }
    with open(vdir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    # 各层
    layer_files = {
        "layer2_performance": "layer2_performance.json",
        "layer3_ab": "layer3_ab.json",
        "layer4_auto_eval_avg": "layer4_auto_eval_avg.json",
        "layer4_auto_eval_per_item": "layer4_auto_eval_per_item.json",
        "layer4_dialogues": "layer4_dialogues.json",
        "layer5_mvp": "layer5_mvp.json",
        "layer6_human_eval": "layer6_human_eval.json",
        "layer7_report": "layer7_report.json",
    }
    for key, filename in layer_files.items():
        if key in data:
            with open(vdir / filename, "w", encoding="utf-8") as f:
                json.dump(data[key], f, ensure_ascii=False, indent=2)

    return vdir


def load_version_result(version: str) -> Optional[dict]:
    """加载指定版本的完整结果。"""
    vdir = _version_dir(version)
    if not vdir.exists():
        return None

    result = {}
    for f in vdir.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                result[f.stem] = json.load(fp)
        except Exception:
            continue
    return result if result else None


def list_versions() -> list[str]:
    """列出所有已保存的版本。"""
    if not RESULTS_DIR.exists():
        return []
    return sorted(
        [d.name for d in RESULTS_DIR.iterdir() if d.is_dir() and (d / "meta.json").exists()]
    )


def _extract_comparable(report: dict) -> dict:
    """从 layer*_report.json 中提取可对比的指标。"""
    metrics = {}

    # Layer 2 性能
    if "layer2_performance" in report:
        p = report["layer2_performance"]
        for key in ["total", "success_rate", "avg_latency_ms", "avg_llm_ms", "avg_tts_ms", "format_rate"]:
            if key in p:
                metrics[f"layer2_{key}"] = p[key]

    # Layer 4 平均分
    if "layer4_auto_eval_avg" in report:
        for key, val in report["layer4_auto_eval_avg"].items():
            metrics[f"layer4_{key}"] = val

    # Layer 5 MVP
    if "layer5_mvp" in report:
        m = report["layer5_mvp"]
        for key in ["completion_rate", "repeat_usage_rate", "engagement_rate", "sample_size"]:
            if key in m:
                metrics[f"layer5_{key}"] = m[key]

    return metrics


def compare_versions(v_a: str, v_b: str) -> dict:
    """比较两个版本的所有可对比指标。"""
    report_a = load_version_result(v_a)
    report_b = load_version_result(v_b)

    if not report_a or not report_b:
        missing = "A" if not report_a else "B"
        return {"error": f"版本 {missing} 不存在"}

    metrics_a = _extract_comparable(report_a)
    metrics_b = _extract_comparable(report_b)

    all_keys = sorted(set(metrics_a.keys()) | set(metrics_b.keys()))
    diffs = {}
    for key in all_keys:
        val_a = metrics_a.get(key)
        val_b = metrics_b.get(key)
        if val_a is not None and val_b is not None and isinstance(val_a, (int, float)):
            delta = val_b - val_a
            pct = (delta / val_a * 100) if val_a != 0 else 0
            diffs[key] = {
                "v_a": round(val_a, 2) if isinstance(val_a, float) else val_a,
                "v_b": round(val_b, 2) if isinstance(val_b, float) else val_b,
                "delta": round(delta, 2),
                "delta_pct": round(pct, 1),
            }
        else:
            diffs[key] = {"v_a": val_a, "v_b": val_b}

    return {
        "v_a": v_a,
        "v_b": v_b,
        "metrics": diffs,
    }


def print_comparison(comp: dict):
    """打印版本对比结果。"""
    if "error" in comp:
        print(f"\n[错误] {comp['error']}")
        return

    print(f"\n{'=' * 50}")
    print(f"   版本对比: {comp['v_a']} → {comp['v_b']}")
    print(f"{'=' * 50}")

    layer_labels = {
        "layer2": "系统性能",
        "layer4": "AI 自动评测",
        "layer5": "MVP 用户行为",
    }

    last_layer = ""
    for key, vals in comp.get("metrics", {}).items():
        layer = key.split("_")[0]
        if layer != last_layer:
            label = layer_labels.get(layer, layer)
            print(f"\n  [{label}]")
            last_layer = layer

        metric_name = key[len(layer) + 1:]
        if "delta_pct" in vals and vals["delta_pct"] != "N/A":
            arrow = "+" if vals.get("delta", 0) > 0 else "-" if vals.get("delta", 0) < 0 else "="
            print(f"  {metric_name:>20}: {vals['v_a']:>8} → {vals['v_b']:<8} {arrow} {vals['delta_pct']:+.1f}%")
        else:
            print(f"  {metric_name:>20}: {vals['v_a']} → {vals['v_b']}")

    print(f"\n{'=' * 50}\n")
