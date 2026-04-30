"""
Drivio Observability Report
============================
Reads logs.jsonl, calculates MVP metrics, generates charts.

Usage:
    python analytics.py              # print report + show charts
    python analytics.py --no-plot    # print report only
    python analytics.py --export     # save charts as PNG
"""

import sys
import json
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).parent
LOGS_PATH = BASE_DIR / "logs.jsonl"
CHARTS_DIR = BASE_DIR / "charts"


def load_logs(path: str | Path) -> list[dict]:
    """Read logs.jsonl, return list of entries grouped by request_id (only TTS phase has complete data)."""
    entries = []
    if not Path(path).exists():
        print(f"[WARN] Log file not found: {path}")
        return entries
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def get_complete_requests(entries: list[dict]) -> list[dict]:
    """Aggregate entries by request_id across all phases to build complete records."""
    groups = defaultdict(dict)
    for e in entries:
        rid = e.get("request_id")
        if not rid:
            continue
        groups[rid].update(e)

    # Only return groups that have at least parse + generate_script phase data
    result = []
    for rid, data in groups.items():
        phases = {e.get("phase") for e in entries if e.get("request_id") == rid}
        if "parse" in phases or "generate_script" in phases or "tts" in phases:
            result.append(data)
    return result


def calculate_metrics(requests: list[dict]) -> dict:
    """Calculate core observability metrics."""
    total = len(requests)
    if total == 0:
        return {"total": 0}

    success_count = sum(1 for r in requests if r.get("success"))
    failed_count = total - success_count

    # Latency
    latencies = [r.get("total_time_ms", 0) for r in requests if r.get("total_time_ms")]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0

    # Phase breakdown
    parse_times = [r.get("parse_time_ms", 0) for r in requests]
    llm_times = [r.get("llm_time_ms", 0) for r in requests]
    tts_times = [r.get("tts_time_ms", 0) for r in requests]
    avg_parse = sum(parse_times) / len(parse_times) if parse_times else 0
    avg_llm = sum(llm_times) / len(llm_times) if llm_times else 0
    avg_tts = sum(tts_times) / len(tts_times) if tts_times else 0

    # Format compliance
    format_valid_count = sum(1 for r in requests if r.get("format_valid"))
    format_rate = (format_valid_count / total) * 100

    # Format stability: what fraction have has_speaker_format
    stable_count = sum(1 for r in requests if r.get("has_speaker_format"))
    stable_rate = (stable_count / total) * 100

    # Quality scores
    scores = {"content_accuracy_score": [], "colloquial_score": [],
              "role_difference_score": [], "scene_fit_score": []}
    for r in requests:
        for k in scores:
            v = r.get(k)
            if v is not None:
                scores[k].append(v)

    avg_scores = {k: (sum(v) / len(v) if v else 0) for k, v in scores.items()}

    # MVP scoring — 纯行为指标（不含文本质量）
    # 总分 = 转化成功*20 + 完整收听*20 + 复用行为*20 = 60分满分
    def calc_mvp_score(r):
        conv = 20 if r.get("success") else 0
        full_play = 20 if r.get("full_play_flag") else 0
        reuse = 20 if r.get("reuse_flag") else 0
        return conv + full_play + reuse

    mvp_scores = [calc_mvp_score(r) for r in requests if r.get("success")]
    mvp_success_count = sum(1 for s in mvp_scores if s >= 50)
    mvp_partial_count = sum(1 for s in mvp_scores if 35 <= s < 50)
    mvp_fail_count = sum(1 for s in mvp_scores if s < 35)
    mvp_success_rate = (mvp_success_count / len(mvp_scores) * 100) if mvp_scores else 0

    return {
        "total": total,
        "success_count": success_count,
        "failed_count": failed_count,
        "success_rate": (success_count / total) * 100,
        "avg_latency_ms": avg_latency,
        "avg_parse_ms": avg_parse,
        "avg_llm_ms": avg_llm,
        "avg_tts_ms": avg_tts,
        "min_latency": min(latencies) if latencies else 0,
        "max_latency": max(latencies) if latencies else 0,
        "format_rate": format_rate,
        "stable_rate": stable_rate,
        "avg_scores": avg_scores,
        "mvp_scores": mvp_scores,
        "mvp_success_count": mvp_success_count,
        "mvp_partial_count": mvp_partial_count,
        "mvp_fail_count": mvp_fail_count,
        "mvp_success_rate": mvp_success_rate,
    }


def print_report(metrics: dict):
    print("\n" + "=" * 50)
    print("   Drivio Observability Report")
    print("=" * 50)

    if metrics["total"] == 0:
        print("\n   No data in logs.jsonl")
        print("=" * 50 + "\n")
        return

    m = metrics
    print(f"\n  [概览]")
    print(f"  {'总请求数':>12}: {m['total']}")
    print(f"  {'成功':>12}: {m['success_count']}")
    print(f"  {'失败':>12}: {m['failed_count']}")
    print(f"  {'成功率':>12}: {m['success_rate']:.1f}%")

    print(f"\n  [延迟分析]")
    print(f"  {'平均总延迟':>12}: {m['avg_latency_ms']:.0f} ms")
    print(f"  {'最短':>12}: {m['min_latency']:.0f} ms")
    print(f"  {'最长':>12}: {m['max_latency']:.0f} ms")
    print(f"  {'解析阶段':>12}: {m['avg_parse_ms']:.0f} ms")
    print(f"  {'LLM阶段':>12}: {m['avg_llm_ms']:.0f} ms")
    print(f"  {'TTS阶段':>12}: {m['avg_tts_ms']:.0f} ms")

    print(f"\n  [质量合规]")
    print(f"  {'格式合规率':>12}: {m['format_rate']:.1f}%")
    print(f"  {'模型稳定率':>12}: {m['stable_rate']:.1f}%")

    print(f"\n  [平均质量评分 (1-5)]")
    for k, v in m["avg_scores"].items():
        label = {"content_accuracy_score": "内容准确性", "colloquial_score": "口语化程度",
                 "role_difference_score": "角色差异性", "scene_fit_score": "场景适配"}.get(k, k)
        bar = "█" * int(v) + "░" * (5 - int(v))
        print(f"  {label}: {v:.1f}  {bar}")

    print(f"\n  [MVP评估 (纯行为)]")
    print(f"  {'成立(≥50分)':>12}: {m['mvp_success_count']}")
    print(f"  {'部分成立(35-49)':>12}: {m['mvp_partial_count']}")
    print(f"  {'不成立(<35)':>12}: {m['mvp_fail_count']}")
    print(f"  {'MVP成立率':>12}: {m['mvp_success_rate']:.1f}%")
    if m["mvp_scores"]:
        avg_mvp = sum(m["mvp_scores"]) / len(m["mvp_scores"])
        print(f"  {'平均MVP分':>12}: {avg_mvp:.1f} / 60")

    verdict = "成立" if m["mvp_success_rate"] >= 70 else ("部分成立" if m["mvp_success_rate"] >= 50 else "不成立")
    print(f"\n  [结论]: {verdict}")
    print("=" * 50 + "\n")


def generate_charts(requests: list[dict], export: bool = False):
    try:
        import matplotlib
        if not export:
            matplotlib.use("TkAgg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("[WARN] matplotlib not installed. Skipping charts.")
        print("        Install: pip install matplotlib")
        return

    if not requests:
        print("[WARN] No data for charts.")
        return

    if export:
        CHARTS_DIR.mkdir(exist_ok=True)

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "PingFang SC", "Noto Sans CJK"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    fig.suptitle("Drivio Observability Dashboard", fontsize=16, fontweight="bold")

    # 1. Latency distribution
    ax1 = axes[0, 0]
    latencies = [r.get("total_time_ms", 0) for r in requests if r.get("total_time_ms")]
    if latencies:
        ax1.hist(latencies, bins=min(20, len(set(latencies))), color="#5865F2", alpha=0.7, edgecolor="white")
        ax1.axvline(sum(latencies) / len(latencies), color="#DC3545", linestyle="--", label=f"平均 {sum(latencies)/len(latencies):.0f}ms")
        ax1.set_xlabel("Total Time (ms)")
        ax1.set_ylabel("Count")
        ax1.set_title("Total Time Distribution")
        ax1.legend()

    # 2. Success trend
    ax2 = axes[0, 1]
    if requests:
        sorted_r = sorted(requests, key=lambda r: r.get("timestamp", ""))
        successes = [1 if r.get("success") else 0 for r in sorted_r]
        cum_success = []
        cum_count = 0
        cum_ok = 0
        for s in successes:
            cum_count += 1
            cum_ok += s
            cum_success.append((cum_ok / cum_count) * 100)
        ax2.plot(range(1, len(cum_success) + 1), cum_success, color="#28A745", linewidth=2)
        ax2.axhline(y=70, color="#DC3545", linestyle="--", alpha=0.5, label="70% 目标")
        ax2.set_xlabel("Request #")
        ax2.set_ylabel("Success Rate (%)")
        ax2.set_title("Success Trend")
        ax2.set_ylim(0, 105)
        ax2.legend()

    # 3. MVP score distribution
    ax3 = axes[1, 0]
    scores = []
    for r in requests:
        conv = 20 if r.get("success") else 0
        full = 20 if r.get("full_play_flag") else 0
        reu = 20 if r.get("reuse_flag") else 0
        scores.append(conv + full + reu)

    if scores:
        bins = [0, 35, 50, 60]
        n, bins_edges, patches = ax3.hist(scores, bins=bins, edgecolor="white", linewidth=1.2)
        for i, p in enumerate(patches):
            if p.get_x() < 35:
                p.set_facecolor("#DC3545")
            elif p.get_x() < 50:
                p.set_facecolor("#FFC107")
            else:
                p.set_facecolor("#28A745")
        ax3.axvline(x=35, color="#DC3545", linestyle=":", alpha=0.5)
        ax3.axvline(x=50, color="#28A745", linestyle=":", alpha=0.5)
        ax3.set_xlabel("MVP Score")
        ax3.set_ylabel("Count")
        ax3.set_title("MVP Score Distribution (Behavioral)")
        # Add zone labels
        ax3.text(17, ax3.get_ylim()[1] * 0.9, "不成立", ha="center", fontsize=10, color="#DC3545")
        ax3.text(42, ax3.get_ylim()[1] * 0.9, "部分", ha="center", fontsize=10, color="#FFC107")
        ax3.text(55, ax3.get_ylim()[1] * 0.9, "成立", ha="center", fontsize=10, color="#28A745")

    # 4. Content accuracy distribution
    ax4 = axes[1, 1]
    accuracy_scores = [r.get("content_accuracy_score", 3) for r in requests if r.get("content_accuracy_score")]
    if accuracy_scores:
        counts = [accuracy_scores.count(i) for i in range(1, 6)]
        bars = ax4.bar(range(1, 6), counts, color="#5865F2", alpha=0.7, edgecolor="white")
        # Color the good bars green
        for i, bar in enumerate(bars):
            if i >= 3:
                bar.set_color("#28A745")
        ax4.set_xlabel("Score (1-5)")
        ax4.set_ylabel("Count")
        ax4.set_title("Content Accuracy Distribution")
        ax4.set_xticks(range(1, 6))

    plt.tight_layout()

    if export:
        path = CHARTS_DIR / "observability_dashboard.png"
        fig.savefig(str(path), dpi=150, bbox_inches="tight")
        print(f"  Charts saved to: {path}")
    else:
        plt.show()


def main():
    export = "--export" in sys.argv
    no_plot = "--no-plot" in sys.argv

    entries = load_logs(LOGS_PATH)
    requests = get_complete_requests(entries)
    metrics = calculate_metrics(requests)
    print_report(metrics)

    if not no_plot:
        generate_charts(requests, export=export)


if __name__ == "__main__":
    main()
