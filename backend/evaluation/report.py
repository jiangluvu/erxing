"""Layer 7: 统一决策报表。

聚合所有层 → UnifiedReport，生成 GO / CONDITIONAL / NO-GO 决策。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from evaluation.performance import PerformanceReport
from evaluation.ab_comparison import ABReport
from evaluation.auto_eval import AutoEvalResult
from evaluation.mvp_metrics import MVPReport
from evaluation.human_eval import HumanEvalReport

# ── 判断阈值 ──
THRESHOLDS = {
    "layer2_min_success_rate": 80.0,
    "layer4_min_content_accuracy": 3.5,
    "layer4_min_dialogue_naturalness": 3.5,
    "layer4_min_scene_fit": 3.0,
    "layer5_min_completion_rate": 20.0,
    "layer5_min_repeat_usage_rate": 15.0,
    "layer6_min_conversation_score": 3.0,
}


@dataclass
class UnifiedReport:
    # 元信息
    version: str = ""
    benchmark_version: str = ""
    generated_at: str = ""
    model: str = ""
    eval_model: str = ""

    # 各层结果
    performance: Optional[PerformanceReport] = None
    ab_comparison: Optional[ABReport] = None
    auto_eval_per_item: list[dict] = field(default_factory=list)
    auto_eval_averages: dict[str, float] = field(default_factory=dict)
    auto_eval_by_category: dict[str, dict[str, float]] = field(default_factory=dict)
    mvp: Optional[MVPReport] = None
    human_eval: Optional[HumanEvalReport] = None

    # 决策
    go_nogo: str = "NO-GO"
    biggest_bottleneck: str = ""
    threshold_breaches: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "report_metadata": {
                "version": self.version,
                "benchmark_version": self.benchmark_version,
                "generated_at": self.generated_at,
                "model": self.model,
                "eval_model": self.eval_model,
            },
            "decision": {
                "go_nogo": self.go_nogo,
                "biggest_bottleneck": self.biggest_bottleneck,
                "thresholds_applied": THRESHOLDS,
                "threshold_breaches": self.threshold_breaches,
            },
        }
        if self.performance:
            d["layer2_performance"] = self.performance.__dict__
        if self.ab_comparison:
            d["layer3_ab"] = self.ab_comparison.to_dict()
        if self.auto_eval_averages:
            d["layer4_auto_eval"] = {
                "averages": self.auto_eval_averages,
                "by_category": self.auto_eval_by_category,
                "per_item": self.auto_eval_per_item,
            }
        if self.mvp:
            d["layer5_mvp"] = self.mvp.__dict__
        if self.human_eval:
            d["layer6_human_eval"] = {
                **self.human_eval.__dict__,
                "avg_scores": self.human_eval.avg_scores,
            }
        return d


def _make_decision(report: UnifiedReport) -> tuple[str, list[str]]:
    """根据各层阈值计算 GO/NO-GO 决策。"""
    breaches = []

    # Layer 2
    if report.performance and report.performance.total > 0:
        if report.performance.success_rate < THRESHOLDS["layer2_min_success_rate"]:
            breaches.append(
                f"layer2: success_rate={report.performance.success_rate:.1f}% < {THRESHOLDS['layer2_min_success_rate']}%"
            )

    # Layer 4
    for dim, key in [
        ("content_accuracy", "layer4_min_content_accuracy"),
        ("dialogue_naturalness", "layer4_min_dialogue_naturalness"),
        ("scene_fit", "layer4_min_scene_fit"),
    ]:
        val = report.auto_eval_averages.get(dim, 5.0)
        threshold = THRESHOLDS[key]
        if val < threshold:
            breaches.append(f"layer4: {dim}={val:.2f} < {threshold}")

    # Layer 5
    if report.mvp and report.mvp.sample_size > 0:
        if report.mvp.completion_rate < THRESHOLDS["layer5_min_completion_rate"]:
            breaches.append(
                f"layer5: completion_rate={report.mvp.completion_rate:.1f}% < {THRESHOLDS['layer5_min_completion_rate']}%"
            )
        if report.mvp.repeat_usage_rate < THRESHOLDS["layer5_min_repeat_usage_rate"]:
            breaches.append(
                f"layer5: repeat_usage_rate={report.mvp.repeat_usage_rate:.1f}% < {THRESHOLDS['layer5_min_repeat_usage_rate']}%"
            )

    if not breaches:
        return "GO", []
    elif len(breaches) <= 2:
        return "CONDITIONAL", breaches
    else:
        return "NO-GO", breaches


def _find_bottleneck(report: UnifiedReport) -> str:
    """定位当前最大瓶颈。"""
    candidates = []

    # Layer 2 延迟瓶颈
    if report.performance and report.performance.avg_llm_ms > 8000:
        candidates.append(("LLM 延迟", f"{report.performance.avg_llm_ms:.0f}ms", "Layer 2"))

    if report.performance and report.performance.avg_tts_ms > 8000:
        candidates.append(("TTS 延迟", f"{report.performance.avg_tts_ms:.0f}ms", "Layer 2"))

    # Layer 4 质量瓶颈
    for dim in ["dialogue_naturalness", "content_accuracy", "scene_fit"]:
        val = report.auto_eval_averages.get(dim, 5.0)
        if val < 3.5:
            candidates.append((f"AI 评分-{dim}", f"{val:.2f}/5", "Layer 4"))

    # Layer 5 行为瓶颈
    if report.mvp and report.mvp.completion_rate < 30:
        candidates.append(("用户完成率", f"{report.mvp.completion_rate:.1f}%", "Layer 5"))

    if not candidates:
        # 从各层取最低分
        lowest = 5.0
        lowest_dim = ""
        for dim, val in report.auto_eval_averages.items():
            if val < lowest:
                lowest = val
                lowest_dim = dim
        if lowest_dim:
            return f"对话质量-{lowest_dim} ({lowest:.2f}/5) — 建议优化生成 Prompt"
        return "无明显瓶颈"

    # 选最严重的一个
    candidates.sort(key=lambda c: ("Prompt", "LLM", "TTS", "用户行为").index(c[2]) if c[2] in ("Prompt", "LLM", "TTS", "用户行为") else 99)
    c = candidates[0]
    return f"{c[0]} ({c[1]}) — 问题位于 {c[2]}"


def generate_report(
    version: str,
    benchmark_version: str,
    performance: Optional[PerformanceReport] = None,
    ab_comparison: Optional[ABReport] = None,
    auto_eval_results: Optional[list[AutoEvalResult]] = None,
    mvp: Optional[MVPReport] = None,
    human_eval: Optional[HumanEvalReport] = None,
    model: str = "",
    eval_model: str = "",
) -> UnifiedReport:
    """聚合各层数据生成统一报表。"""
    report = UnifiedReport(
        version=version,
        benchmark_version=benchmark_version,
        generated_at=datetime.now(timezone.utc).isoformat(),
        model=model,
        eval_model=eval_model,
        performance=performance,
        ab_comparison=ab_comparison,
        mvp=mvp,
        human_eval=human_eval,
    )

    # Layer 4 聚合
    if auto_eval_results:
        report.auto_eval_per_item = [r.to_dict() for r in auto_eval_results]
        # 计算平均值
        dims = ["content_accuracy", "dialogue_naturalness", "scene_fit"]
        for dim in dims:
            vals = [getattr(r, dim, 3.0) for r in auto_eval_results]
            report.auto_eval_averages[dim] = sum(vals) / len(vals) if vals else 0.0

        # 按类别聚合
        categories = {}
        for r in auto_eval_results:
            cat = r.item_id.split("_")[0] if "_" in r.item_id else "unknown"
            categories.setdefault(cat, []).append(r)
        for cat, items in categories.items():
            report.auto_eval_by_category[cat] = {}
            for dim in dims:
                vals = [getattr(r, dim, 3.0) for r in items]
                report.auto_eval_by_category[cat][dim] = sum(vals) / len(vals) if vals else 0.0

    # 决策
    report.go_nogo, report.threshold_breaches = _make_decision(report)
    report.biggest_bottleneck = _find_bottleneck(report)

    return report


def print_report(report: UnifiedReport):
    """打印统一报表到终端。"""
    border = "=" * 50
    print(f"\n{border}")
    print(f"   Podcraft 评估报告 — {report.version}")
    print(f"   benchmark: {report.benchmark_version}  |  {report.generated_at[:19]}")
    print(border)

    # Layer 2 性能
    if report.performance:
        p = report.performance
        print(f"\n  [系统性能 Layer 2]")
        print(f"  {'总请求数':>12}: {p.total}")
        print(f"  {'成功率':>12}: {p.success_rate:.1f}%")
        print(f"  {'平均总延迟':>12}: {p.avg_latency_ms:.0f} ms")
        print(f"  {'解析阶段':>12}: {p.avg_parse_ms:.0f} ms")
        print(f"  {'LLM阶段':>12}: {p.avg_llm_ms:.0f} ms")
        print(f"  {'TTS阶段':>12}: {p.avg_tts_ms:.0f} ms")
        print(f"  {'格式合规率':>12}: {p.format_rate:.1f}%")

    # Layer 3 A/B
    if report.ab_comparison:
        ab = report.ab_comparison
        print(f"\n  [A/B 对比 Layer 3]")
        print(f"  {'版本A':>12}: {ab.version_a}")
        print(f"  {'版本B':>12}: {ab.version_b}")
        print(f"  {'综合判断':>12}: {ab.overall_verdict}")
        print(f"  {'对比轮次':>12}: {ab.comparisons_total}")
        for r in ab.results:
            label_map = {
                "overall_naturalness": "整体自然度",
                "car_scene_fit": "播客收听场景适配",
                "info_density_reasonableness": "信息密度合理性",
            }
            label = label_map.get(r.dimension, r.dimension)
            sig = "[S]" if r.is_significant else "[ ]"
            print(f"  {label}: A={r.a_win_rate:.0%} B={r.b_win_rate:.0%} 平={r.ties} {sig}")

    # Layer 4 AI 自动评测
    if report.auto_eval_averages:
        print(f"\n  [AI 自动评测 Layer 4 (参考)]")
        label_map = {
            "content_accuracy": "内容准确性",
            "dialogue_naturalness": "对话自然度",
            "scene_fit": "场景适配",
        }
        for dim, avg in report.auto_eval_averages.items():
            label = label_map.get(dim, dim)
            bar = "#" * int(avg) + "-" * (5 - int(avg))
            print(f"  {label}: {avg:.2f}  [{bar}]")

    # Layer 5 MVP
    if report.mvp:
        m = report.mvp
        print(f"\n  [MVP 用户行为 Layer 5]")
        print(f"  {'样本量':>12}: {m.sample_size}")
        print(f"  {'完整收听率':>12}: {m.completion_rate:.1f}%")
        print(f"  {'复用率':>12}: {m.repeat_usage_rate:.1f}%")
        print(f"  {'互动率':>12}: {m.engagement_rate:.1f}%")
        print(f"  {'跳出率':>12}: {m.drop_off_rate:.1f}%")

    # Layer 6 人工评测
    if report.human_eval and report.human_eval.entries_count > 0:
        h = report.human_eval
        print(f"\n  [人工评测 Layer 6]")
        print(f"  {'评分条目':>12}: {h.entries_count}")
        print(f"  {'评分人数':>12}: {h.rater_count}")
        label_map = {
            "sounds_like_real_conversation": "像真实对话",
            "suitable_for_car": "适合播客收听",
            "info_density_reasonableness": "信息密度合理",
            "willing_to_finish": "愿意听完",
        }
        for dim, avg in h.avg_scores.items():
            label = label_map.get(dim, dim)
            bar = "#" * int(avg) + "-" * (5 - int(avg))
            print(f"  {label}: {avg:.2f}  [{bar}]")

    # 决策
    print(f"\n  [决策]")
    no_emoji_map = {"GO": "[V]", "CONDITIONAL": "[~]", "NO-GO": "[X]"}
    print(f"  {'结论':>12}: {no_emoji_map.get(report.go_nogo, '?')} {report.go_nogo}")
    if report.threshold_breaches:
        print(f"  {'告警':>12}:")
        for b in report.threshold_breaches[:3]:
            print(f"           - {b}")
    print(f"  {'最大瓶颈':>12}: {report.biggest_bottleneck}")

    print(border + "\n")


def export_report_json(report: UnifiedReport, path: Path):
    """导出报表为 JSON 文件。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
