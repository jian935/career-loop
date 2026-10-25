"""把评估结果渲染成一份可以直接贴进作品集的 Markdown 报告。"""

from __future__ import annotations

import datetime as _dt
import re

from .match import fix_for, gaps, score
from .schema import STATUS_ICON, STATUS_LABEL, Assessment, Requirement

WEEK_PLAN = [
    ("第 1 周", "最小可跑通", "跑通链路，允许丑"),
    ("第 2 周", "有数据", "至少 20 条真实样本"),
    ("第 3 周", "有对比", "v1 vs v2 指标对照"),
    ("第 4 周", "有结论", "能说出为什么涨、为什么没涨"),
]


def _cell(text: str) -> str:
    """把一段任意文本压成**能安全放进 Markdown 表格**的一格。

    为什么必须这一个函数：report.md 的主体是表格，而表格是最脆的格式——
    一个 `|` 就多出一列、一个换行就把一行拆成两行，整张表立刻错位。

    以前只给 quote / evidence 做了替换，**label 漏了**。而 label 恰恰是最危险
    的来源：自定义能力项的标签是从 JD 原文抽出来的短语（"Java|Python|Go"
    这类技能罗列很常见），引擎不保证它不含管道符。
    """
    s = str(text or "")
    s = s.replace("|", "／")
    s = re.sub(r"\s*[\r\n]+\s*", " ", s)     # 换行会把一行表格拆成两行
    return s.strip()


def _inline(text: str) -> str:
    """非表格位置（标题、列表项）也要压成一行。

    这里不必管 `|`（表格外无害），但**换行必须处理**：Markdown 的列表项
    和标题是一行的结构，一个裸换行会把 `- **JD 依据**：…` 的下半句甩到
    列表外面去。这些文本来自 JD 原文，换行什么都有。
    """
    return re.sub(r"\s*[\r\n]+\s*", " ", str(text or "")).strip()


def _verdict(score_value: float) -> str:
    if score_value >= 75:
        return "强匹配，值得直接投，重点准备项目深挖"
    if score_value >= 60:
        return "基本匹配，补掉 1-2 个高权重缺口再投转化会明显变好"
    if score_value >= 40:
        return "有明显缺口，先补能力再投，否则大概率卡在简历关"
    return "当前不是这个岗位的主场，建议先换一个更贴近你现有证据的方向"


def build_roadmap(
    assessment: Assessment, top_n: int = 4
) -> list[tuple[str, Requirement, str]]:
    plan = []
    for idx, (req, status, _prio) in enumerate(gaps(assessment.requirements, assessment.matches)[:top_n]):
        week, goal, check = WEEK_PLAN[min(idx, len(WEEK_PLAN) - 1)]
        plan.append((week, req, f"{goal}；验收：{check}"))
    return plan


def render(assessment: Assessment, profile_name: str = "你的经历") -> str:
    reqs = assessment.requirements
    matches = assessment.matches
    total = len(reqs)
    counts = {"full": 0, "partial": 0, "missing": 0}
    for req in reqs:
        counts[matches.get(req.key).status if req.key in matches else "missing"] += 1

    score_value = score(reqs, matches)
    gap_list = gaps(reqs, matches)
    hard_gaps = [g for g in gap_list if g[0].weight == 3]

    lines: list[str] = []
    add = lines.append

    add(f"# {assessment.jd_title} · 匹配报告")
    add("")
    add(
        f"> 评估对象：{profile_name}　|　评估模式："
        f"{'LLM 语义匹配' if assessment.mode == 'llm' else '规则基线（未配置 API Key）'}　|　"
        f"{_dt.date.today().isoformat()}"
    )
    add("")
    add("## 一句话结论")
    add("")
    add(
        f"加权覆盖率 **{score_value}%**。{total} 项要求里 "
        f"{counts['full']} 项已覆盖、{counts['partial']} 项部分覆盖、{counts['missing']} 项缺失"
        + (f"，其中 **{len(hard_gaps)} 项是权重 3 的核心硬要求**。" if hard_gaps else "。")
    )
    add("")
    add(f"**判断：{_verdict(score_value)}**")
    add("")

    add("## 能力矩阵")
    add("")
    add("| 能力项 | 权重 | 状态 | JD 依据 | 你的证据 |")
    add("|---|---|---|---|---|")
    for req in reqs:
        hit = matches.get(req.key)
        status = hit.status if hit else "missing"
        quote = _cell(req.quote) or "—"
        add(
            f"| {_cell(req.label)} | {req.weight} | {STATUS_ICON[status]} {STATUS_LABEL[status]} "
            f"| {quote} | {(_cell(hit.evidence) if hit else '') or '—'} |"
        )
    add("")

    if gap_list:
        add("## 缺口（按 权重 × 严重度 排序）")
        add("")
        for idx, (req, status, prio) in enumerate(gap_list[:5], 1):
            hit = matches.get(req.key)
            add(f"### {idx}. {_inline(req.label)}（权重 {req.weight} · {STATUS_LABEL[status]} · 优先级 {prio}）")
            add("")
            if req.quote:
                add(f"- **JD 依据**：{_inline(req.quote)}")
            if hit and hit.note:
                add(f"- **为什么判为{STATUS_LABEL[status]}**：{hit.note}")
            add(f"- **怎么补**：{_inline(fix_for(req.key))}")
            add("")
    else:
        add("## 缺口")
        add("")
        add("没有识别到缺口。如果是规则基线模式，建议配置 API Key 用语义匹配复核一遍。")
        add("")

    roadmap = build_roadmap(assessment)
    if roadmap:
        add("## 4 周补强路线")
        add("")
        add("| 周次 | 目标能力 | 做什么 | 验收 |")
        add("|---|---|---|---|")
        for week, req, note in roadmap:
            add(f"| {week} | {_cell(req.label)} | {_cell(fix_for(req.key))} | {note.split('验收：')[-1]} |")
        add("")

    add("## 可直接写进简历的句子（把数字填上再抄）")
    add("")
    for req, _status, _prio in gap_list[:3]:
        add(f"- 围绕「{_inline(req.label)}」做一个最小项目：做了 ___ 条样本 / ___ 个用户，"
            f"指标从 ___ 提升到 ___，单次成本 ___ 元。")
    add("")
    add("---")
    add("")
    add("由 `career-loop` 生成。它只是一个起点——真正让别人 star 你的，是这份报告后面那个能跑的项目。")
    return "\n".join(lines)
