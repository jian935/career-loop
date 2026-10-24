# -*- coding: utf-8 -*-
"""Internship direction recommendation.

Scores a small, built-in set of internship postings against a profile, then
orders them by (goal match, weighted score). Also generates a cohort timeline.

The presets are deliberately short and generic: they are direction anchors, not
real openings. Pass --presets to use your own JSONL.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import matching

PRESETS: list[dict] = [
    {
        "id": "ai-pm",
        "title": "AI 产品经理实习生（AIGC）",
        "family": "ai",
        "tags": ["ai", "product"],
        "jd": """AI 产品经理实习生（AIGC 方向）
岗位职责
- 参与 AIGC 产品的需求调研、竞品分析与 PRD 撰写
- 跟进提示词模板与模型效果评测，输出迭代建议
任职要求
1. 熟悉大模型能力边界，有提示词工程实践
2. 能做用户访谈与数据分析
3. 每周到岗 4 天，实习 3 个月以上""",
    },
    {
        "id": "ai-ops",
        "title": "AI 产品运营实习生",
        "family": "ai",
        "tags": ["ai", "operations"],
        "jd": """AI 产品运营实习生
岗位职责
- 负责 AIGC 工具的用户运营与内容运营
- 策划活动，分析转化与留存数据
任职要求
1. 熟悉小红书、抖音等内容平台
2. 会写文案，能做数据复盘
3. 有社群或创作者运营经验优先""",
    },
    {
        "id": "creator-ops",
        "title": "创作者运营实习生",
        "family": "operations",
        "tags": ["creator", "operations"],
        "jd": """创作者运营实习生
岗位职责
- 负责画师、创作者社群的日常运营与活动策划
- 收集创作者反馈，推动产品优化
任职要求
1. 熟悉米画师、画加等接单平台生态
2. 具备良好的沟通与用户洞察能力
3. 能写运营文案，做数据复盘""",
    },
    {
        "id": "business-analyst",
        "title": "商业分析实习生",
        "family": "data",
        "tags": ["data", "business"],
        "jd": """商业分析实习生
岗位职责
- 支持业务指标体系建设与经营分析
- 搭建看板，输出分析报告
任职要求
1. 熟练使用 Excel，会 SQL 优先
2. 具备数据分析与业务理解能力
3. 逻辑清晰，沟通表达好""",
    },
    {
        "id": "data-analyst",
        "title": "数据分析实习生",
        "family": "data",
        "tags": ["data"],
        "jd": """数据分析实习生
任职要求
1. 熟练使用 SQL 做数据查询与清洗
2. 能搭建看板，定义漏斗与转化率指标
3. 有 A/B 测试或业务复盘经验优先""",
    },
    {
        "id": "product-intern",
        "title": "产品经理实习生（工具/内容）",
        "family": "product",
        "tags": ["product", "content"],
        "jd": """产品经理实习生
岗位职责
- 参与工具类产品的需求分析、原型设计与 PRD 撰写
- 跟进版本迭代，收集用户反馈
任职要求
1. 熟练使用墨刀、Axure 等原型工具
2. 具备用户调研与竞品分析能力
3. 沟通协作能力强，能推动跨团队落地""",
    },
    {
        "id": "growth-ops",
        "title": "增长运营实习生",
        "family": "growth",
        "tags": ["growth", "operations"],
        "jd": """增长运营实习生
岗位职责
- 负责拉新、激活与留存策略的执行
- 分析漏斗数据，优化转化率
任职要求
1. 熟悉增长漏斗与转化率指标
2. 能策划活动并做数据复盘
3. 有社群或私域运营经验优先""",
    },
    {
        "id": "solution-intern",
        "title": "AI 解决方案/售前实习生",
        "family": "ai",
        "tags": ["ai", "solution"],
        "jd": """AI 解决方案实习生
岗位职责
- 面向客户设计 AI 解决方案，输出方案文档
- 支持售前 POC 与产品演示
任职要求
1. 具备较强的沟通与方案表达能力
2. 了解大模型应用与 Agent 场景
3. 能独立对接客户需求""",
    },
    {
        "id": "content-ops",
        "title": "内容运营实习生（AIGC）",
        "family": "marketing",
        "tags": ["content", "operations"],
        "jd": """内容运营实习生
岗位职责
- 负责公众号、小红书等渠道的内容策划与发布
2. 用 AIGC 工具批量生产图文素材
任职要求
1. 文案功底好，有选题能力
2. 熟悉小红书、抖音的内容生态
3. 会用 AI 工具提升内容效率""",
    },
    {
        "id": "user-research",
        "title": "用户研究实习生",
        "family": "research",
        "tags": ["product", "research"],
        "jd": """用户研究实习生
岗位职责
- 执行用户访谈、问卷与可用性测试
- 输出用户画像与需求洞察报告
任职要求
1. 掌握访谈、问卷等调研方法
2. 具备数据分析与报告撰写能力
3. 有互联网产品调研经验优先""",
    },
]


@dataclass
class InternshipResult:
    id: str
    title: str
    family: str
    tags: list[str]
    score: float
    goal_match: bool
    top_gap: str | None = None
    top_gain: float | None = None
    gaps: list[str] = field(default_factory=list)


def load_presets(path: str | None = None) -> list[dict]:
    if not path:
        return PRESETS
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def rank(profile: str, presets: list[dict] | None = None,
         goal: str | None = None) -> list[InternshipResult]:
    presets = presets or PRESETS
    out: list[InternshipResult] = []
    for p in presets:
        reqs, _ = matching.extract_requirements(p["jd"])
        matches, _ = matching.match(reqs, profile)
        base, ups = matching.counterfactual(reqs, matches)
        top = ups[0] if ups else None
        tags = p.get("tags", [])
        out.append(InternshipResult(
            id=p["id"], title=p["title"], family=p.get("family", ""),
            tags=tags, score=base,
            goal_match=bool(goal and goal in tags),
            top_gap=top[0].label if top else None,
            top_gain=top[2] if top else None,
            gaps=[f"{r.label} +{d}" for r, s, d, n in ups[:3]],
        ))
    if goal:
        out.sort(key=lambda r: (not r.goal_match, -r.score))
    else:
        out.sort(key=lambda r: -r.score)
    return out


def timeline(cohort: int, today: date | None = None) -> list[dict]:
    """Cohort timeline. cohort=2028 -> graduate 2028.06, 秋招 2027 autumn."""
    today = today or date.today()
    cur = (today.year, today.month)
    y = cohort
    phases = [
        ("日常实习", (y - 2, 10), (y - 1, 1), "拿到第一段真实交付"),
        ("暑期实习投递", (y - 1, 2), (y - 1, 4), "大厂 / 明星 AI 公司"),
        ("暑期实习", (y - 1, 6), (y - 1, 8), "争取转正 / return"),
        ("秋招", (y - 1, 8), (y - 1, 11), f"{y} 届秋招，主攻目标岗位"),
        ("春招补录", (y, 3), (y, 6), "兜底"),
    ]
    out = []
    for name, start, end, goal in phases:
        out.append({
            "phase": name,
            "start": f"{start[0]}.{start[1]:02d}",
            "end": f"{end[0]}.{end[1]:02d}",
            "goal": goal,
            "current": start <= cur <= end,
        })
    return out


def render_markdown(results: list[InternshipResult], goal: str | None,
                    cohort: int | None, profile_name: str) -> str:
    lines = ["# 实习方向推荐", ""]
    lines.append(f"- 评估对象：{profile_name}")
    lines.append(f"- 目标方向：{goal or '未指定'}（按匹配分排序）")
    lines.append("")
    lines.append("| 排名 | 方向 | 匹配分 | 目标契合 | 最大缺口 |")
    lines.append("| ---: | --- | ---: | :---: | --- |")
    for i, r in enumerate(results, 1):
        gap = f"{r.top_gap} +{r.top_gain}" if r.top_gap else "无"
        lines.append(f"| {i} | {r.title} | {r.score}% | {'✓' if r.goal_match else '—'} | {gap} |")
    lines.append("")
    lines.append("> 分数是关键词与证据覆盖的近似值，不是职业建议。方向选择应服务目标岗位。")
    if cohort:
        lines.append("")
        lines.append(f"## {cohort} 届时间线")
        lines.append("")
        lines.append("| 阶段 | 时间 | 目标 |")
        lines.append("| --- | --- | --- |")
        for p in timeline(cohort):
            mark = " ← 当前阶段" if p["current"] else ""
            lines.append(f"| {p['phase']} | {p['start']} – {p['end']} | {p['goal']}{mark} |")
    return "\n".join(lines) + "\n"
