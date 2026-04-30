"""Layer 5: MVP 用户行为指标。

严格禁止文本质量指标。只衡量用户行为：
- completion_rate：完整收听率
- repeat_usage_rate：复用率
- engagement_rate：互动率（暂停/继续/收藏）
- drop_off_rate：跳出率
"""

from __future__ import annotations

from dataclasses import dataclass

from evaluation.config import LOGS_PATH


@dataclass
class MVPReport:
    completion_rate: float = 0.0
    repeat_usage_rate: float = 0.0
    engagement_rate: float = 0.0
    drop_off_rate: float = 0.0
    sample_size: int = 0


def compute_mvp(requests: list[dict]) -> MVPReport:
    """从完整请求记录计算纯行为指标。"""
    total = len(requests)
    if total == 0:
        return MVPReport()

    full_play_count = sum(1 for r in requests if r.get("full_play_flag"))
    reuse_count = sum(1 for r in requests if r.get("reuse_flag"))
    interaction_count = sum(1 for r in requests if r.get("interaction_flag", 0))

    completion_rate = (full_play_count / total) * 100
    repeat_usage_rate = (reuse_count / total) * 100
    engagement_rate = (interaction_count / total) * 100
    drop_off_rate = 100.0 - completion_rate

    return MVPReport(
        completion_rate=completion_rate,
        repeat_usage_rate=repeat_usage_rate,
        engagement_rate=engagement_rate,
        drop_off_rate=drop_off_rate,
        sample_size=total,
    )
