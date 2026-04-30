"""Layer 1: Benchmark 数据模型与加载器。"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

from evaluation.config import BENCHMARK_DIR


@dataclass
class BenchmarkItem:
    id: str
    category: Literal["short_news", "mid_article", "long_article", "car_scene"]
    title: str
    source_text: str
    char_count: int
    variant: Literal["short", "standard", "long"] = "standard"
    description: str = ""
    source_url: str = ""
    expected_key_points: list[str] = field(default_factory=list)

    @property
    def is_deprecated(self) -> bool:
        return False


@dataclass
class BenchmarkSet:
    version: str
    items: list[BenchmarkItem]

    @classmethod
    def load(cls, version: str = "v1") -> "BenchmarkSet":
        path = BENCHMARK_DIR / f"benchmark_{version}.json"
        if not path.exists():
            raise FileNotFoundError(f"Benchmark file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = [BenchmarkItem(**item) for item in data["items"]]
        return cls(version=data["version"], items=items)

    def filter_by_category(self, category: str) -> list[BenchmarkItem]:
        return [i for i in self.items if i.category == category and not i.is_deprecated]

    def by_id(self, item_id: str) -> Optional[BenchmarkItem]:
        for i in self.items:
            if i.id == item_id:
                return i
        return None

    def __len__(self) -> int:
        return len(self.items)
