"""JD -> 结构化能力项。有 Key 走 LLM，无 Key 走规则基线。"""

from __future__ import annotations

import re

from .llm import LLM, LLMError
from .schema import TAXONOMY, Requirement, canonical_hits

SECTION_MARKERS = {
    "job": ["岗位职责", "工作职责", "工作内容", "职位描述", "你将", "职责"],
    "must": ["任职要求", "岗位要求", "任职资格", "基础要求", "要求"],
    "nice": ["优先条件", "加分项", "优先", "bonus"],
}

STRONG_WORDS = ["精通", "深入", "独立", "主导", "熟练掌握", "扎实", "闭环", "从0到1", "从 0 到 1"]


def _detect_section(line: str) -> str | None:
    stripped = line.strip(" #*【】[]：:　")
    if len(stripped) > 30:
        return None  # 太长不可能是纯标题
    for section, markers in SECTION_MARKERS.items():
        for m in markers:
            if m in stripped:
                leftover = stripped.replace(m, "").strip(" ：:，、.。")
                # 只有当标题词几乎占满整行时，才把它当成分节标题；
                # 像"要求熟悉 Python 编程"这种带着内容的句子要当成要求本身。
                if len(leftover) <= 4:
                    return section
                break
    return None


def _split_sections(text: str) -> list[tuple[str, str]]:
    """把 JD 切成 (section, line) 列表。"""
    out: list[tuple[str, str]] = []
    current = "must"
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#") or line.startswith("【") and len(line) < 24:
            continue  # 标题行不是要求，别让它变成依据
        marker = _detect_section(line)
        if marker:
            current = marker
            continue
        if len(line) < 6:
            continue  # 导航行/编号残片
        out.append((current, line))
    return out


def _weight_for(section: str, line: str) -> int:
    if section == "nice":
        return 1
    if section == "job":
        return 2
    strong = any(w in line for w in STRONG_WORDS)
    return 3 if strong else 2


def extract_title(text: str) -> str:
    for line in text.splitlines():
        line = line.strip(" #*")
        if line and len(line) <= 40:
            return line
    return "目标岗位"


def extract_by_rules(jd_text: str) -> list[Requirement]:
    """无 LLM 时的基线：按词表命中 + 章节权重抽取能力项。"""
    best: dict[str, Requirement] = {}
    for section, line in _split_sections(jd_text):
        weight = _weight_for(section, line)
        for key, words in canonical_hits(line).items():
            existing = best.get(key)
            if existing is None or weight > existing.weight:
                best[key] = Requirement(
                    key=key,
                    label=TAXONOMY[key]["label"],
                    weight=weight,
                    kind="nice" if weight == 1 else "must",
                    quote=line[:120],
                    section=section,
                )
    return sorted(best.values(), key=lambda r: -r.weight)


EXTRACT_SYSTEM = """你是资深 AI 产品经理招聘官。把 JD 拆成互不重叠的能力项。

只输出 JSON：
{"requirements":[{"key":"python|llm_basics|prompt_eng|rag|agent|function_calling|framework|coding_tools|product_sense|data_analysis|eval|engineering|communication|domain 之一","label":"中文能力名，不超过 12 字","weight":1|2|3,"kind":"must|nice","quote":"JD 原文片段，不超过 60 字"}]}

规则：
- key 只能从给定枚举里选，无法归类的并入最接近的一项，不要发明新 key。
- weight: 3=核心硬门槛（精通/独立负责/必须），2=一般要求，1=优先/加分。
- 同一 key 只出现一次，取权重最高的那条依据。
- 只输出 JSON，不要解释。"""


def extract_by_llm(jd_text: str, llm: LLM) -> list[Requirement]:
    data = llm.json(EXTRACT_SYSTEM, f"JD 原文：\n\n{jd_text}")
    items = []
    for item in data.get("requirements", []):
        key = item.get("key", "")
        if key not in TAXONOMY:
            continue
        weight = int(item.get("weight", 2))
        weight = min(3, max(1, weight))
        items.append(
            Requirement(
                key=key,
                label=item.get("label") or TAXONOMY[key]["label"],
                weight=weight,
                kind=item.get("kind") or ("nice" if weight == 1 else "must"),
                quote=(item.get("quote") or "")[:120],
            )
        )
    if not items:
        raise LLMError("LLM 未抽取到有效能力项")
    return sorted(items, key=lambda r: -r.weight)


def extract_requirements(jd_text: str, llm: LLM | None = None) -> tuple[list[Requirement], str]:
    if llm and llm.available:
        try:
            return extract_by_llm(jd_text, llm), "llm"
        except (LLMError, KeyError, ValueError):
            pass
    return extract_by_rules(jd_text), "rule"
