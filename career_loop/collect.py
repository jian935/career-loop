"""W3：JD 采集 —— 批量把原始 JD 文本（.md/.txt）清洗后入库，并汇总岗位需求热力。

- collect_dir: 扫一个目录，清掉招聘站导航噪声，抽取能力项，去重入库。
- capability_demand: 跨整批 JD 汇总「哪些能力最被需要」，若提供经历则额外算出
  「补哪一项性价比最高」（需求权重 × 你的未覆盖比例），直接回答「下一步该做什么」。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import matching, store
from .matching.schema import TAXONOMY


# 采集时要清掉的招聘站导航 / 联系类噪声；不动「岗位职责 / 任职要求」等正文标题。
_BOILERPLATE = [
    "一键投递", "立即申请", "申请职位", "收藏职位", "分享给朋友", "举报",
    "查看地图", "融资轮次", "公司规模", "经验要求：", "学历要求：",
]


def normalize_jd(raw: str) -> str:
    """保守清洗：只删明确噪声，不伤及岗位/要求正文，避免污染匹配。"""
    text = raw
    text = re.sub(r"https?://\S+", "", text)                 # 链接
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "", text)     # 邮箱
    text = re.sub(r"(?<!\d)(1[3-9]\d{9})(?!\d)", "", text)   # 手机号
    for phrase in _BOILERPLATE:
        text = text.replace(phrase, "")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


@dataclass
class CollectResult:
    ingested: int
    skipped: int
    titles: list[str]


def collect_dir(dir_path: str, db=None) -> CollectResult:
    p = Path(dir_path)
    files = sorted(p.glob("*.md")) + sorted(p.glob("*.txt"))
    existing = {j["title"] for j in store.list_jds(db)}
    ingested = 0
    titles: list[str] = []
    for f in files:
        raw = f.read_text(encoding="utf-8")
        text = normalize_jd(raw)
        title = matching.extract_title(text)
        if title in existing:
            continue
        reqs, _ = matching.extract_requirements(text)
        store.add_jd(title, text, reqs, db)
        existing.add(title)
        ingested += 1
        titles.append(title)
    return CollectResult(ingested=ingested, skipped=len(files) - ingested, titles=titles)


@dataclass
class CapItem:
    key: str
    label: str
    demand_weight: int
    demand_count: int
    coverage: float | None = None     # 0..1，提供经历时才有
    priority: float | None = None     # demand_weight * (1 - coverage)


@dataclass
class DemandReport:
    total_jds: int
    items: list[CapItem]
    has_profile: bool


def _iter_jds(jds) -> list[tuple[str, str]]:
    """jds 可以是 [(title, text)]，也可以是 store.list_jds 返回的 dict 列表。"""
    out = []
    for j in jds:
        if isinstance(j, dict):
            out.append((j["title"], j["text"]))
        else:
            out.append((j[0], j[1]))
    return out


def capability_demand(jds, profile_text: str | None = None) -> DemandReport:
    pairs = _iter_jds(jds)
    agg_w: dict[str, int] = {}
    agg_c: dict[str, int] = {}
    for title, text in pairs:
        reqs, _ = matching.extract_requirements(text)
        for r in reqs:
            agg_w[r.key] = agg_w.get(r.key, 0) + r.weight
            agg_c[r.key] = agg_c.get(r.key, 0) + 1

    items: list[CapItem] = []
    for key in sorted(agg_w, key=lambda k: -agg_w[k]):
        label = TAXONOMY.get(key, {}).get("label", key)
        cov = None
        pri = None
        if profile_text is not None:
            sat_w = 0.0
            tot_w = 0.0
            for title, text in pairs:
                reqs, _ = matching.extract_requirements(text)
                for r in reqs:
                    if r.key != key:
                        continue
                    tot_w += r.weight
                    m = matching.match_by_rules([r], profile_text).get(key)
                    if m and m.status in ("full", "partial"):
                        sat_w += r.weight
            cov = (sat_w / tot_w) if tot_w else 0.0
            pri = agg_w[key] * (1 - cov)
        items.append(CapItem(key, label, agg_w[key], agg_c[key], cov, pri))

    return DemandReport(total_jds=len(pairs), items=items, has_profile=profile_text is not None)


def render_demand(rep: DemandReport) -> str:
    lines = ["# 岗位需求热力报告", ""]
    lines.append(f"- 统计 JD 数：**{rep.total_jds}**")
    if rep.has_profile:
        lines.append("- 已结合你的经历，给出「补能力优先级」")
    lines.append("")

    lines.append("## 需求最高的能力")
    lines.append("")
    lines.append("| 能力 | 需求权重 | 出现 JD 数 |")
    lines.append("| --- | ---: | ---: |")
    for it in rep.items:
        lines.append(f"| {it.label} | {it.demand_weight} | {it.demand_count} |")
    lines.append("")

    if rep.has_profile:
        lines.append("## 下一步该补什么（需求权重 × 你的未覆盖比例）")
        lines.append("")
        lines.append("| 能力 | 需求权重 | 你的覆盖 | 优先级 | 建议做法 |")
        lines.append("| --- | ---: | ---: | ---: | --- |")
        for it in sorted(rep.items, key=lambda x: -(x.priority or 0)):
            fix = TAXONOMY.get(it.key, {}).get("fix", "")
            cov = f"{it.coverage:.0%}" if it.coverage is not None else "-"
            lines.append(f"| {it.label} | {it.demand_weight} | {cov} | {it.priority:.0f} | {fix} |")
        lines.append("")
    return "\n".join(lines)
