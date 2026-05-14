"""Layer 4: AI 自动评测 — 质量筛查，不参与决策。

用途：快速发现明显质量问题。
维度：content_accuracy, dialogue_naturalness, scene_fit
约束：不参与 MVP 评分，不参与 A/B 决策。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from evaluation.config import EVAL_MODEL


# Layer 4 评测 prompt — 仅 3 维度，与运行时评估分离
LAYER4_EVAL_SYSTEM = """你是一个严格且客观的播客质量评估专家。请从以下三个维度对生成的对话进行评分（1-5分），
并严格按照JSON格式输出。

⚠️ 要求严格评分：
- 5分 = 完美，几乎没有改进空间（极少使用）
- 4分 = 很好，但有小瑕疵
- 3分 = 及格，有明显可改进之处 ← 这是大多数合格对话的基准分
- 2分 = 较差，多个维度存在问题
- 1分 = 很差，基本不可用

评分维度：

1. content_accuracy（内容准确性）：
   对话内容是否准确反映了原文的核心观点，有没有编造事实或偏离主题。
   5分=精准覆盖所有核心观点，无任何偏离
   3分=覆盖大部分观点，有少量偏离或添加了原文没有的细节
   1分=严重偏离原文或编造大量内容

2. dialogue_naturalness（对话自然度）：
   对话是否自然流畅，口语化程度高，角色区分鲜明，有真实互动感。
   5分=就像真实朋友在聊天，有自然的插话、附和、语气词
   3分=较为自然但偶尔像念稿，对话节奏不够真实
   1分=机械化、书面化、完全不自然

3. scene_fit（场景适配性）：
   对话是否适合伴随式收听场景——句子简短易懂，信息密度适中，节奏舒服。
   5分=非常适合伴随式收听，句子简短、节奏舒服
   3分=基本适合，偶有长句或信息过密
   1分=不适合伴随式收听场景

记住：客观、严格、有区分度。不要全部打5分。"""


@dataclass
class AutoEvalResult:
    content_accuracy: float = 3.0
    dialogue_naturalness: float = 3.0
    scene_fit: float = 3.0
    item_id: str = ""

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "content_accuracy": self.content_accuracy,
            "dialogue_naturalness": self.dialogue_naturalness,
            "scene_fit": self.scene_fit,
        }


_API_KEY = None


def _get_api_key() -> str:
    global _API_KEY
    if _API_KEY is None:
        from dotenv import load_dotenv
        load_dotenv()
        _API_KEY = os.environ.get("ZHI_API_KEY") or ""
    return _API_KEY


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


def auto_evaluate(
    article: str,
    dialogue: list[dict],
    item_id: str = "",
) -> AutoEvalResult:
    """调用 EVAL_MODEL 对单条对话做 3 维度评分。"""
    dialogue_text = "\n".join(f"{d['speaker']}：{d['text']}" for d in dialogue)
    prompt = f"【原文】\n{article[:1500]}\n\n【对话】\n{dialogue_text}\n\n请评分。"

    try:
        raw = _call_openai(LAYER4_EVAL_SYSTEM, prompt)
        if raw:
            scores = json.loads(raw.strip())
            return AutoEvalResult(
                item_id=item_id,
                content_accuracy=max(1, min(5, scores.get("content_accuracy", 3))),
                dialogue_naturalness=max(1, min(5, scores.get("dialogue_naturalness", 3))),
                scene_fit=max(1, min(5, scores.get("scene_fit", 3))),
            )
    except Exception:
        pass

    return AutoEvalResult(item_id=item_id)


def batch_auto_evaluate(results: list[dict]) -> list[AutoEvalResult]:
    """批量评测。results 是 [{item_id, source_text, dialogue}, ...]"""
    outputs = []
    for r in results:
        result = auto_evaluate(r["source_text"], r["dialogue"], item_id=r.get("item_id", ""))
        outputs.append(result)
    return outputs
