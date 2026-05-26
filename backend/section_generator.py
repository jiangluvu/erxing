"""Phase 1: Structure-first Section Generator.

Implements the Structure-first Hybrid RAG approach:
1. _build_global_outline() - Two-phase outline generation
2. Section-based text splitting with robust source anchoring
3. Section-level dialogue generation with context passing + new prompt template

split_strategy="section" in generate_structured_dialogue dispatches here.
"""

import json, re, time, math
from pathlib import Path
from typing import Any

# ── imports from app ──────────────────────────────────────────────────
from app import (
    _call_ai,
    logger,
    ZHI_MODEL,
    _check_role_consistency,
    parse_dialogue,
    validate_dialogue_format,
    _deduplicate_overlap,
    evaluate_dialogue,
    _write_metrics,
    METRICS_GENERATION_PATH,
    _duration_hint,
    _FORMAT_EXAMPLE,
    _split_text_chunks,
    _semantic_split_chunks,
)
from datetime import datetime, timezone
import uuid

# ── Prompt templates ──────────────────────────────────────────────────

OUTLINE_SYSTEM_V2 = """你是一个文章结构分析师。请按以下步骤分析文章并生成结构化的全局大纲。

步骤1：先理解全文的主旨，用一句话概括 global_topic
步骤2：提取 5-10 个贯穿全文的核心关键词作为 global_keywords
步骤3：识别文章的自然章节（section）边界，按原文逻辑划分

对每个 section，你需要：
1. title：用原文中的核心短语作为章节标题
2. summary：用一句话概括本章核心内容（必须基于原文，不要编造）
3. keywords：3-5 个本章关键词（选择未来其他 section 可能会引用的概念/术语）
4. starts_with：从原文中**逐字复制**本章开始的第一个完整句子作为锚点

重要约束：
- 每个 section 的 starts_with 必须是原文中逐字复制的句子，不能改写
- Global keywords 不要太多，只保留最核心的 5-10 个
- Section keywords 选择"未来其他 section 可能引用"的概念，不是本章所有重要词
- 短文本（<3000字）可以只分 2-3 个 section，不要强行多分

输出格式严格为 JSON，不要输出任何额外文字：
```json
{
  "global_topic": "...",
  "global_keywords": ["...", "..."],
  "sections": [
    {
      "title": "...",
      "summary": "...",
      "keywords": ["...", "..."],
      "starts_with": "逐字复制原文中的句子..."
    }
  ]
}
```"""

OUTLINE_MERGE_SYSTEM = """你是一个文章结构分析师。以下是一篇长文的不同段落分别提取的局部大纲。

请将它们合并为一个完整的全局大纲：
1. 合并重复的 section，保留更完整的版本
2. 重新排列 section 顺序，使其符合原文逻辑
3. 重新提取 global_keywords（取各段最重要的 5-10 个）
4. 确保合并后的大纲完整覆盖全文

输出格式严格为 JSON：
```json
{
  "global_topic": "...",
  "global_keywords": ["...", "..."],
  "sections": [
    {
      "title": "...",
      "summary": "...",
      "keywords": ["...", "..."],
      "starts_with": "逐字复制原文中的句子..."
    }
  ]
}
```"""

SECTION_SYSTEM = """你正在生成一段双人播客对话。

## 核心约束
- **只基于原文生成**，不允许补充任何外部知识
- 如果原文没有提及某个细节，允许对话中说"这一点原文没有明确说明"，不要强行编造
- 保持自然对话感，是"两个人在聊这篇文章"，不是"两个人在念稿"
- **必须覆盖本章节关键词中的核心概念**，不要遗漏

## 角色分工

### 主持（框架梳理者）
- 职责：串联、总结、建立论点之间的逻辑连接，引导话题转换
- 语言习惯："你看""换句话说""这里面有几个层面"
- 禁忌：不使用反问句，不说"说实话""我有点好奇"

### 嘉宾（细节追问者）
- 职责：展开分析、提供见解、从听众角度追问细节
- 语言习惯："说实话""我有点好奇""那岂不是""等一下"
- 禁忌：不做长篇大论的学术总结，不说"综上所述"

**角色锚点：**
1. 主持的功能是"总结+连接"，嘉宾的功能是"展开+追问"，不可互换
2. 主持绝对不说"说实话""我有点好奇"；嘉宾绝对不说"你看""换句话说"

## 全局上下文
全文主题：{global_topic}
核心主题词：{global_keywords}
当前位置：第 {current_section} 部分，共 {total_sections} 部分

## 当前章节
章节标题：{section_title}
章节作用：{section_summary}
章节关键词：{section_keywords}

## 当前对话状态：{section_state}
- **Opening**：嘉宾用场景/问题开场，主持点出话题价值。不深入细节，引发兴趣为主。
- **Exploration**：主持梳理框架，嘉宾追问关键概念。覆盖关键词，建立认知基础。
- **Deep Dive**：嘉宾深入追问细节，主持提供具体分析。信息密度高，允许较长分析句。
- **Reflection**：主持总结核心要点，嘉宾反思评价。语气放缓，适合用[沉思]。

## 前文衔接
上一部分的结论摘要：
{previous_conclusion}

## 需要处理的原文
{current_source}

{optional_retrieved}

## 情绪标签（必须轮换，不可连续同标签）
- **平静**（默认，占 40-50%）：自然平稳的讨论
- **兴奋**（每 section 至少 1 次）：数据惊人、重大突破时使用
- **疑问**（每 section 至少 1 次）：提问、质疑、表达不理解时使用
- **沉思**（每 section 至少 1 次）：深入分析、总结教训、回顾历史时使用
- 同一情绪**禁止**连续使用超过 2 轮

## 输出要求
- 每轮输出主持一句 + 嘉宾一句
- **开场：** 嘉宾先开口（用提问或场景引发兴趣），主持接话（点出话题价值）
- **结尾：** 主持收尾，包含总结词 + 自然结束语
- 每行格式：`主持[情绪]：...` 或 `嘉宾[情绪]：...`
- 说完一轮后自然进入下一轮
- 不要输出任何额外的说明文字
- 不要编号"""


# ── Outline generation ───────────────────────────────────────────────

def _build_global_outline(clean_text: str) -> dict:
    """Two-phase outline generation.

    Phase 1: For texts ≤ 15000 chars → single LLM call.
    Phase 2: For longer texts → split → local outlines → merge.
    """
    if len(clean_text) <= 15000:
        return _build_outline_single(clean_text)
    else:
        return _build_outline_merge(clean_text)


def _build_outline_single(text: str) -> dict:
    """Single-phase outline for texts that fit in context."""
    try:
        prompt = f"原文如下：\n\n{text}\n\n请分析并生成结构化全局大纲。"
        raw = _call_ai(OUTLINE_SYSTEM_V2, prompt, temperature=0.2)
        outline = _parse_outline_json(raw)
        if outline and outline.get("sections"):
            return outline
        # Fallback: try to extract JSON from markdown
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
        if json_match:
            try:
                outline = json.loads(json_match.group(1))
                if outline and outline.get("sections"):
                    return outline
            except json.JSONDecodeError:
                pass
    except Exception as e:
        logger.error(f"Outline generation failed: {e}")
    # Last resort: one-section fallback outline
    logger.warning("Outline parsing failed, using fallback single-section outline")
    return {
        "global_topic": "全文讨论",
        "global_keywords": [],
        "sections": [{
            "title": "全文",
            "summary": "全文核心内容",
            "keywords": [],
            "starts_with": text[:50],
        }]
    }


def _build_outline_merge(text: str) -> dict:
    """Two-phase outline for long texts: chunk → local outline → merge."""
    try:
        chunks = _split_text_chunks(text, chunk_size=6000, overlap=300)
    except Exception as e:
        logger.error(f"Outline merge chunking failed: {e}")
        return _build_outline_single(text[:15000])
    logger.info(f"Outline merge: split {len(text)} chars into {len(chunks)} chunks")

    local_outlines = []
    for i, chunk in enumerate(chunks):
        try:
            logger.info(f"  Extracting local outline chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")
            prompt = f"以下是长文的一个段落（第{i+1}段，共{len(chunks)}段）：\n\n{chunk}\n\n请分析这段的结构并生成局部大纲。"
            raw = _call_ai(OUTLINE_SYSTEM_V2, prompt, temperature=0.2)
            local = _parse_outline_json(raw)
            if local and local.get("sections"):
                local_outlines.append(local)
        except Exception as e:
            logger.warning(f"Local outline chunk {i+1} failed: {e}, skipping")

    if not local_outlines:
        return _build_outline_single(text[:15000])

    if len(local_outlines) == 1:
        return local_outlines[0]

    # Merge local outlines
    try:
        merge_input = json.dumps(local_outlines, ensure_ascii=False, indent=2)
        prompt = f"以下是同一篇文章不同段落的局部大纲，请合并为一个完整的全局大纲：\n\n{merge_input}"
        raw = _call_ai(OUTLINE_MERGE_SYSTEM, prompt, temperature=0.2)
        merged = _parse_outline_json(raw)
        if merged and merged.get("sections"):
            return merged
    except Exception as e:
        logger.warning(f"Outline merge failed: {e}")

    # Fallback: use first local outline as fallback
    logger.warning("Outline merge failed, using first chunk's outline as fallback")
    return local_outlines[0]


def _parse_outline_json(raw: str) -> dict | None:
    """Parse JSON outline from LLM output, handling markdown fences."""
    # Try direct JSON parse
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    # Try extracting from markdown ```json ... ```
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    return None


# ── Section-to-text mapping ──────────────────────────────────────────

def _map_sections_to_text(clean_text: str, outline: dict) -> list[tuple[str, dict]]:
    """Map outline sections back to original text positions.

    Uses verbatim starts_with matching, with robust fallbacks.
    Returns list of (section_text, section_info).
    """
    sections = outline.get("sections", [])
    if not sections:
        return [(clean_text, {"title": "全文", "summary": "", "keywords": []})]

    # Step 1: Find start positions for each section by matching starts_with
    boundaries = []
    for i, section in enumerate(sections):
        anchor = section.get("starts_with", "").strip()
        pos = -1
        if anchor and len(anchor) >= 10:
            pos = clean_text.find(anchor)
            if pos == -1:
                # Try first 30 chars (partial match for long anchors)
                pos = clean_text.find(anchor[:30])
                if pos == -1:
                    # Try first 15 chars
                    pos = clean_text.find(anchor[:15])
        boundaries.append({
            "section": section,
            "start_pos": pos,
            "anchor": anchor,
        })

    # Step 2: Fill in missing positions
    # For sections with no anchor match, interpolate between known boundaries
    known = [b for b in boundaries if b["start_pos"] >= 0]
    if known:
        # Sort known boundaries by position
        known.sort(key=lambda b: b["start_pos"])
        # Assign proportional positions for unanchored sections
        unanchored_indices = [i for i, b in enumerate(boundaries) if b["start_pos"] < 0]
        for i in unanchored_indices:
            # Find nearest known before and after
            before = [b for b in known if boundaries.index(b) < i]
            after = [b for b in known if boundaries.index(b) > i]
            if before and after:
                prev_known = max(before, key=lambda b: boundaries.index(b))
                next_known = min(after, key=lambda b: boundaries.index(b))
                prev_idx = boundaries.index(prev_known)
                next_idx = boundaries.index(next_known)
                ratio = (i - prev_idx) / (next_idx - prev_idx + 1)
                span = next_known["start_pos"] - prev_known["start_pos"]
                boundaries[i]["start_pos"] = prev_known["start_pos"] + int(span * ratio)
            elif before:
                boundaries[i]["start_pos"] = before[-1]["start_pos"] + 200
            elif after:
                boundaries[i]["start_pos"] = after[0]["start_pos"] - 200

    # Step 3: Sort by position, build sections with text ranges
    valid = [(i, b) for i, b in enumerate(boundaries) if b["start_pos"] >= 0]
    valid.sort(key=lambda x: x[1]["start_pos"])

    result = []
    for idx, (orig_i, b) in enumerate(valid):
        start = b["start_pos"]
        if idx + 1 < len(valid):
            end = valid[idx + 1][1]["start_pos"]
        else:
            end = len(clean_text)

        section_text = clean_text[start:end].strip()
        if len(section_text) < 50 and idx > 0:
            # Too short, merge with previous section
            continue

        section_info = {
            "section_id": orig_i + 1,
            "title": b["section"].get("title", f"第{orig_i+1}部分"),
            "summary": b["section"].get("summary", ""),
            "keywords": b["section"].get("keywords", []),
        }
        result.append((section_text, section_info))

    if not result:
        # Complete fallback: split text evenly by section count
        logger.warning("No sections mapped, falling back to even split")
        total = len(sections)
        section_len = len(clean_text) // max(total, 1)
        for i, section in enumerate(sections):
            start = i * section_len
            end = (i + 1) * section_len if i < total - 1 else len(clean_text)
            text = clean_text[start:end].strip()
            if text:
                result.append((text, {
                    "section_id": i + 1,
                    "title": section.get("title", f"第{i+1}部分"),
                    "summary": section.get("summary", ""),
                    "keywords": section.get("keywords", []),
                }))

    return result


# ── Section-by-section generation ─────────────────────────────────────

def _extract_conclusion(dialogue: list[dict]) -> str:
    """Extract host's closing statement as a concise conclusion."""
    if not dialogue:
        return ""
    for d in reversed(dialogue):
        if d.get("speaker") == "主持":
            text = d.get("text", "").strip()
            if text and len(text) > 10:
                return text
    return dialogue[-1].get("text", "")[-50:] if dialogue else ""


def _determine_section_state(section_index: int, total_sections: int, keywords: list[str]) -> str:
    """Determine conversation state based on section position and content density."""
    if total_sections <= 1:
        return "exploration"
    if section_index == 0:
        return "opening"
    if section_index >= total_sections - 1:
        return "reflection"
    if len(keywords) >= 4:
        return "deep_dive"
    return "exploration"


SECTION_GENERATION_INSTRUCTION = "请严格按照上述要求和格式，生成一段双人播客对话。"


def _build_section_prompt(
    section_text: str,
    section_info: dict,
    outline: dict,
    section_index: int,
    total_sections: int,
    previous_conclusion: str,
    retrieved_context: str = "",
) -> str:
    """Build the generation prompt for a single section."""
    global_topic = outline.get("global_topic", "")
    global_keywords = outline.get("global_keywords", [])
    section_title = section_info.get("title", "")
    section_summary = section_info.get("summary", "")
    section_keywords = section_info.get("keywords", [])
    section_state = _determine_section_state(section_index - 1, total_sections, section_keywords)

    prompt = SECTION_SYSTEM.format(
        global_topic=global_topic or "（原文讨论）",
        global_keywords=", ".join(global_keywords) if global_keywords else "（无）",
        current_section=section_index,
        total_sections=total_sections,
        section_title=section_title or f"第{section_index}部分",
        section_summary=section_summary or "（本章核心内容）",
        section_keywords=", ".join(section_keywords) if section_keywords else "（无）",
        section_state=section_state,
        previous_conclusion=previous_conclusion or "（这是第一部分，没有前文）",
        current_source=section_text,
        optional_retrieved=retrieved_context,
    )
    return prompt


def generate_by_section(
    clean_text: str,
    model: str | None = None,
    duration: str | None = None,
) -> tuple[list[dict], dict, int, list[dict] | None]:
    """Section-by-section generation with context passing.

    Returns (dialogue, eval_scores, llm_time_ms, section_metadata).
    section_metadata is a list of dicts with section info and turn ranges, or None if fallback.
    """
    t0 = time.time()

    # Phase 1: Build global outline
    logger.info("Phase 1: Building global outline...")
    outline = _build_global_outline(clean_text)
    logger.info(f"  Outline: {len(outline.get('sections', []))} sections, "
                f"topic='{outline.get('global_topic', '')[:50]}'")

    # Phase 2: Map sections to text
    logger.info("Phase 2: Mapping sections to text...")
    sections = _map_sections_to_text(clean_text, outline)
    logger.info(f"  Mapped {len(sections)} sections from {len(outline.get('sections', []))} outline entries")

    if not sections:
        logger.error("No sections mapped, falling back to single-shot")
        dialogue, scores, elapsed = _fallback_single_shot(clean_text, model, duration)
        return dialogue, scores, elapsed, None

    # Phase 3: Generate dialogue section by section
    logger.info(f"Phase 3: Generating {len(sections)} sections...")
    all_dialogue = []
    chunk_dialogues = []
    section_metadata = []
    previous_conclusion = ""
    total_llm_time = 0

    for idx, (section_text, section_info) in enumerate(sections):
        section_t0 = time.time()

        # Track turn range for this section
        turn_start = len(all_dialogue)

        # Handle long sections (>6000 chars) by sub-chunking
        if len(section_text) > 6000:
            dialogues = _generate_long_section(
                section_text, section_info, outline,
                idx, len(sections),
                previous_conclusion,
                model, duration,
            )
            section_dialogue = dialogues
        else:
            # Single-shot section generation
            prompt = _build_section_prompt(
                section_text, section_info, outline,
                idx + 1, len(sections),
                previous_conclusion,
            )

            section_dialogue = []
            for attempt in range(1, 3):
                try:
                    # Dynamic temperature: opening more creative, final more precise
                    if idx == 0:
                        temperature = 0.7
                    elif idx == len(sections) - 1:
                        temperature = 0.4
                    else:
                        temperature = 0.6
                    raw = _call_ai(system=SECTION_SYSTEM + "\n\n" + prompt, content=SECTION_GENERATION_INSTRUCTION, model=model, temperature=temperature)
                    parsed = parse_dialogue(raw)
                    has_speaker, format_valid = validate_dialogue_format(parsed)
                    if parsed and len(parsed) >= 2 and format_valid:
                        section_dialogue = parsed
                        break
                    logger.warning(f"  Section {idx+1} attempt {attempt}: invalid format, retrying...")
                except Exception as e:
                    logger.warning(f"  Section {idx+1} attempt {attempt} failed: {e}")

        section_time = int((time.time() - section_t0) * 1000)
        total_llm_time += section_time

        if not section_dialogue:
            logger.warning(f"  Section {idx+1} produced no dialogue, skipping")
            continue

        _check_role_consistency(section_dialogue)

        # Deduplicate overlap with previous section
        if all_dialogue:
            section_dialogue = _deduplicate_overlap(all_dialogue, section_dialogue)

        all_dialogue.extend(section_dialogue)
        chunk_dialogues.append(section_dialogue)

        # Track section metadata
        turn_end = len(all_dialogue)
        section_metadata.append({
            "section_id": section_info.get("section_id", idx + 1),
            "title": section_info.get("title", f"第{idx+1}部分"),
            "summary": section_info.get("summary", ""),
            "keywords": section_info.get("keywords", []),
            "turn_start": turn_start,
            "turn_end": turn_end,
        })

        # Extract conclusion for next section
        previous_conclusion = _extract_conclusion(section_dialogue)

        logger.info(f"  Section {idx+1}/{len(sections)}: {len(section_dialogue)} turns ({section_time}ms)")

    if not all_dialogue:
        logger.error("No dialogue generated from any section, falling back to single-shot")
        return _fallback_single_shot(clean_text, model, duration)

    elapsed = int((time.time() - t0) * 1000)
    logger.info(f"  Total: {len(all_dialogue)} turns from {len(sections)} sections ({elapsed}ms)")

    # Evaluate
    eval_scores = evaluate_dialogue(clean_text, all_dialogue)

    # Write metrics
    output_length = sum(len(d["text"]) for d in all_dialogue)
    text_stats = _compute_text_stats(all_dialogue)
    role_violations = _check_role_consistency(all_dialogue)
    _write_metrics(METRICS_GENERATION_PATH, {
        "request_id": str(uuid.uuid4()),
        "session_id": None,
        "model": model or ZHI_MODEL,
        "prompt_mode": "section",
        "split_strategy": "section",
        "chunk_count": len(sections),
        "total_turns": len(all_dialogue),
        "output_length_chars": output_length,
        "expansion_ratio": round(output_length / max(1, len(clean_text)), 4),
        "llm_time_ms": elapsed,
        "keyword_coverage": eval_scores.get("keyword_coverage"),
        "faithfulness": eval_scores.get("faithfulness"),
        "role_distinction": eval_scores.get("role_distinction"),
        "distinct_1": eval_scores.get("distinct_1"),
        "distinct_2": eval_scores.get("distinct_2"),
        "coherence_score": eval_scores.get("coherence_score"),
        "format_valid": True,
        "has_speaker_format": True,
        "role_violation_rate": round(role_violations["total"] / max(1, len(all_dialogue)), 4),
        "num_sections": len(sections),
        **text_stats,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return all_dialogue, eval_scores, elapsed, section_metadata


def _generate_long_section(
    section_text: str,
    section_info: dict,
    outline: dict,
    section_index: int,
    total_sections: int,
    previous_conclusion: str,
    model: str | None = None,
    duration: str | None = None,
) -> list[dict]:
    """Handle a section longer than 6000 chars by sub-chunking."""
    sub_chunks = _split_text_chunks(section_text, chunk_size=3000, overlap=300)
    logger.info(f"    Long section ({len(section_text)} chars) split into {len(sub_chunks)} sub-chunks")

    all_dialogue = []
    sub_previous_conclusion = previous_conclusion

    for sub_idx, sub_text in enumerate(sub_chunks):
        # Build a sub-prompt that anchors to the section context
        section_keywords = section_info.get("keywords", [])
        section_state = _determine_section_state(section_index, total_sections, section_keywords)
        prompt = SECTION_SYSTEM.format(
            global_topic=outline.get("global_topic", ""),
            global_keywords=", ".join(outline.get("global_keywords", [])),
            current_section=f"{section_index}.{sub_idx + 1}",
            total_sections=total_sections,
            section_title=section_info.get("title", f"第{section_index}部分"),
            section_summary=f"第{sub_idx + 1}/{len(sub_chunks)}子段",
            section_keywords=", ".join(section_keywords),
            section_state=section_state,
            previous_conclusion=sub_previous_conclusion or "（无）",
            current_source=sub_text,
            optional_retrieved="",
        )

        sub_dialogue = []
        for attempt in range(1, 3):
            try:
                raw = _call_ai(system=SECTION_SYSTEM + "\n\n" + prompt, content=SECTION_GENERATION_INSTRUCTION, model=model, temperature=0.5)
                parsed = parse_dialogue(raw)
                has_speaker, format_valid = validate_dialogue_format(parsed)
                if parsed and len(parsed) >= 2 and format_valid:
                    sub_dialogue = parsed
                    break
            except Exception:
                pass

        if not sub_dialogue:
            continue

        if all_dialogue:
            sub_dialogue = _deduplicate_overlap(all_dialogue, sub_dialogue)

        all_dialogue.extend(sub_dialogue)
        sub_previous_conclusion = _extract_conclusion(sub_dialogue)

    return all_dialogue


def _fallback_single_shot(
    text: str,
    model: str | None = None,
    duration: str | None = None,
) -> tuple[list[dict], dict, int]:
    """Fallback to simple recursive chunking if section generation fails."""
    from app import generate_structured_dialogue
    logger.warning("Section generation failed, falling back to recursive chunking")
    return generate_structured_dialogue(
        text, model=model, duration=duration,
        split_strategy="original", prompt_mode="original",
    )


def _compute_text_stats(dialogue: list[dict]) -> dict:
    """Compute text-level stats for metrics logging."""
    from app import _compute_text_stats as _cts
    return _cts(dialogue)