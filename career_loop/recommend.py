"""双向匹配：给定一份经历，给一批 JD 排序，并算出「补哪一项能力最划算」。

这是求职闭环里帮你决定「下一步该做什么项目」的核心——不是告诉你「你很匹配」，
而是告诉你「把 X 做完，能多解锁 N 个你本来够不着的岗位」。
"""

from __future__ import annotations

from dataclasses import dataclass

from .matching import extract_requirements, match, score
from .matching.schema import MatchResult, TAXONOMY


@dataclass
class JdRank:
    title: str
    score: float
    n_reqs: int


def recommend(profile: str, jds: list[tuple[str, str]], llm=None) -> list[JdRank]:
    """jds: [(title, text), ...]。返回按匹配分降序排序的列表。"""
    out: list[JdRank] = []
    for title, text in jds:
        reqs, _ = extract_requirements(text, llm)
        matches, _ = match(reqs, profile, llm)
        out.append(JdRank(title=title, score=score(reqs, matches), n_reqs=len(reqs)))
    out.sort(key=lambda x: -x.score)
    return out


def gap_leverage(
    profile: str, jds: list[tuple[str, str]], threshold: float = 70.0, llm=None
) -> list[dict]:
    """对每一项能力，模拟「把它补到 full」后，能让多少个原本低于阈值的 JD 跨过线。

    返回的条目按 gained 降序——gained 越高，说明这项能力是你的「性价比最高缺口」。
    """
    base = recommend(profile, jds, llm)
    base_scores = {b.title: b.score for b in base}

    keys: set[str] = set()
    for _, text in jds:
        for r in extract_requirements(text, llm)[0]:
            keys.add(r.key)

    leverage: list[dict] = []
    for key in sorted(keys):
        gained = 0
        unlocked: list[str] = []
        for title, text in jds:
            reqs, _ = extract_requirements(text, llm)
            req_map = {r.key: r for r in reqs}
            if key not in req_map:
                continue
            if base_scores[title] >= threshold:
                continue  # 本来就越过线了，补这项没有边际收益
            matches, _ = match(reqs, profile, llm)
            if matches.get(key, MatchResult(key, "missing")).status == "full":
                continue  # 本来就有，谈不上「补」
            matches[key] = MatchResult(key, "full")  # 模拟补完
            if score(reqs, matches) >= threshold:
                gained += 1
                unlocked.append(title)
        leverage.append(
            {
                "key": key,
                "label": TAXONOMY.get(key, {}).get("label", key),
                "gained": gained,
                "jds": unlocked,
                "fix": TAXONOMY.get(key, {}).get("fix", ""),
            }
        )
    leverage.sort(key=lambda x: -x["gained"])
    return leverage
