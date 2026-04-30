"""Layer 2: 系统性能指标（延迟、成功率、格式合规）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PerformanceReport:
    total: int = 0
    success_count: int = 0
    failed_count: int = 0
    success_rate: float = 0.0
    avg_latency_ms: float = 0.0
    avg_parse_ms: float = 0.0
    avg_llm_ms: float = 0.0
    avg_tts_ms: float = 0.0
    min_latency: float = 0.0
    max_latency: float = 0.0
    format_rate: float = 0.0  # format_valid 百分比
    stable_rate: float = 0.0  # has_speaker_format 百分比


def compute_performance(requests: list[dict]) -> PerformanceReport:
    """从完整的请求记录列表计算 Layer 2 性能指标。"""
    total = len(requests)
    if total == 0:
        return PerformanceReport()

    success_count = sum(1 for r in requests if r.get("success"))
    failed_count = total - success_count
    success_rate = (success_count / total) * 100

    # 延迟
    latencies = [r.get("total_time_ms", 0) for r in requests if r.get("total_time_ms")]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    min_lat = min(latencies) if latencies else 0
    max_lat = max(latencies) if latencies else 0

    # 分阶段延迟
    parse_times = [r.get("parse_time_ms", 0) for r in requests]
    llm_times = [r.get("llm_time_ms", 0) for r in requests]
    tts_times = [r.get("tts_time_ms", 0) for r in requests]
    avg_parse = sum(parse_times) / len(parse_times) if parse_times else 0
    avg_llm = sum(llm_times) / len(llm_times) if llm_times else 0
    avg_tts = sum(tts_times) / len(tts_times) if tts_times else 0

    # 格式合规
    format_valid_count = sum(1 for r in requests if r.get("format_valid"))
    format_rate = (format_valid_count / total) * 100
    stable_count = sum(1 for r in requests if r.get("has_speaker_format"))
    stable_rate = (stable_count / total) * 100

    return PerformanceReport(
        total=total,
        success_count=success_count,
        failed_count=failed_count,
        success_rate=success_rate,
        avg_latency_ms=avg_latency,
        avg_parse_ms=avg_parse,
        avg_llm_ms=avg_llm,
        avg_tts_ms=avg_tts,
        min_latency=min_lat,
        max_latency=max_lat,
        format_rate=format_rate,
        stable_rate=stable_rate,
    )
