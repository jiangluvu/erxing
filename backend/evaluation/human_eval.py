"""Layer 6: 人工评测 — 盲测校准，不参与实时决策。

评分维度（1-5）：
- sounds_like_real_conversation：是否像真实对话
- suitable_for_car：是否适合车载收听
- info_density_reasonableness：信息密度是否合理
- willing_to_finish：是否愿意完整听完

规则：
- blind test（隐藏版本信息）
- 至少 2 人评分取均值
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from evaluation.config import RESULTS_DIR


@dataclass
class HumanEvalEntry:
    id: str = ""
    benchmark_item_id: str = ""
    version: str = ""
    rater_id: str = ""
    scores: dict[str, int] = field(default_factory=dict)
    rated_at: str = ""

    @property
    def is_valid(self) -> bool:
        return len(self.scores) == 4 and all(1 <= v <= 5 for v in self.scores.values())


@dataclass
class HumanEvalReport:
    entries_count: int = 0
    rater_count: int = 0
    avg_scores: dict[str, float] = field(default_factory=dict)
    per_rater: dict[str, dict[str, float]] = field(default_factory=dict)


HUMAN_EVAL_DIR = RESULTS_DIR / "human_eval"


def _ensure_dir():
    HUMAN_EVAL_DIR.mkdir(parents=True, exist_ok=True)


def register_evaluation(
    benchmark_item_id: str,
    version: str,
    rater_id: str,
    scores: dict[str, int],
) -> HumanEvalEntry:
    """录入一条人工评分。"""
    _ensure_dir()
    entry = HumanEvalEntry(
        id=str(uuid.uuid4()),
        benchmark_item_id=benchmark_item_id,
        version=version,
        rater_id=rater_id,
        scores=scores,
        rated_at=datetime.now(timezone.utc).isoformat(),
    )
    if not entry.is_valid:
        raise ValueError(f"评分无效: {scores}")

    path = HUMAN_EVAL_DIR / f"{entry.id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entry.__dict__, f, ensure_ascii=False, indent=2)
    return entry


def _load_all_entries() -> list[HumanEvalEntry]:
    _ensure_dir()
    entries = []
    for p in HUMAN_EVAL_DIR.glob("*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries.append(HumanEvalEntry(**data))
        except Exception:
            continue
    return entries


def compute_human_report(version: Optional[str] = None) -> HumanEvalReport:
    """计算某版本（或全部）的人工评分聚合。"""
    entries = _load_all_entries()
    if version:
        entries = [e for e in entries if e.version == version]

    if not entries:
        return HumanEvalReport()

    raters = set(e.rater_id for e in entries)

    # 计算总分
    all_scores: dict[str, list[int]] = {}
    for e in entries:
        for dim, score in e.scores.items():
            all_scores.setdefault(dim, []).append(score)

    avg_scores = {dim: sum(vals) / len(vals) for dim, vals in all_scores.items()}

    # 按评分人分组
    per_rater: dict[str, dict[str, float]] = {}
    for rater in raters:
        rater_entries = [e for e in entries if e.rater_id == rater]
        rater_scores: dict[str, list[int]] = {}
        for e in rater_entries:
            for dim, score in e.scores.items():
                rater_scores.setdefault(dim, []).append(score)
        per_rater[rater] = {dim: sum(vals) / len(vals) for dim, vals in rater_scores.items()}

    return HumanEvalReport(
        entries_count=len(entries),
        rater_count=len(raters),
        avg_scores=avg_scores,
        per_rater=per_rater,
    )
