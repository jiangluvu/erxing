"""Layer 3: A/B 对比评测 — 核心决策层。

Pairwise LLM-as-judge。只输出 A better / B better / Tie。
禁止单独打分。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from evaluation.config import EVAL_MODEL, AB_SIGNIFICANCE_THRESHOLD

# Layer 3 A/B pairwaise 评测 prompt
AB_JUDGE_SYSTEM = """你是一个播客质量评审专家。给定同一篇文章生成的两个播客对话脚本，请从以下三个维度判断哪个更好，或平局。

维度说明：
1. 整体自然度：对话是否自然流畅，像真实的人在聊天，而不是在念稿
2. 车载场景适配：句子是否简短易懂，信息密度适中，适合驾车时收听
3. 信息密度合理性：涵盖的信息量是否恰到好处，既不显得空洞也不过度堆砌

请严格按 JSON 格式输出，不要多余内容：
{
  "overall_naturalness": "A"|"B"|"tie",
  "car_scene_fit": "A"|"B"|"tie",
  "info_density_reasonableness": "A"|"B"|"tie",
  "overall_reason": "一句话总结判断理由"
}"""


@dataclass
class ABDimensionResult:
    dimension: str
    a_wins: int = 0
    b_wins: int = 0
    ties: int = 0

    @property
    def total(self) -> int:
        return self.a_wins + self.b_wins + self.ties

    @property
    def a_win_rate(self) -> float:
        return self.a_wins / self.total if self.total > 0 else 0.0

    @property
    def b_win_rate(self) -> float:
        return self.b_wins / self.total if self.total > 0 else 0.0

    @property
    def is_significant(self) -> bool:
        return max(self.a_win_rate, self.b_win_rate) >= AB_SIGNIFICANCE_THRESHOLD

    @property
    def winner(self) -> str:
        if not self.is_significant:
            return "tie"
        return "A" if self.a_win_rate > self.b_win_rate else "B"

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "a_wins": self.a_wins,
            "b_wins": self.b_wins,
            "ties": self.ties,
            "a_win_rate": round(self.a_win_rate, 3),
            "b_win_rate": round(self.b_win_rate, 3),
            "is_significant": self.is_significant,
            "winner": self.winner,
        }


@dataclass
class ABReport:
    version_a: str = ""
    version_b: str = ""
    results: list[ABDimensionResult] = field(default_factory=list)
    comparisons_total: int = 0

    @property
    def overall_verdict(self) -> str:
        """综合判断哪个版本更好。"""
        if not self.results:
            return "no_data"
        wins = {"A": 0, "B": 0, "tie": 0}
        for r in self.results:
            if r.is_significant:
                wins[r.winner] = wins.get(r.winner, 0) + 1
        if wins["A"] > wins["B"] and wins["A"] >= 2:
            return "A better"
        elif wins["B"] > wins["A"] and wins["B"] >= 2:
            return "B better"
        return "No clear winner"

    def to_dict(self) -> dict:
        return {
            "version_a": self.version_a,
            "version_b": self.version_b,
            "comparisons_total": self.comparisons_total,
            "overall_verdict": self.overall_verdict,
            "dimensions": [r.to_dict() for r in self.results],
        }


# A/B 请求默认维度
AB_DIMENSIONS = ["overall_naturalness", "car_scene_fit", "info_density_reasonableness"]


def _dialogue_to_text(dialogue: list[dict]) -> str:
    return "\n".join(f"{d['speaker']}：{d['text']}" for d in dialogue)


def _get_api_key() -> str:
    import os
    from dotenv import load_dotenv
    load_dotenv()
    return os.environ.get("ZHI_API_KEY") or ""


def _call_openai(system: str, content: str) -> str:
    """通过 OpenAI 兼容接口调用 EVAL_MODEL。"""
    import requests as req

    payload = {
        "model": EVAL_MODEL,
        "max_tokens": 512,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
    }
    resp = req.post(
        "https://api.zhizengzeng.com/v1/chat/completions",
        json=payload,
        headers={
            "Authorization": f"Bearer {_get_api_key()}",
            "Content-Type": "application/json",
        },
        timeout=60,
    )
    data = resp.json()
    choices = data.get("choices", [])
    if choices:
        return choices[0]["message"]["content"]
    raise ValueError("No response from eval model")


def _judge_pair(
    source_text: str,
    dialogue_a: list[dict],
    dialogue_b: list[dict],
) -> Optional[dict]:
    """对一对 A/B 对话执行 LLM pairwise 判断。"""
    text_a = _dialogue_to_text(dialogue_a)
    text_b = _dialogue_to_text(dialogue_b)

    prompt = f"""【原文】
{source_text[:1500]}

【版本A】
{text_a}

【版本B】
{text_b}

请判断哪个版本更好。"""

    try:
        raw = _call_openai(AB_JUDGE_SYSTEM, prompt)
        if raw:
            result = json.loads(raw.strip())
            for dim in AB_DIMENSIONS:
                if result.get(dim) not in ("A", "B", "tie"):
                    result[dim] = "tie"
            return result
    except Exception:
        return None


def run_ab_comparison(
    paired_data: list[dict],
    version_a: str = "A",
    version_b: str = "B",
    client=None,
) -> ABReport:
    """运行 A/B 对比。

    参数:
        paired_data: [{source_text, dialogue_a, dialogue_b}, ...]
        version_a: A 版本标签
        version_b: B 版本标签
        client: 保留参数，不再使用
    """
    dim_results = {dim: ABDimensionResult(dimension=dim) for dim in AB_DIMENSIONS}

    for item in paired_data:
        judgment = _judge_pair(
            item["source_text"],
            item["dialogue_a"],
            item["dialogue_b"],
        )
        if not judgment:
            continue
        for dim in AB_DIMENSIONS:
            winner = judgment.get(dim, "tie")
            if winner == "A":
                dim_results[dim].a_wins += 1
            elif winner == "B":
                dim_results[dim].b_wins += 1
            else:
                dim_results[dim].ties += 1

    report = ABReport(
        version_a=version_a,
        version_b=version_b,
        results=list(dim_results.values()),
        comparisons_total=len(paired_data),
    )
    return report
