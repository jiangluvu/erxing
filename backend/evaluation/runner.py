"""CLI 入口点 — 编排所有评测层。

用法：
  python -m evaluation.runner --benchmark            # 仅运行基准
  python -m evaluation.runner --benchmark --version v1.1.0
  python -m evaluation.runner --ab                   # 运行 A/B 比较
  python -m evaluation.runner --full                 # 运行所有
  python -m evaluation.runner --list-versions        # 列出已存储的结果
  python -m evaluation.runner --compare v1.0.0 v1.1.0
  python -m evaluation.runner --report v1.0.0        # 查看已保存的报告
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Optional

# 将 backend 目录加入 path，以便导入 app 模块
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from evaluation.benchmark import BenchmarkSet
from evaluation.performance import compute_performance, PerformanceReport
from evaluation.auto_eval import auto_evaluate, batch_auto_evaluate, AutoEvalResult
from evaluation.mvp_metrics import compute_mvp, MVPReport
from evaluation.ab_comparison import run_ab_comparison, ABReport
from evaluation.human_eval import compute_human_report, HumanEvalReport
from evaluation.report import generate_report, print_report, export_report_json, UnifiedReport
from evaluation.storage import (
    save_version_result, load_version_result, list_versions,
    compare_versions, print_comparison,
)
from evaluation.config import ZHI_MODEL, EVAL_MODEL, LOGS_PATH


def _load_logs() -> list[dict]:
    """从 logs.jsonl 加载并聚合完整的请求记录。"""
    import json as j
    from collections import defaultdict

    if not LOGS_PATH.exists():
        return []

    entries = []
    with open(LOGS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(j.loads(line))
                except Exception:
                    continue

    groups = defaultdict(dict)
    for e in entries:
        rid = e.get("request_id")
        if rid:
            groups[rid].update(e)

    # 只保留有 TTS 阶段数据的完整请求
    result = []
    for rid, data in groups.items():
        if data.get("phase") == "tts" or data.get("total_time_ms"):
            result.append(data)
    return result


def _get_client():
    """获取 Anthropic client（延迟导入避免 app 初始化开销）。"""
    from app import client as app_client
    return app_client


def cmd_benchmark(args):
    """Layer 1 + 2 + 4: 加载 benchmark → 生成对话 → 自动评测 → 性能统计。"""
    print(f"\n[Layer 1] 加载 benchmark {args.benchmark}...")
    bset = BenchmarkSet.load(args.benchmark)
    print(f"  共 {len(bset)} 条数据")

    if args.filter:
        items = bset.filter_by_category(args.filter)
        print(f"  筛选类别: {args.filter} → {len(items)} 条")
    else:
        items = bset.items

    if not items:
        print("[错误] 没有可用的 benchmark 条目")
        return

    client = _get_client()
    generation_results = []

    print(f"\n[Layer 2] 执行对话生成...")
    for i, item in enumerate(items):
        t0 = time.time()
        try:
            from app import generate_structured_dialogue
            dialogue, eval_scores, llm_time = generate_structured_dialogue(
                item.source_text, item.variant
            )
            total_ms = int((time.time() - t0) * 1000)
            generation_results.append({
                "item_id": item.id,
                "category": item.category,
                "title": item.title,
                "source_text": item.source_text,
                "dialogue": dialogue,
                "success": True,
                "parse_time_ms": 0,
                "llm_time_ms": llm_time,
                "tts_time_ms": 0,
                "total_time_ms": total_ms,
                "output_length": sum(len(d["text"]) for d in dialogue),
                "format_valid": all(d.get("speaker") in ("小羊", "小姜") and len(d.get("text", "").strip()) > 0 for d in dialogue),
                "has_speaker_format": all(d.get("speaker") in ("小羊", "小姜") for d in dialogue),
            })
            print(f"  [{i+1}/{len(items)}] {item.id} ({item.category}) OK {total_ms}ms")
        except Exception as e:
            print(f"  [{i+1}/{len(items)}] {item.id} FAIL {str(e)[:60]}")
            generation_results.append({
                "item_id": item.id,
                "category": item.category,
                "title": item.title,
                "source_text": item.source_text,
                "dialogue": [],
                "success": False,
                "parse_time_ms": 0,
                "llm_time_ms": 0,
                "tts_time_ms": 0,
                "total_time_ms": 0,
                "output_length": 0,
                "format_valid": False,
                "has_speaker_format": False,
            })

    # Layer 2: 性能统计
    perf = compute_performance(generation_results)
    print(f"\n[Layer 2] 性能统计完成")
    print(f"  成功率: {perf.success_rate:.1f}%  |  平均 LLM 延迟: {perf.avg_llm_ms:.0f}ms")

    # Layer 4: AI 自动评测
    print(f"\n[Layer 4] AI 自动评测 (model: {EVAL_MODEL})...")
    auto_results = []
    for i, r in enumerate(generation_results):
        if r["dialogue"] and r["success"]:
            result = auto_evaluate(r["source_text"], r["dialogue"], item_id=r["item_id"])
        else:
            result = AutoEvalResult(item_id=r["item_id"])
        auto_results.append(result)
        print(f"  [{i+1}/{len(generation_results)}] {result.item_id}: {result.content_accuracy}/{result.dialogue_naturalness}/{result.scene_fit}")

    # Layer 5: MVP（从现有 logs.jsonl 加载）
    logs_requests = _load_logs()
    mvp = compute_mvp(logs_requests) if logs_requests else None

    # Layer 6: 人工评测（如果有数据）
    human = compute_human_report(version=args.version) if not args.skip_human else None

    # Layer 7: 统一报表
    version = args.version or f"benchmark_{args.benchmark}"
    report = generate_report(
        version=version,
        benchmark_version=args.benchmark,
        performance=perf,
        auto_eval_results=auto_results,
        mvp=mvp,
        human_eval=human,
        model=ZHI_MODEL,
        eval_model=EVAL_MODEL,
    )

    print_report(report)

    # 存储结果
    if args.save:
        data = {
            "layer2_performance": perf.__dict__,
            "layer4_auto_eval_avg": report.auto_eval_averages,
            "layer4_auto_eval_per_item": report.auto_eval_per_item,
            "layer4_dialogues": [  # 保存对话内容供 A/B 对比使用
                {"item_id": r["item_id"], "category": r["category"],
                 "source_text": r["source_text"], "dialogue": r["dialogue"]}
                for r in generation_results if r["dialogue"]
            ],
            "layer5_mvp": mvp.__dict__ if mvp else {},
            "layer6_human_eval": human.__dict__ if human else {},
            "layer7_report": report.to_dict(),
        }
        meta = {"model": ZHI_MODEL, "eval_model": EVAL_MODEL, "benchmark": args.benchmark}
        vdir = save_version_result(version, data, meta=meta)
        print(f"\n  结果已保存: {vdir}")

        # 导出 JSON 报表
        report_path = vdir / "layer7_report.json"
        export_report_json(report, report_path)


def cmd_ab(args):
    """Layer 3: A/B 对比。"""
    if not args.version_a or not args.version_b:
        versions = list_versions()
        if len(versions) < 2:
            print("[错误] 需要至少两个已存储的版本做 A/B 对比")
            return
        args.version_a = args.version_a or versions[-2]
        args.version_b = args.version_b or versions[-1]

    print(f"\n[Layer 3] A/B 对比: {args.version_a} vs {args.version_b}")

    result_a = load_version_result(args.version_a)
    result_b = load_version_result(args.version_b)

    if not result_a or not result_b:
        print(f"[错误] 版本数据不完整")
        return

    dialogues_a = result_a.get("layer4_dialogues", [])
    dialogues_b = result_b.get("layer4_dialogues", [])

    if not dialogues_a or not dialogues_b:
        print("[错误] 版本中没有保存对话数据，请重新运行 benchmark 并确保 storage 保存了 dialogue")
        return

    # 按 item_id 配对
    by_id_a = {d["item_id"]: d for d in dialogues_a}
    by_id_b = {d["item_id"]: d for d in dialogues_b}
    common_ids = sorted(set(by_id_a.keys()) & set(by_id_b.keys()))

    if len(common_ids) < 3:
        print(f"[错误] 共同条目不足 (找到 {len(common_ids)} 条，需要至少 3 条)")
        return

    print(f"  共同条目: {len(common_ids)} 条")
    paired = []
    for item_id in common_ids:
        paired.append({
            "item_id": item_id,
            "source_text": by_id_a[item_id]["source_text"],
            "dialogue_a": by_id_a[item_id]["dialogue"],
            "dialogue_b": by_id_b[item_id]["dialogue"],
        })

    # 运行 A/B 对比
    ab_report = run_ab_comparison(paired, version_a=args.version_a, version_b=args.version_b)
    print(f"\n[Layer 3] A/B 对比完成")
    for r in ab_report.results:
        sig = "[S]" if r.is_significant else "[ ]"
        print(f"  {r.dimension}: A={r.a_win_rate:.1%} B={r.b_win_rate:.1%} 平={r.ties} {sig}")
    print(f"  综合判断: {ab_report.overall_verdict}")


def cmd_full(args):
    """运行完整评测: benchmark + A/B + 报告。"""
    # 先跑 benchmark
    cmd_benchmark(args)

    # 然后尝试 A/B 对比
    versions = list_versions()
    if len(versions) >= 2:
        print(f"\n--- 运行 A/B 对比 ---")
        args.version_a = versions[-2]
        args.version_b = versions[-1]
        cmd_ab(args)


def cmd_list(args):
    """列出已存储的版本。"""
    versions = list_versions()
    if not versions:
        print("\n没有已保存的版本结果。")
        return
    print(f"\n已保存的版本 ({len(versions)}):")
    for v in versions:
        result = load_version_result(v)
        meta = result.get("meta", {}) if result else {}
        ts = meta.get("timestamp", "?")[:19] if meta else "?"
        model = meta.get("model", "?") if meta else "?"
        print(f"  {v:<12} {ts}  model: {model}")


def cmd_compare(args):
    """比较两个版本。"""
    if args.versions and len(args.versions) >= 2:
        comp = compare_versions(args.versions[0], args.versions[1])
    else:
        versions = list_versions()
        if len(versions) < 2:
            print("[错误] 需要至少两个已保存的版本")
            return
        comp = compare_versions(versions[-2], versions[-1])

    print_comparison(comp)


def cmd_report(args):
    """查看已保存的报告。"""
    result = load_version_result(args.version)
    if not result:
        print(f"[错误] 版本 {args.version} 不存在")
        return

    report_data = result.get("layer7_report", {})
    if not report_data:
        print(f"[错误] 版本 {args.version} 没有报表数据")
        return

    # 重建 UnifiedReport 对象
    meta = report_data.get("report_metadata", {})
    decision = report_data.get("decision", {})

    perf_data = report_data.get("layer2_performance")
    perf = PerformanceReport(**perf_data) if perf_data else None

    print(f"\n=== 报告: {args.version} ===")
    print(f"  生成时间: {meta.get('generated_at', '?')[:19]}")
    print(f"  模型: {meta.get('model', '?')}")
    print(f"  结论: {decision.get('go_nogo', '?')}")
    if decision.get("biggest_bottleneck"):
        print(f"  最大瓶颈: {decision['biggest_bottleneck']}")


def main():
    parser = argparse.ArgumentParser(description="Podcraft 多层评测系统")
    parser.add_argument("--benchmark", default="v1", nargs="?", const="v1",
                        help="运行 benchmark 评测（默认 v1）")
    parser.add_argument("--ab", action="store_true", help="运行 A/B 对比")
    parser.add_argument("--full", action="store_true", help="运行完整评测")
    parser.add_argument("--version", default="", help="版本标签")
    parser.add_argument("--version-a", default="", help="A/B 版本 A")
    parser.add_argument("--version-b", default="", help="A/B 版本 B")
    parser.add_argument("--filter", default="", help="按类别筛选 (short_news/mid_article/long_article/car_scene)")
    parser.add_argument("--save", action="store_true", help="保存结果")
    parser.add_argument("--skip-human", action="store_true", help="跳过人工评测层")
    parser.add_argument("--list-versions", action="store_true", help="列出已存版本")
    parser.add_argument("--compare", nargs="*", default=[], help="比较两个版本")
    parser.add_argument("--report", default="", help="查看已保存的报告")

    args = parser.parse_args()

    if args.list_versions:
        cmd_list(args)
    elif args.compare:
        cmd_compare(args)
    elif args.report:
        cmd_report(args)
    elif args.ab:
        cmd_ab(args)
    elif args.full:
        cmd_full(args)
    elif args.benchmark:
        cmd_benchmark(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()


# ── 公共入口（供外部程序调用） ──

def run_benchmark(version: str = "v1", save: bool = False, **kwargs):
    """运行 benchmark 评测。"""
    import argparse
    args = argparse.Namespace(benchmark=version, version="", filter="", save=save,
                              skip_human=False)
    for k, v in kwargs.items():
        setattr(args, k, v)
    cmd_benchmark(args)


def run_ab_comparison(version_a: str = "", version_b: str = ""):
    """运行 A/B 对比。"""
    import argparse
    args = argparse.Namespace(version_a=version_a, version_b=version_b)
    cmd_ab(args)


def run_full(version: str = "v1", save: bool = False, **kwargs):
    """运行完整评测。"""
    import argparse
    args = argparse.Namespace(benchmark=version, version="", filter="", save=save,
                              skip_human=False)
    for k, v in kwargs.items():
        setattr(args, k, v)
    cmd_full(args)
