"""JD -> 结构化能力项。有 Key 走 LLM，无 Key 走规则基线。"""

from __future__ import annotations

import hashlib
import re

from .boilerplate import strip_boilerplate
from .llm import LLM, LLMError
from .schema import ALL_DIMS, Requirement, canonical_hits

SECTION_MARKERS = {
    "job": ["岗位职责", "工作职责", "工作内容", "职位描述", "你将", "职责",
            "essential duties", "essential functions", "job duties", "responsibilities",
            "what you will do", "the role", "your impact", "about the role",
            "position summary", "role overview", "job description"],
    "must": ["任职要求", "岗位要求", "任职资格", "基础要求", "要求",
             "requirements", "required", "qualifications", "minimum qualifications",
             "must have", "you have", "who you are", "minimum education",
             "basic qualifications", "we are looking for", "you should have"],
    "nice": ["优先条件", "加分项", "优先", "bonus",
             "nice to have", "preferred", "preferred qualifications", "plus",
             "good to have", "desirable", "extra credit"],
}

# 英文 JD 里大量"看起来像标题"的行：全大写段落名、URL、栏目标签。
# 它们会被规则基线当成一条"要求"，产出 custom 垃圾能力项
# （实测公开英文数据集上 custom 项占抽取总数 29.5%，严重稀释匹配分区分度）。
EN_NOISE_PATTERNS = [
    re.compile(r"https?://", re.I),
    re.compile(r"www\.", re.I),
    re.compile(r"^[A-Z0-9\s/&'()\-.,:#]{3,}$"),   # 全大写行
    re.compile(r"^(e-?mail|email)\s*[:：]?\s*\S+", re.I),
    re.compile(r"^(phone|tel|address|location|salary|posted|date)\s*[:：]", re.I),
    re.compile(r"^\W*$"),
    re.compile(r"[$¥€£]\s?\d"),                       # 薪资数字行
]

# 全大写标题判定：字母里 90% 以上是大写 → 是栏目标题，不是能力要求。
# 比字符白名单正则稳，因为标题里常有中文标点、弯引号、& 等杂字符。
_UPPER_RATIO = 0.9

# 英文 JD 常见的"栏目式"要求行（本身是模板文字，不是具体能力要求）
EN_TEMPLATE_PHRASES = [
    "hello folks", "hope you are", "we are looking for", "we want you",
    "please apply", "click here", "join our", "about us", "why you",
    "what we offer", "what we do", "our team", "our mission", "equal opportunity",
    "salary is", "benefits include", "how to apply", "good luck",
]

STRONG_WORDS = ["精通", "深入", "独立", "主导", "熟练掌握", "扎实", "闭环", "从0到1", "从 0 到 1"]

# 判断一行是否是「要求」（用于把词表未覆盖的要求也纳入，不静默丢弃）
REQ_SIGNALS = [
    "熟悉", "掌握", "具备", "能够", "会", "负责", "了解", "精通", "熟练", "经验",
    "优先", "要求", "独立", "完成", "参与", "维护", "开发", "设计", "管理", "推进",
    "分析", "制定", "执行", "对接", "沟通", "处理", "操作", "使用",
]
NOISE_MARKERS = [
    "薪资", "福利", "五险", "双休", "地点", "地址", "公司简介", "融资", "规模",
    "简历投递", "邮箱", "微信", "电话", "官网", "包吃", "补贴", "年终奖", "团建", "上班时间",
]


def _is_upper_heading(line: str) -> bool:
    """全大写标题行（ESSENTIAL DUTIES / MINIMUM EDUCATION…）判定。

    要求：字母数 >= 4，且其中 90% 以上是大写。
    中文行不含英文字母，天然不满足，不会误伤。
    """
    letters = [c for c in line if c.isalpha() and c.isascii()]
    if len(letters) < 4:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters) >= _UPPER_RATIO


def _is_noise_line(line: str) -> bool:
    """判断一行是不是 JD 模板噪声（URL、全大写标题、栏目标签、招呼语）。

    英文招聘 JD 有大量这类行。不滤掉的话，规则基线会把它们当成"要求"，
    产出一堆 custom 垃圾能力项，实测占抽取总数的 29.5%。
    """
    stripped = line.strip()
    if not stripped:
        return True
    low = stripped.lower()
    if any(p in low for p in EN_TEMPLATE_PHRASES):
        return True
    if _is_upper_heading(stripped):
        return True
    for pat in EN_NOISE_PATTERNS:
        if pat.search(stripped):
            return True
    return False


def _looks_like_requirement(line: str) -> bool:
    """在“职责/要求/优先”段里，只要不是噪声行，就当作要求。

    不再要求出现固定动词——否则「能读论文并复现实验」「英语可作为工作语言」
    这类没有标准动词的要求会被静默丢掉，跨行业覆盖就会漏。
    """
    if len(line) < 6 or len(line) > 120:
        return False
    if any(n in line for n in NOISE_MARKERS):
        return False
    if _is_noise_line(line):
        return False
    return True


def _custom_label(line: str) -> str:
    s = re.sub(r"^\s*(?:[-*+•]|\d+[.、)]|[（(]\d+[)）])\s*", "", line).strip()
    s = re.sub(r"^(负责|熟悉|掌握|具备|能够|要求|参与|独立|完成|了解|精通|熟练)", "", s)
    return (s[:16] or line[:16]).strip()


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


def _looks_like_title(line: str) -> bool:
    """JD 第一行常常是岗位名（没有 # 号），不能当成要求。

    判定用**双向判据**，不能只靠"含要求动词就不算标题"：
    只做否定判断时，遇到动词表以外的动词就一律误判成标题——
    实测真实中文 JD 里「具有较强的技术工程能力和技能」
    「吃苦耐劳，有良好的团队合作精神和组织协调能力」
    「与国内供应商建立并维护良好的合作关系」三条都被当成岗位名丢掉。

    规则：
    1. 太长 / 带句号 → 不是标题（要求行长这样）
    2. 含要求动词 → 不是标题
    3. **看起来像个岗位名**（短、以常见岗位后缀结尾、或就是职位名）→ 是标题
    4. 其余 → **不是标题**（宁可留，不可丢）
    """
    s = line.strip(" #*【】")
    # 去掉括号补充说明（"Java开发工程师（双休）" 的职位主体是"Java开发工程师"）
    s = re.split(r"[（(【\[]", s)[0].strip() or line.strip(" #*【】")
    if len(s) > 30:
        return False
    if any(p in s for p in "。；;！？"):
        return False
    verbs = ("负责", "要求", "熟悉", "掌握", "具备", "能够", "参与", "独立",
             "优先", "经验", "熟练", "了解", "精通", "使用", "会")
    if any(v in s for v in verbs):
        return False
    # 常见岗位名后缀 / 职位名形态 —— 只有这些才判成标题
    title_suffixes = ("工程师", "经理", "主管", "专员", "助理", "实习生", "顾问",
                      "总监", "组长", "部长", "代表", "开发", "设计", "运营",
                      "销售", "采购", "翻译", "教师", "讲师", "分析师", "BD")
    if any(s.endswith(x) for x in title_suffixes):
        return True
    # 极短的孤立词组（如「前端开发」「数据分析」）——但要含职位感
    if len(s) <= 8 and any(k in s for k in ("开发", "设计", "运营", "分析", "测试", "前端", "后端")):
        return True
    # 其余默认不是标题
    return False


def _split_inline_segments(line: str) -> list[str]:
    """把压在一行里的中文 JD 拆成独立要求条目。

    真实中文 JD 极常见这种写法（整个 JD 只有一行）：

        岗位职责：1、负责智能家电MCU固件开发；2、调试外设驱动、蓝牙通信；
        3、版本自测、bug闭环。任职要求：1、自动化/电子；2、熟悉C语言；…

    不拆的话，整段会被当成一行，`canonical_hits` 只能命中一个词
    （实测：这类 JD 平均只抽出 1 个能力项，"蓝牙通信""示波器"全漏）。

    切分点：分号 / 句号 / 中英文分节标题前。
    序号（1、2、3）保留在片段里，抽取时会剥掉。
    """
    # 先在分节标题前断开（"…bug闭环。任职要求：1、…"）
    parts: list[str] = []
    buf = ""
    i = 0
    n = len(line)
    while i < n:
        matched = False
        for section, markers in SECTION_MARKERS.items():
            for m in markers:
                # 标题必须出现在子句开头（前面只能有标点/空白），
                # 否则"有K8s项目优先"里的"优先"会被误当成 nice 段标题
                if not line.startswith(m, i):
                    continue
                if i > 0 and line[i - 1] not in "：:，,。；;、 \t":
                    continue
                head = buf.rstrip("：:，,。；; ")
                if head:
                    parts.append(head)
                parts.append("\x00SECTION:" + section)
                buf = ""
                i += len(m)
                matched = True
                break
            if matched:
                break
        if matched:
            continue
        ch = line[i]
        if ch in "；;。":
            seg = buf.strip("：:，, ")
            if seg:
                parts.append(seg)
            buf = ""
        else:
            buf += ch
        i += 1
    tail = buf.strip("：:，, ")
    if tail:
        parts.append(tail)
    return parts


def _split_sections(text: str) -> list[tuple[str, str]]:
    """把 JD 切成 (section, line) 列表。"""
    out: list[tuple[str, str]] = []
    current = "must"
    first = True
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#") or line.startswith("【") and len(line) < 24:
            continue  # 标题行不是要求，别让它变成依据
        marker = _detect_section(line)
        if marker:
            current = marker
            first = False
            continue
        if first:
            first = False
            if _looks_like_title(line):
                continue
        if len(line) < 6:
            continue  # 导航行/编号残片
        # 一行里可能压着多条要求（中文 JD 常见），拆开再处理
        for seg in _split_inline_segments(line):
            if seg.startswith("\x00SECTION:"):
                current = seg.split(":", 1)[1]
                continue
            seg = seg.strip()
            if len(seg) < 4:
                continue
            # 内联段来自明确编号的列表（"1、…" "2、…"），本身就是要求项，
            # 不该再套标题规则——否则「跟进线上问题排查」这类
            # 动词不在表里的真实职责会被误当成岗位名丢掉。
            out.append((current, seg))
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
    """无 LLM 时的基线：按词表命中 + 章节权重抽取能力项。

    对词表未覆盖的要求行，不再丢弃，而是生成一条 custom 要求，
    由匹配阶段按文本相似度判断——这样会计/销售/设计等非 AI 岗位也能被分析。

    入口先剥平台样板（来源声明/反诈免责声明，见 boilerplate.py）：
    这些句子会带着「证照」「招聘」等词误命中能力项，且不该出现在
    给用户看的 quote 里。
    """
    jd_text = strip_boilerplate(jd_text)
    best: dict[str, Requirement] = {}
    for section, line in _split_sections(jd_text):
        weight = _weight_for(section, line)
        hits = canonical_hits(line, doc=jd_text)
        if hits:
            for key in hits:
                existing = best.get(key)
                if existing is None or weight > existing.weight:
                    best[key] = Requirement(
                        key=key,
                        label=ALL_DIMS.get(key, {}).get("label", key),
                        weight=weight,
                        kind="nice" if weight == 1 else "must",
                        quote=line[:120],
                        section=section,
                    )
        elif _looks_like_requirement(line):
            ckey = "custom:" + hashlib.md5(line.encode("utf-8")).hexdigest()[:8]
            existing = best.get(ckey)
            if existing is None or weight > existing.weight:
                best[ckey] = Requirement(
                    key=ckey,
                    label=_custom_label(line),
                    weight=weight,
                    kind="nice" if weight == 1 else "must",
                    quote=line[:120],
                    section=section,
                )
    return sorted(best.values(), key=lambda r: -r.weight)


EXTRACT_SYSTEM = """你是资深招聘官。把 JD 拆成互不重叠的能力项。

只输出 JSON：
{"requirements":[{"key":"...","label":"中文能力名，不超过 12 字","weight":1|2|3,"kind":"must|nice","quote":"JD 原文片段，不超过 60 字"}]}

规则：
- 优先从输入的 known_keys 里选 key，key 必须与 known_keys 完全一致。
- 如果没有合适的 key，用 "custom:<简短 slug>"，并给出中文 label；不要发明 known_keys 之外的普通 key。
- weight: 3=核心硬门槛（精通/独立负责/必须），2=一般要求，1=优先/加分。
- 同一 key 只出现一次，取权重最高的一条依据。
- label 用中文，不超过 12 字；quote 必须逐字摘自 JD，不要编造。
- 只输出 JSON，不要解释。"""


def extract_by_llm(jd_text: str, llm: LLM) -> list[Requirement]:
    """LLM extraction is not limited to the built-in vocabulary.

    It may return a known key, a `custom:<slug>` key, or an invented key which we
    normalize to `llm:<slug>`. This is what lets it cover roles that have no pack.
    """
    payload = {
        "known_keys": {k: v["label"] for k, v in ALL_DIMS.items()},
        "jd": jd_text,
    }
    data = llm.json(EXTRACT_SYSTEM, f"输入：\n{payload}")
    best: dict[str, Requirement] = {}
    for item in data.get("requirements", []):
        key = str(item.get("key", "")).strip()
        label = str(item.get("label") or "").strip()
        if not key:
            continue
        if key in ALL_DIMS:
            label = label or ALL_DIMS[key]["label"]
        elif key.startswith(("custom:", "llm:")):
            if not label:
                continue
        else:
            if not label:
                continue
            slug = re.sub(r"[^a-z0-9\u4e00-\u9fa5_-]+", "-", key.lower()).strip("-")[:24] or "skill"
            key = f"llm:{slug}"
        weight = int(item.get("weight", 2))
        weight = min(3, max(1, weight))
        req = Requirement(
            key=key,
            label=label[:24],
            weight=weight,
            kind=item.get("kind") or ("nice" if weight == 1 else "must"),
            quote=(item.get("quote") or "")[:120],
        )
        prev = best.get(key)
        if prev is None or weight > prev.weight:
            best[key] = req
    if not best:
        raise LLMError("LLM 未抽取到有效能力项")
    return sorted(best.values(), key=lambda r: -r.weight)


def extract_requirements(jd_text: str, llm: LLM | None = None) -> tuple[list[Requirement], str]:
    if llm and llm.available:
        try:
            return extract_by_llm(jd_text, llm), "llm"
        except (LLMError, KeyError, ValueError):
            pass
    return extract_by_rules(jd_text), "rule"
