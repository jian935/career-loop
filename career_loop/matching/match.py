"""经历文本 x 能力项 -> 匹配矩阵。"""

from __future__ import annotations

import re

from .llm import LLM, LLMError
from .schema import ALL_DIMS, TAXONOMY, MatchResult, Requirement, canonical_hits

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

# --- 否定作用域 ---------------------------------------------------------
# 早期实现只穷举 NEGATIVE_MARKERS 里的固定短语，于是「没搭建过工作流」
# 「没独立负责过项目」「没写过正式文档」这类**否定词 + 动作词**的组合
# 因为没被短语表覆盖，被判成了 full（实测 3/8 误判）。
#
# 正确做法是判断否定词的**作用域**：否定词出现在某个动作词之前的短窗口内，
# 该动作词就不构成正向证据。这样新出现的否定句式不需要再往表里加词。
NEGATION_WORDS = ["没", "未", "不", "无", "非", "缺", "少", "尚未", "从未", "并非"]

# 否定词到动作词之间的最大距离（字符数）。中文里「没独立做过」「完全没落地」
# 最多隔两三个字；超过这个距离多半是另一句话，否定作用域不该延伸过去。
NEG_SCOPE_WINDOW = 6

# 这些词本身含"没/无"，但表达的是肯定语义（"没问题""不错过"），
# 命中时不算否定词。
NEGATION_FALSE_FRIENDS = ["没问题", "不错过", "没错过", "无异议", "不少", "不时", "无比"]

# 否定词的"作用域"里，只允许出现这些填充词。
# 例：「没自己独立搭建」「完全没落地」→ 中间的"自己独立""完全"允许；
#     「没有问题后来搭建」→ 中间的"问题后来"不在白名单 → 不算否定。
NEG_FILLER_CHARS = set(
    "有会能曾经过真太完全独立自己亲手的多点一直到从在没不并尚未再得地"
    "实做用练干搞拿推出用过"
)

# 以否定字开头、但整体是肯定语义的词，命中时不算否定。
# 不做这一步，「不仅实现过」「未来搭建过」「不断迭代过」都会被误判成否定。
NEGATION_INHIBITORS = [
    "不仅", "不但", "不只", "不止", "不外", "不由", "不愧", "不疑", "不妨",
    "不禁", "不约", "不无", "不断", "不时", "不同", "不便", "不安", "不详",
    "不宜", "不济", "未来", "无论", "不论", "不管", "不顾", "无非", "唯一",
    "无不", "无误", "无奈", "无意", "无从", "无需", "无须", "无异议", "无关",
    "非常", "未必",
]

# 否定词（多字优先匹配）。刻意不收单字"少""非"——
# 「少量数据清洗」「非常熟练使用」会把它们误当成否定。
NEGATION_TOKENS = [
    "没有", "没用", "未能", "未曾", "不曾", "并非", "尚未", "从未", "不能",
    "不会", "难以", "无法", "缺少", "欠缺", "不太", "不够", "没", "未", "不", "无",
]

# 限定词：出现在动作词之前，说明"动作范围有限"——
# 「只在课程作业里跑通过」→ 只是跑过例子，不是工程落地 → 算部分具备。
LIMITER_WORDS = ["只", "仅", "光", "些许", "偶尔", "偶尔"]

# 否定辖域内，否定词与动作词之间允许的最大字符数。
NEG_MAX_SPAN = 20

# 限定词与动作词之间允许的最大距离。
LIMITER_MAX_SPAN = 20

# 子句分隔符：否定/限定的辖域不跨子句。
CLAUSE_DELIMITERS = "。；！？，,;!?\n"

# 转折词：出现在否定词之后、动作词之前时，否定辖域被切断。
# 「没写过文档，但独立落地了系统」→ 后半句是肯定。
FLIP_WORDS = ["但是", "但", "不过", "然而", "可是", "却", "尽管", "虽然", "反而"]

# 动作词前的否定作用域命中后，这一行的证据强度上限。
# partial = 提了但没做过；missing = 明确没做过。
_NEG_SCOPE_PARTIAL = "partial"
_NEG_SCOPE_MISSING = "missing"


# 自定义（词表未覆盖）要求的匹配：用字符二元组重合度兜底
CUSTOM_STOP = {
    "负责", "经验", "相关", "工作", "能力", "要求", "熟悉", "了解", "具备", "完成",
    "以及", "进行", "能够", "优先", "以上", "学历", "本科", "专业", "岗位", "职责",
    "任职", "参与", "独立", "熟练", "掌握", "良好", "一定", "具有",
}


def _bigrams(s: str) -> set[str]:
    s = re.sub(r"[^\u4e00-\u9fa5a-z0-9]", "", s.lower())
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _match_custom(req: Requirement, lines: list[str]) -> MatchResult:
    target = _bigrams(req.quote) - CUSTOM_STOP
    if not target:
        return MatchResult(req.key, "missing")
    best_c = 0.0
    best_line = ""
    for line in lines:
        pb = _bigrams(line)
        if not pb:
            continue
        c = len(target & pb) / len(target)
        if c > best_c:
            best_c = c
            best_line = line
    if best_c >= 0.5:
        status = "full" if any(a in best_line for a in ACTION_WORDS) else "partial"
        return MatchResult(req.key, status, evidence=best_line[:110])
    if best_c >= 0.28:
        return MatchResult(
            req.key, "partial", evidence=best_line[:110],
            note="文字有部分重合，建议人工确认是否真的做过",
        )
    return MatchResult(req.key, "missing")


# 一行里「命中词只有 2 个字」的能力最多认领几个。中文能力词大量是两字词，
# 太小会误判缺失；太大会让一行认领过多能力、虚高分数。
_WEAK_KEEP = 4


def _strip_inhibitors(text: str) -> str:
    """去掉「不仅/未来/不断」这类整体为肯定语义的词。

    去掉之后，剩余文本里出现的否定字才算真正的否定。
    """
    out = text
    for inh in NEGATION_INHIBITORS:
        out = out.replace(inh, "")
    return out


def _clauses(line: str) -> list[str]:
    """把一行按子句分隔符切开。

    否定与限定的辖域不跨子句：「没写过文档，但独立落地了系统」
    后半句是肯定，不能被前半句的"没"污染。
    """
    out: list[str] = []
    cur: list[str] = []
    for ch in line:
        if ch in CLAUSE_DELIMITERS:
            if cur:
                out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur))
    return out


def _find_actions(clause: str) -> list[int]:
    """找出子句里所有动作词的起始位置。

    最长词优先且不重叠：ACTION_WORDS 里同时有"搭建""搭""建"，
    若不处理重叠，"没搭建过"里的"建"会被当成一个独立动作词，
    而它前面的"搭"不在否定辖域填充白名单里 → 作用域断裂 → 误判为有正向证据。
    """
    taken: list[tuple[int, int]] = []
    hits: list[int] = []
    for word in sorted(ACTION_WORDS, key=len, reverse=True):
        start = 0
        while True:
            idx = clause.find(word, start)
            if idx < 0:
                break
            start = idx + len(word)
            end = idx + len(word)
            if any(idx < e and s < end for s, e in taken):
                continue
            taken.append((idx, end))
            hits.append(idx)
    return sorted(hits)


def _negation_scope(clause: str, action_idx: int) -> bool:
    """判断 clause 中第 action_idx 处开始的动作词，是否落在否定作用域内。

    中文否定辖域的规则：否定词后面可以跟一串"填充词"（自己/独立/完全/真正…），
    然后才是被否定的动作词；一旦出现别的成分（题/后来…），辖域就断了。

    例：
      「没自己独立搭建过工作流」→ 没 + 自己独立 + 搭建 → 否定 ✓
      「没有问题后来搭建了系统」→ 没 + 有问题后来 + 搭建 → 辖域断 → 不算否定 ✓
    """
    prefix = _strip_inhibitors(clause[:action_idx])
    if not prefix:
        return False
    for token in NEGATION_TOKENS:
        pos = prefix.rfind(token)
        if pos < 0:
            continue
        between = prefix[pos + len(token):]
        if not all(c in NEG_FILLER_CHARS for c in between):
            continue
        if any(f in between for f in FLIP_WORDS):
            continue  # 「没写过文档，但独立落地了系统」→ 转折后是肯定
        return True
    return False


def _limiter_scope(clause: str, action_idx: int) -> bool:
    """判断动作词是否被「只/仅/光」这类限定词限定住了动作范围。

    「只在课程作业里跑通过单 Agent 例子」→ 动作被"只"限定 → 只算部分具备。
    """
    prefix = _strip_inhibitors(clause[:action_idx])
    if not prefix:
        return False
    return any(w in prefix for w in LIMITER_WORDS)


def _weak_negative(line: str) -> bool:
    """行级弱否定：「只做过 demo」「简单」「粗略」「谈不上」等。

    这些不是"否定词 + 动作词"的构造，没法用作用域判定，
    但语义上同样表示"提了但没真做"，所以单独走一张短语表。
    """
    text = _strip_inhibitors(line)
    return any(n in text for n in NEGATIVE_MARKERS)


def _relevant_clauses(line: str, key: str) -> list[str]:
    """只保留提到了该能力关键词的子句。

    「没写过正式文档，但独立落地过内容运营项目」
    → 对 writing 能力，只有前半句相关；后半句的"落地"属于别的能力，
    不能拿来给 writing 当正向证据。
    """
    kws = [k.lower() for k in ALL_DIMS.get(key, {}).get("kw", [])]
    if not kws:
        return _clauses(line)
    out = [c for c in _clauses(line) if any(k in c.lower() for k in kws)]
    return out or _clauses(line)


def _evaluate_line(line: str, key: str) -> tuple[bool, bool, bool]:
    """判断一行对某个能力的作用。返回 (有正向证据, 有否定/限定信号, 强否定)。

    三条判定分开走，因为它们的适用范围不同：

    1. **强否定**（"没用过/没做过"）默认按整行判 ——
       「从没独立负责过项目，都是执行别人安排的任务」里，
       关键词落在下一句，但整句语义仍是"没有项目负责经验"。
       唯一的例外：若某个提到该能力的子句里有**明确的正向动作**，
       则不让整行的强否定把它判成缺失
       （「没用过 Python，但独立开发过 Java 服务」→ Java 不该跟着受牵连）。
    2. **否定/限定作用域**只看相关子句 ——
       「没写过正式文档，但独立落地过内容运营项目」里，
       "落地"是别的能力的事，不能给 writing 当正向证据。
    3. **正向证据**优先在相关子句里找；相关子句压根没有动作词时，
       退回整行找 —— 否则「用 Docker 部署了服务，配置了监控和告警」
       会因为"部署"不是动作词、而"配置"落在另一个子句，被误判成缺失。
    """
    rel = _relevant_clauses(line, key)
    all_clauses = _clauses(line)

    rel_neg = False
    rel_has_action = False
    rel_positive = False
    for c in rel:
        for idx in _find_actions(c):
            rel_has_action = True
            if _negation_scope(c, idx) or _limiter_scope(c, idx):
                rel_neg = True
            else:
                rel_positive = True

    scope = rel if rel_has_action else all_clauses
    positive = False
    for c in scope:
        for idx in _find_actions(c):
            if not (_negation_scope(c, idx) or _limiter_scope(c, idx)):
                positive = True
                break
        if positive:
            break

    # 强否定：整行判，但相关子句里有明确正向动作时不牵连
    line_strong = any(s in line for s in STRONG_NEGATIVE)
    strong = line_strong and not (rel_positive and not rel_neg)
    return positive, rel_neg, strong


def _profile_lines(profile: str) -> list[str]:
    lines = []
    for raw in profile.splitlines():
        if raw.strip().startswith("#"):
            continue  # 标题不是证据
        line = BULLET_RE.sub("", raw).strip()
        if len(line) >= 6:
            lines.append(line)
    return lines


def _claim_lines(lines: list[str], doc: str = "") -> dict[str, list[str]]:
    """把每一行归属给命中的能力。

    规则：命中词长度必须 >= 2；同一行里长度处于同一档（top-1 或 top-2）的能力都能认领，
    只有当某能力命中词明显更短（比最长短 2 以上）时才丢弃，避免一行后端描述把
    Python 和工程都算上，也避免几个平级能力互相挤掉。

    `doc` 传简历全文时，过泛词的语境判定会放宽到整篇简历
    （"有服务意识"是通用能力，不该被算成工程落地）。
    """
    owned: dict[str, list[str]] = {}
    for line in lines:
        hits = canonical_hits(line, doc=doc or line)
        if not hits:
            continue
        ranked = sorted(
            ((max(len(w) for w in words), key) for key, words in hits.items()),
            key=lambda x: (-x[0], x[1]),
        )
        # 词表扩到 189 项之后，一行可能同时命中十几个能力。固定取前 N 个会有两个问题：
        #   1) 短关键词（中文里大量能力词就是两个字：业务、沟通、会计、招聘…）
        #      会被更长的术语挤掉；
        #   2) 同长度之间的取舍只由 key 名字的字母序决定 —— 这是任意的。
        # 改成按证据强度分档：
        #   命中词 >= 3 字：多字术语，证据强，全部保留；
        #   命中词 == 2 字：弱证据，最多保留 _WEAK_KEEP 个，避免一行认领过多。
        strong = [k for length, k in ranked if length >= 3]
        weak = [k for length, k in ranked if length == 2][:_WEAK_KEEP]
        for key in strong + weak:
            owned.setdefault(key, []).append(line)
    return owned


def match_by_rules(requirements: list[Requirement], profile: str) -> dict[str, MatchResult]:
    lines = _profile_lines(profile)
    owned = _claim_lines(lines, doc=profile)
    results: dict[str, MatchResult] = {}
    for req in requirements:
        if req.key.startswith("custom:"):
            results[req.key] = _match_custom(req, lines)
            continue
        candidates = owned.get(req.key, [])
        if not candidates:
            results[req.key] = MatchResult(req.key, "missing")
            continue
        evidence = ""
        negated = False
        positive_found = False
        strong_neg = False
        for line in candidates:
            positive, scope_negated, strong = _evaluate_line(line, req.key)
            if strong:
                strong_neg = True
            weak_neg = _weak_negative(line)
            if positive and not scope_negated and not weak_neg:
                evidence = line[:110]
                positive_found = True
                break
            # 这一行不能作为正向证据（动作词被否定，或命中弱否定词）
            if not evidence:
                evidence = line[:110]
            if scope_negated or weak_neg:
                negated = True
        if strong_neg:
            results[req.key] = MatchResult(
                req.key,
                "missing",
                evidence=evidence or candidates[0][:110],
                note="明确写了『没用过/没做过』，判为缺失而非部分具备",
            )
            continue
        if not positive_found:
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
