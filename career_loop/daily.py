# -*- coding: utf-8 -*-
"""每日投递清单：把一批 JD 变成一张**今天就能照着做**的待办。

它回答的是比「我适合哪个岗」更具体的问题：**今天先投哪个、投之前先改哪一句**。

三条设计约束：

1. **每条必须能当场执行**——岗位 + 匹配分 + 最划算补强 + 截止日，四样缺一样
   就不是清单，只是一份排行榜。「补强」用的是 `counterfactual`（真的重算一遍
   补上之后的分数），所以带的是「78.5% → 86.0%」这种具体落点，不是一句建议。
2. **导出要能进别的地方**——Markdown 勾选框（贴进笔记/滴答清单）、
   CSV（进表格/Notion 数据库）、ICS（进日历与待办 App，带截止日提醒）。
3. **截止日是启发式抽取**，每条都写明来源（JD 原文 / 命令行默认值 / 没找到），
   让人一眼知道该自己核哪一条——**把猜出来的日期伪装成确定的，是这类工具最坏的 bug**。
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from . import matching

# 截止日的线索词：只有在它们附近出现的日期才被当成投递截止日。
# 不放宽到全文找日期，是因为 JD 里还有发布日期、公司成立年份、
# 「2025 年营收」这类数字，抓下来只会污染清单。
DEADLINE_CUES = ("截止时间", "截止日期", "截止", "截至", "deadline", "报名截止",
                 "投递截止", "有效至", "有效期至")

#: 「招满为止」这类写法没有具体日期，单独识别，好明确告诉用户「JD 没给」
OPEN_ENDED = ("招满为止", "长期有效", "长期招聘", "额满为止")

_DATE_FULL = re.compile(r"(\d{4})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})")
_DATE_SHORT = re.compile(r"(?<!\d)(\d{1,2})\s*[月/.-]\s*(\d{1,2})\s*日?(?!\d)")


@dataclass
class Job:
    """一条待评估的岗位。"""

    title: str
    text: str
    source: str = ""
    company: str = ""


@dataclass
class DailyItem:
    """清单里的一行。"""

    title: str
    score: float
    source: str = ""
    company: str = ""
    due: Optional[str] = None        # ISO YYYY-MM-DD
    due_source: str = ""             # 来源说明，必须写清（这份日期是怎么来的）
    best_fix: Optional[tuple] = None  # (能力名, 当前分, 补后分)
    gaps: list[str] = field(default_factory=list)
    why: str = ""

    @property
    def delta(self) -> float:
        """补上最强那项能涨多少分。"""
        return round(self.best_fix[2] - self.best_fix[1], 1) if self.best_fix else 0.0

    @property
    def due_label(self) -> str:
        if not self.due:
            return "无截止信息"
        return f"{self.due}（{self.due_source}）"


@dataclass
class DailyPlan:
    """一份清单。"""

    day: str
    items: list[DailyItem] = field(default_factory=list)
    profile_label: str = "你的经历"
    total_candidates: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def sort_rule(self) -> str:
        return ("排序：**有截止日的先按截止日升序**（先到期先投），"
                "没有截止日的排在后面、内部按匹配分降序。")


# --------------------------------------------------------------------------
# 读 JD：目录 / JSONL / CSV 都支持
# --------------------------------------------------------------------------


def load_jobs(path: str | Path) -> list[Job]:
    """读一批 JD。支持三种形态：

    - 目录：里面的 `*.md` / `*.txt`（和 `collect` 同一个约定）
    - JSONL：每行一个 dict，取 `description` / `jd` / `text` 与 `title`
    - CSV：列名 `jd_text` / `jd` / `description` 与 `role` / `title` / `岗位`
    """
    p = Path(path)
    if p.is_dir():
        out: list[Job] = []
        for f in sorted(p.glob("*.md")) + sorted(p.glob("*.txt")):
            text = f.read_text(encoding="utf-8")
            out.append(Job(title=matching.extract_title(text), text=text, source=str(f)))
        return out

    raw = p.read_text(encoding="utf-8-sig")
    stripped = raw.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        rows = json.loads(raw) if stripped.startswith("[") else [
            json.loads(line) for line in raw.splitlines() if line.strip()
        ]
        rows = rows if isinstance(rows, list) else [rows]
        out = []
        for d in rows:
            if not isinstance(d, dict):
                continue
            text = str(d.get("description") or d.get("jd") or d.get("jd_text")
                       or d.get("text") or "")
            if text.strip():
                out.append(Job(
                    title=str(d.get("title") or d.get("role") or d.get("岗位") or ""),
                    text=text, source=str(d.get("id") or d.get("url") or ""),
                    company=str(d.get("company") or d.get("公司") or ""),
                ))
        return out

    out = []
    for row in csv.DictReader(raw.splitlines()):
        low = {(k or "").strip().lower(): (v or "") for k, v in row.items() if k}
        text = (low.get("jd_text") or low.get("jd") or low.get("description")
                or low.get("原文") or "")
        if not text.strip():
            continue
        out.append(Job(
            title=low.get("role") or low.get("title") or low.get("岗位") or "",
            text=text, source=low.get("id") or "",
            company=low.get("company") or low.get("公司") or "",
        ))
    return out


# --------------------------------------------------------------------------
# 截止日：启发式，必须标来源
# --------------------------------------------------------------------------


def _mk_date(y: int, m: int, d: int) -> Optional[str]:
    """组成 ISO 日期；`2026-02-30` 这种非法日期返回 None（宁可不要，不要错日期）。"""
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def _first_date(window: str, today: Optional[date] = None) -> Optional[str]:
    """在一段文本里找第一个合法日期。年份缺失时用今年，若已过期则推到明年。"""
    today = today or date.today()
    m = _DATE_FULL.search(window)
    if m:
        got = _mk_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if got:
            return got
    short = _DATE_SHORT.search(window)
    if short:
        month, day = int(short.group(1)), int(short.group(2))
        # "11/30" 也可能是 2026-11-30 之外的写法；先按 月/日 理解（中文 JD 的惯例）
        if 1 <= month <= 12 and 1 <= day <= 31:
            for year in (today.year, today.year + 1):
                got = _mk_date(year, month, day)
                if got and date.fromisoformat(got) >= today:
                    return got
            return _mk_date(today.year, month, day, today)
    return None


def find_deadline(text: str, today: Optional[date] = None) -> Optional[tuple[str, str]]:
    """抽截止日。返回 (ISO 日期, 来源说明)，找不到返回 None。

    **这是启发式**：只在「截止 / deadline / 有效期至」这类线索词附近的
    60 字窗口里找日期。抓错比抓不到更糟，所以宁可漏。
    """
    today = today or date.today()
    low = text.lower()
    for cue in DEADLINE_CUES:
        start = 0
        while True:
            idx = low.find(cue.lower(), start)
            if idx < 0:
                break
            start = idx + 1
            window = text[idx:idx + 60]
            got = _first_date(window, today)
            if got:
                return got, "JD 原文"
            # 线索词旁边写的是「招满为止」→ 确实是没给日期，但要看它出现在窗口里
            for phrase in OPEN_ENDED:
                if phrase in window:
                    return None, f"JD 写的是『{phrase}』，没有具体日期"
    # 一个线索词都没有，但通篇写着「招满为止」——也要说明清楚是 JD 没写，
    # 而不是我们没抓到。注意这一步**只能放在找完日期之后**：
    # 真实 JD 常见「截止日期：2027-02-28（招满为止不做另行通知）」，
    # 里面既有具体日期又有「招满为止」，先判「招满为止」会把日期吃掉。
    for phrase in OPEN_ENDED:
        if phrase in text:
            return None, f"JD 写的是『{phrase}』，没有具体日期"
    return None, ""


# --------------------------------------------------------------------------
# 生成清单
# --------------------------------------------------------------------------


def _sort_key(item: DailyItem) -> tuple:
    # 有截止的排前面：先到期优先；没截止的排后面，按分降序
    has_due = 0 if item.due else 1
    due_rank = item.due or "9999-12-31"
    return (has_due, due_rank, -item.score)


def build_plan(
    jobs: list[Job],
    profile: str,
    *,
    today: Optional[date] = None,
    top: int = 10,
    min_score: float = 0.0,
    default_due: Optional[str] = None,
    llm=None,
) -> DailyPlan:
    """给每个岗位打分、找出最划算补强、解析截止日，排出今天的清单。"""
    today = today or date.today()
    plan = DailyPlan(day=today.isoformat(), total_candidates=len(jobs))
    if not profile.strip():
        plan.notes.append("经历文本为空，无法打分。")
        return plan

    scored: list[DailyItem] = []
    no_due = 0
    for job in jobs:
        reqs, _ = matching.extract_requirements(job.text, llm)
        if not reqs:
            continue
        matches, _ = matching.match(reqs, profile, llm)
        score = matching.score(reqs, matches)
        if score < min_score:
            continue

        base, rows = matching.counterfactual(reqs, matches)
        best = None
        for req, _status, delta, new in rows:
            if delta > 0:
                best = (req.label, round(base, 1), round(new, 1))
                break
        gaps = [
            r.label for r, m in ((r, matches.get(r.key)) for r in reqs)
            if m is None or m.status != "full"
        ]

        due, note = find_deadline(job.text, today)
        if due is None:
            due = default_due
            src = "命令行 --due 统一指定" if default_due else "JD 未给出"
            if not default_due:
                no_due += 1
                src = note or src
        else:
            src = note or "JD 原文"

        # 为什么排进今天：把排序理由说清楚，用户才知道要不要照着做
        why = f"匹配分 {score:.1f}"
        if due:
            left = (date.fromisoformat(due) - today).days
            why += f"，距截止 {left} 天" if left >= 0 else f"，**已过期 {abs(left)} 天**"
        if best:
            why += f"；补「{best[0]}」可从 {best[1]}% 涨到 {best[2]}%"

        scored.append(DailyItem(
            title=job.title or "(未命名岗位)", score=score, source=job.source,
            company=job.company, due=due, due_source=src, best_fix=best,
            gaps=gaps[:5], why=why,
        ))

    scored.sort(key=_sort_key)
    plan.items = scored[:top]
    if no_due:
        plan.notes.append(
            f"{no_due} 个岗位没有识别出截止日（清单里标了来源），"
            "这类请自己打开链接核一眼——**不确定的日期不能当确定的用**。"
        )
    if len(scored) > len(plan.items):
        plan.notes.append(f"候选 {len(scored)} 个，只取前 {len(plan.items)} 个（--top 可调）。")
    return plan


# --------------------------------------------------------------------------
# 导出：Markdown / CSV / ICS
# --------------------------------------------------------------------------


def to_markdown(plan: DailyPlan) -> str:
    L = [f"# 今日投递清单（{plan.day}）\n",
         f"> {plan.sort_rule}",
         f"> 经历：{plan.profile_label}　｜　共 {plan.total_candidates} 个候选，"
         f"选出 {len(plan.items)} 个。\n"]
    for it in plan.items:
        line = f"- [ ] **{it.title}**　{it.score:.1f}%　截止 {it.due_label}"
        if it.company:
            line += f"（{it.company}）"
        L.append(line)
        L.append(f"      - {it.why}")
        if it.best_fix:
            name, base, new = it.best_fix
            L.append(f"      - 最划算补强：**{name}**　{base}% → {new}%"
                     f"（+{round(new - base, 1)}）")
        if it.gaps:
            L.append(f"      - 还缺：{'、'.join(it.gaps)}")
        if it.source:
            L.append(f"      - 来源：`{it.source}`")
    L.append("")
    for n in plan.notes:
        L.append(f"> {n}")
    L.append("\n> 截止日来自 JD 文本的启发式抽取，可能抓错；投之前请核一眼原始链接。")
    return "\n".join(L) + "\n"


def to_csv(plan: DailyPlan) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["岗位", "公司", "匹配分", "截止日", "截止日来源",
                "最划算补强", "补后分数", "还缺能力", "来源"])
    for it in plan.items:
        w.writerow([
            it.title, it.company, f"{it.score:.1f}", it.due or "", it.due_source,
            it.best_fix[0] if it.best_fix else "",
            it.best_fix[2] if it.best_fix else "",
            "、".join(it.gaps), it.source,
        ])
    return buf.getvalue()


def _ics_escape(s: str) -> str:
    """ICS 里 `,` `;` `\\` 必须转义，换行要变成字面 `\\n`。"""
    return (str(s).replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def to_ics(plan: DailyPlan) -> str:
    """导出成待办条目（VTODO）——带截止日，能直接进日历 / 待办类 App。

    用 VTODO 而不是 VEVENT：这是一件**要做的事**（有完成状态），
    不是一段占用的时间。
    """
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//career-loop//daily//ZH",
         "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    for it in plan.items:
        uid_seed = f"{plan.day}|{it.title}|{it.due or ''}"
        uid = hashlib.md5(uid_seed.encode("utf-8")).hexdigest()[:16] + "@career-loop"
        desc = [f"匹配分 {it.score:.1f}%"]
        if it.best_fix:
            name, base, new = it.best_fix
            desc.append(f"最划算补强：{name}（{base}% → {new}%）")
        if it.gaps:
            desc.append("还缺：" + "、".join(it.gaps))
        desc.append(f"截止日来源：{it.due_source}")
        L += [
            "BEGIN:VTODO",
            f"UID:{uid}",
            f"DTSTAMP:{now}",
            f"SUMMARY:{_ics_escape('投递 · ' + it.title + f' · {it.score:.1f}%')}",
            f"DESCRIPTION:{_ics_escape(chr(10).join(desc))}",
        ]
        if it.due:
            L.append(f"DUE;VALUE=DATE:{it.due.replace('-', '')}")
        L += ["STATUS:NEEDS-ACTION", "END:VTODO"]
    L.append("END:VCALENDAR")
    return "\r\n".join(L) + "\r\n"


EXPORTERS = {"md": to_markdown, "csv": to_csv, "ics": to_ics}


def render_console(plan: DailyPlan) -> str:
    L = ["=" * 60, f"今日投递清单 {plan.day}　（候选 {plan.total_candidates} → "
                   f"选出 {len(plan.items)}）", "=" * 60]
    for i, it in enumerate(plan.items, 1):
        L.append(f"{i:>2}. {it.score:>5.1f}%  {it.title}　截止 {it.due_label}")
        if it.best_fix:
            name, base, new = it.best_fix
            L.append(f"     补「{name}」→ {new}%（+{round(new - base, 1)}）")
    for n in plan.notes:
        L.append("· " + n)
    return "\n".join(L)
