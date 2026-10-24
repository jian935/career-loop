"""经历文本 x 能力项 -> 匹配矩阵。"""

from __future__ import annotations

import re

from .llm import LLM, LLMError
from .schema import TAXONOMY, MatchResult, Requirement, canonical_hits

ACTION_WORDS = [
    "做", "实现", "搭建", "开发", "写", "上线", "设计", "优化",
    "负责", "跑通", "落地", "迭代", "维护", "主导", "参与", "评测", "标注",
    "梳理", "标出", "定", "记录", "画", "配置", "封装", "搭", "报", "跑",
    "输出", "录", "整理", "建", "分析", "对比", "统计", "定位",
]

BULLET_RE = re.compile(r"^\s*(?:[-*+•]|\d+[.、)]|[（(]\d+[)）])\s*")

# 出现这些表述，说明"提了但没做/做得不够"，证据降级为 partial
NEGATIVE_MARKERS = [
    "没有", "未", "尚未", "只做过", "只在自己", "仅", "缺少", "谈不上",
    "没做", "没统计", "感觉还行", "demo", "玩具", "简单", "粗略", "没实际",
]

# 这些是"明确没做过"，比上面的弱否定更强，应直接判缺失
STRONG_NEGATIVE = [
    "没用过", "没做过", "从没", "完全没有", "毫无", "从不", "没碰过", "没接触", "不了解",
]


def _profile_lines(profile: str) -> list[str]:
    lines = []
    for raw in profile.splitlines():
        if raw.strip().startswith("#"):
            continue  # 标题不是证据
        line = BULLET_RE.sub("", raw).strip()
        if len(line) >= 6:
            lines.append(line)
    return lines


def _claim_lines(lines: list[str]) -> dict[str, list[str]]:
    """把每一行归属给命中的能力。

    规则：命中词长度必须 >= 2；同一行里长度处于同一档（top-1 或 top-2）的能力都能认领，
    只有当某能力命中词明显更短（比最长短 2 以上）时才丢弃，避免一行后端描述把
    Python 和工程都算上，也避免几个平级能力互相挤掉。
    """
    owned: dict[str, list[str]] = {}
    for line in lines:
        hits = canonical_hits(line)
        if not hits:
            continue
        ranked = sorted(
            ((max(len(w) for w in words), key) for key, words in hits.items()),
            reverse=True,
        )
        top_len = ranked[0][0]
        for length, key in ranked:
            if length < 2:
                continue
            if length >= top_len - 1:
                owned.setdefault(key, []).append(line)
    return owned


def match_by_rules(requirements: list[Requirement], profile: str) -> dict[str, MatchResult]:
    lines = _profile_lines(profile)
    owned = _claim_lines(lines)
    results: dict[str, MatchResult] = {}
    for req in requirements:
        candidates = owned.get(req.key, [])
        if not candidates:
            results[req.key] = MatchResult(req.key, "missing")
            continue
        strong_neg = any(s in line for line in candidates for s in STRONG_NEGATIVE)
        if strong_neg:
            results[req.key] = MatchResult(
                req.key,
                "missing",
                evidence=candidates[0][:110],
                note="明确写了『没用过/没做过』，判为缺失而非部分具备",
            )
            continue
        evidence = ""
        negated = False
        for line in candidates:
            if any(a in line for a in ACTION_WORDS):
                evidence = line[:110]
                negated = any(n in line for n in NEGATIVE_MARKERS)
                break
        if not evidence:
            evidence = candidates[0][:110]
            negated = True  # 提到但没有任何"做过"的动作，只能算部分具备
        if negated:
            results[req.key] = MatchResult(
                req.key,
                "partial",
                evidence=evidence,
                note="证据里有『没做过/只做过 demo』一类的自我否定，实际大概率是缺口",
            )
        else:
            results[req.key] = MatchResult(req.key, "full", evidence=evidence)
    return results


MATCH_SYSTEM = """你是严格的技术面试官。判断候选人经历是否真正覆盖 JD 的每一项能力。

只输出 JSON：
{"matches":[{"key":"能力 key","status":"full|partial|missing","evidence":"候选人原文片段，没有就空字符串","note":"不超过 30 字的判断理由"}]}

判定标准：
- full：有具体项目/产出/数字能证明这项能力，不是只会说名词。
- partial：提到了相关技术或课程，但缺少落地证据。
- missing：完全没提。
- evidence 必须逐字摘自候选人经历，禁止编造。
- 必须覆盖输入的每一个 key。"""


def match_by_llm(
    requirements: list[Requirement], profile: str, llm: LLM
) -> dict[str, MatchResult]:
    keys = [r.key for r in requirements]
    payload = {
        "keys": keys,
        "labels": {r.key: r.label for r in requirements},
        "profile": profile,
    }
    data = llm.json(MATCH_SYSTEM, f"输入：\n{payload}")
    results: dict[str, MatchResult] = {}
    for item in data.get("matches", []):
        key = item.get("key", "")
        if key not in keys:
            continue
        status = item.get("status", "missing")
        if status not in ("full", "partial", "missing"):
            status = "missing"
        results[key] = MatchResult(
            key, status, (item.get("evidence") or "")[:110], (item.get("note") or "")[:60]
        )
    missing_keys = [k for k in keys if k not in results]
    if len(missing_keys) == len(keys):
        raise LLMError("LLM 未返回有效匹配结果")
    for key in missing_keys:
        results[key] = MatchResult(key, "missing")
    return results


def match(
    requirements: list[Requirement], profile: str, llm: LLM | None = None
) -> tuple[dict[str, MatchResult], str]:
    if llm and llm.available:
        try:
            return match_by_llm(requirements, profile, llm), "llm"
        except (LLMError, KeyError, ValueError):
            pass
    return match_by_rules(requirements, profile), "rule"


def score(requirements: list[Requirement], matches: dict[str, MatchResult]) -> float:
    """加权覆盖率，partial 记半分。"""
    total = sum(r.weight for r in requirements)
    if not total:
        return 0.0
    got = 0.0
    for req in requirements:
        status = matches.get(req.key, MatchResult(req.key, "missing")).status
        got += req.weight * {"full": 1.0, "partial": 0.5, "missing": 0.0}[status]
    return round(got / total * 100, 1)


def gaps(
    requirements: list[Requirement], matches: dict[str, MatchResult]
) -> list[tuple[Requirement, str, float]]:
    """按 (权重 x 缺口严重度) 排序，返回 (能力项, 状态, 优先级分)。"""
    out = []
    for req in requirements:
        status = matches.get(req.key, MatchResult(req.key, "missing")).status
        if status == "full":
            continue
        severity = 1.0 if status == "missing" else 0.5
        out.append((req, status, round(req.weight * severity, 2)))
    return sorted(out, key=lambda x: -x[2])


def counterfactual(
    requirements: list[Requirement], matches: dict[str, MatchResult]
) -> tuple[float, list[tuple[Requirement, str, float, float]]]:
    """反事实：假设把某一项补到 full，匹配分会变成多少。

    返回 (当前分, [(能力项, 原状态, 涨幅, 新分数), ...])，按涨幅降序。
    这是「补哪一项最划算」的直接量化，比只列缺口更有决策价值。
    """
    base = score(requirements, matches)
    out = []
    for req in requirements:
        status = matches.get(req.key, MatchResult(req.key, "missing")).status
        if status == "full":
            continue
        sim = dict(matches)
        sim[req.key] = MatchResult(req.key, "full")
        new_score = score(requirements, sim)
        out.append((req, status, round(new_score - base, 1), new_score))
    out.sort(key=lambda x: -x[2])
    return base, out


def fix_for(key: str) -> str:
    return TAXONOMY.get(key, {}).get("fix", "找一个最小可交付物，把它做完并公开。")
