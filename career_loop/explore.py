# -*- coding: utf-8 -*-
"""Resume -> all-industry job scan -> fit -> gaps -> recommendations.

Input is a profile plus a job corpus (JSONL or a folder of .md). Output is a
ranked list, an industry roll-up, the most common gaps, and next actions.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from . import matching
from .matching.schema import ALL_DIMS


LEVELS = ["intern", "junior", "mid", "senior", "exec"]

LEVEL_FACTOR = {
    "intern": {"intern": 1.0, "junior": 0.9, "mid": 0.5, "senior": 0.15, "exec": 0.1},
    "junior": {"intern": 1.0, "junior": 1.0, "mid": 0.9, "senior": 0.35, "exec": 0.2},
    "mid": {"intern": 0.8, "junior": 0.95, "mid": 1.0, "senior": 0.7, "exec": 0.35},
    "senior": {"intern": 0.5, "junior": 0.8, "mid": 0.95, "senior": 1.0, "exec": 0.8},
}


def detect_level(title: str, description: str = "", hint: str | None = None) -> str:
    """Seniority from an explicit hint, then the title, then the description.

    Word boundaries matter: "internal" must not match "intern".
    """
    import re

    if hint:
        h = str(hint).lower()
        for k, v in (("intern", "intern"), ("entry", "junior"), ("junior", "junior"),
                     ("mid", "mid"), ("senior", "senior"), ("manager", "senior"),
                     ("director", "exec"), ("executive", "exec")):
            if k in h:
                return v

    t = title.lower()
    d = description[:300].lower()

    def hit(pattern: str, text: str) -> bool:
        return re.search(pattern, text) is not None

    if hit(r"\bintern(ship)?\b", t) or "实习" in title:
        return "intern"
    if hit(r"\b(director|vice president|vp|head of|chief)\b", t) or any(w in title for w in ("总监", "负责人")):
        return "exec"
    if "engineering manager" in t or hit(r"\b(senior|sr\.?|principal|staff|lead|leader)\b", t) \
            or any(w in title for w in ("高级", "主管")):
        return "senior"
    if hit(r"\b(junior|entry.level|graduate|associate)\b", t) or any(w in title for w in ("初级", "专员")):
        return "junior"
    if hit(r"\bintern(ship)?\b", d) or "实习" in d:
        return "intern"
    return "mid"


@dataclass
class JobFit:
    id: str
    title: str
    company: str
    category: str
    score: float
    n_reqs: int
    mode: str
    level: str = "mid"
    rank_score: float = 0.0
    goal_match: bool = False
    top_gaps: list[tuple[str, str, float]] = field(default_factory=list)
    error: str = ""


@dataclass
class IndustryFit:
    category: str
    n_jobs: int
    best_score: float
    avg_score: float
    best_title: str
    best_rank: float = 0.0


@dataclass
class ScanReport:
    total: int
    ok: int
    categories: int
    jobs: list[JobFit]
    industries: list[IndustryFit]
    gap_counts: list[tuple[str, str, int, str]]
    mode: str
    mode_counts: dict[str, int] = field(default_factory=dict)
    target_level: str | None = None
    goal: str | None = None


def load_jobs(path: str) -> list[dict]:
    p = Path(path)
    if p.is_dir():
        out = []
        for f in sorted(p.glob("*.md")) + sorted(p.glob("*.txt")):
            text = f.read_text(encoding="utf-8")
            out.append({
                "id": f.stem, "title": matching.extract_title(text),
                "company": "", "category": "未分类", "description": text,
            })
        return out
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        desc = d.get("description") or d.get("jd") or d.get("text") or ""
        rows.append({
            "id": d.get("id") or d.get("url") or d.get("title", ""),
            "title": d.get("title") or d.get("jobTitle") or "",
            "company": d.get("company") or d.get("companyName") or "",
            "category": d.get("category") or d.get("jobIndustry") or "未分类",
            "description": desc,
            "level_hint": d.get("level_hint") or d.get("seniority"),
        })
    return rows


GOAL_KEYWORDS = {
    "ai": ("ai", "artificial intelligence", "machine learning", "llm", "agent", "product"),
    "product": ("product", "产品"),
    "data": ("data", "analytics", "分析"),
    "design": ("design", "ux", "ui"),
    "sales": ("sales", "business development", "account"),
}


def _goal_match(title: str, category: str, description: str, goal: str | None) -> bool:
    """Match the goal against the title only.

    Using the description makes almost every tech job match ("we use AI"), which
    defeats the purpose of a target section.
    """
    if not goal:
        return False
    words = GOAL_KEYWORDS.get(goal, (goal,))
    t = title.lower()
    return any(w.lower() in t for w in words)


def _one(job: dict, profile: str, llm, target_level: str | None = "junior",
         goal: str | None = None) -> JobFit:
    level = detect_level(job.get("title", ""), job.get("description", ""),
                         job.get("level_hint"))
    factor = LEVEL_FACTOR.get(target_level or "", {}).get(level, 1.0)
    goal_match = _goal_match(job.get("title", ""), job.get("category", ""),
                             job.get("description", ""), goal)
    try:
        reqs, emode = matching.extract_requirements(job["description"], llm)
        if not reqs:
            return JobFit(id=job["id"], title=job["title"], company=job["company"],
                          category=job["category"], score=0.0, n_reqs=0, mode=emode,
                          level=level, rank_score=0.0, goal_match=goal_match,
                          error="no requirements")
        matches, mmode = matching.match(reqs, profile, llm)
        s = matching.score(reqs, matches)
        _, ups = matching.counterfactual(reqs, matches)
        gaps = [(r.key, r.label, d) for r, st, d, n in ups[:3]]
        return JobFit(id=job["id"], title=job["title"], company=job["company"],
                      category=job["category"], score=s, n_reqs=len(reqs), mode=mmode,
                      level=level, rank_score=round(s * factor, 1),
                      goal_match=goal_match, top_gaps=gaps)
    except Exception as exc:  # noqa: BLE001
        return JobFit(id=job["id"], title=job["title"], company=job["company"],
                      category=job["category"], score=0.0, n_reqs=0, mode="error",
                      level=level, rank_score=0.0, goal_match=goal_match,
                      error=str(exc)[:120])


def scan(profile: str, jobs: list[dict], llm=None, top: int = 20,
         workers: int = 6, level: str | None = "junior",
         goal: str | None = None) -> ScanReport:
    use_llm = bool(llm and getattr(llm, "available", False))
    if use_llm and len(jobs) > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(lambda j: _one(j, profile, llm, level, goal), jobs))
    else:
        results = [_one(j, profile, None, level, goal) for j in jobs]

    valid = [r for r in results if not r.error]
    valid.sort(key=lambda r: -r.rank_score)

    by_cat: dict[str, list[JobFit]] = defaultdict(list)
    for r in valid:
        by_cat[r.category].append(r)
    industries = []
    for cat, rs in by_cat.items():
        best = max(rs, key=lambda x: x.rank_score)
        industries.append(IndustryFit(
            cat, len(rs), best.score,
            round(sum(x.score for x in rs) / len(rs), 1), best.title,
            best_rank=best.rank_score,
        ))
    industries.sort(key=lambda x: (-x.best_rank, -x.avg_score))

    basis = [r for r in valid if r.goal_match] if goal else valid
    if not basis:
        basis = valid
    counter: Counter[str] = Counter()
    label_of: dict[str, str] = {}
    for r in basis[:top]:
        for key, label, delta in r.top_gaps[:2]:
            counter[key] += 1
            label_of[key] = label
    gap_counts = []
    for key, n in counter.most_common(8):
        fix = ALL_DIMS.get(key, {}).get("fix") or TAXONOMY_FIX.get(key, "做一个可验证的小作品来证明这项能力。")
        gap_counts.append((key, label_of.get(key, key), n, fix))

    return ScanReport(
        total=len(results), ok=len(valid), categories=len(by_cat),
        jobs=valid, industries=industries, gap_counts=gap_counts,
        mode="llm" if use_llm else "rule",
        mode_counts=dict(Counter(r.mode for r in valid)),
        target_level=level, goal=goal,
    )


# TAXONOMY has hand-written fix text; other dims use the generic suggestion.
try:  # pragma: no cover - import-time convenience
    from .matching.schema import TAXONOMY

    TAXONOMY_FIX = {k: v.get("fix", "") for k, v in TAXONOMY.items()}
except Exception:  # noqa: BLE001
    TAXONOMY_FIX = {}


def render_markdown(report: ScanReport, profile_name: str,
                    intern_rows: list | None = None,
                    cohort: int | None = None) -> str:
    lines = ["# 全行业岗位适配报告", ""]
    lines.append(f"- 评估对象：{profile_name}")
    lines.append(f"- 扫描岗位：**{report.total}** 个（成功 {report.ok}）")
    lines.append(f"- 覆盖行业：**{report.categories}** 个")
    lines.append(f"- 匹配模式：{report.mode}（{report.mode_counts}）")
    if report.target_level:
        lines.append(f"- 目标职级：**{report.target_level}**（更高职级已按比例降权）")
    lines.append("")
    lines.append("> 分数是要求覆盖度的近似值；LLM 模式按证据强度判断，规则模式偏乐观。")

    if report.goal:
        targets = [r for r in report.jobs if r.goal_match][:10]
        lines += ["", f"## 目标方向（{report.goal}）", ""]
        if targets:
            lines.append("> 高级/管理岗已按目标职级降权；匹配分列仍是原始分，可作 stretch 参考。")
            lines += ["| 匹配分 | 职级 | 岗位 | 公司 | 行业 | 最大缺口 |",
                      "| ---: | --- | --- | --- | --- | --- |"]
            for r in targets:
                gap = f"{r.top_gaps[0][1]} +{r.top_gaps[0][2]}" if r.top_gaps else "无"
                lines.append(f"| {r.score}% | {r.level} | {r.title} | {r.company} | {r.category} | {gap} |")
        else:
            lines.append("> 这批岗位里没有命中目标方向的岗位，建议换一批更贴近的 JD。")

    lines += ["", "## 最适配的岗位（Top 20）", "",
              "| 排名 | 匹配分 | 职级 | 岗位 | 公司 | 行业 | 最大缺口 |",
              "| ---: | ---: | --- | --- | --- | --- | --- |"]
    for i, r in enumerate(report.jobs[:20], 1):
        gap = f"{r.top_gaps[0][1]} +{r.top_gaps[0][2]}" if r.top_gaps else "无"
        lines.append(f"| {i} | {r.score}% | {r.level} | {r.title} | {r.company} | {r.category} | {gap} |")

    lines += ["", "## 行业适配度", "",
              "| 行业 | 岗位数 | 最高分 | 平均分 | 最高分岗位 |",
              "| --- | ---: | ---: | ---: | --- |"]
    for ind in report.industries:
        lines.append(f"| {ind.category} | {ind.n_jobs} | {ind.best_score}% | {ind.avg_score}% | {ind.best_title} |")

    lines += ["", "## 最该补的能力（Top 岗位中出现的缺口）", "",
              "| 能力 | 出现次数 | 怎么补 |", "| --- | ---: | --- |"]
    for key, label, n, fix in report.gap_counts:
        lines.append(f"| {label} | {n} | {fix} |")

    targets = [r for r in report.jobs if r.goal_match] if report.goal else []
    lines += ["", "## 下一步建议", ""]
    if targets:
        cats = []
        for r in targets:
            if r.category not in cats:
                cats.append(r.category)
        lines.append("1. **优先投这些方向**：" + "、".join(cats[:3]) + "（按目标方向筛选）")
        lines.append("2. **先投这几家**：" + "、".join(f"{r.title}（{r.score}%）" for r in targets[:5]))
    else:
        if report.industries:
            top_ind = report.industries[:3]
            lines.append("1. **优先投这些行业**：" + "、".join(f"{x.category}（最高 {x.best_score}%）" for x in top_ind))
        if report.jobs:
            lines.append("2. **先投这几家**：" + "、".join(f"{r.title}（{r.score}%）" for r in report.jobs[:5]))
    if report.gap_counts:
        lines.append("3. **先补这两项**：" + "、".join(g[1] for g in report.gap_counts[:2]))
    lines.append("4. **再用 `whatif` 看单项提升**：`career-loop whatif --jd <目标JD> --profile <简历>`")

    if intern_rows:
        lines += ["", "## 实习方向（按目标契合 + 匹配分）", "",
                  "| 排名 | 方向 | 匹配分 | 目标契合 |", "| ---: | --- | ---: | :---: |"]
        for i, r in enumerate(intern_rows[:6], 1):
            lines.append(f"| {i} | {r.title} | {r.score}% | {'✓' if r.goal_match else '—'} |")
        if cohort:
            lines.append(f"\n> {cohort} 届时间线可用 `career-loop intern --cohort {cohort}` 查看。")

    return "\n".join(lines) + "\n"
