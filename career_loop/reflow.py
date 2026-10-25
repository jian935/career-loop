# -*- coding: utf-8 -*-
"""投递回流分析：把「一批投递记录 + 你的简历」变成可证伪的校准结论。

这个模块回答两个**不同**的问题，必须分开算，混在一起会得出错误结论：

- **early（早期互动信号）**：招聘方有没有理我？
  口径：正反馈 = replied / interview / offer（HR 有实质动作）。
  仅"已读 / 入库 / 回执 / 待处理"都只是 applied，不算正反馈。
- **terminal（终局录取）**：我到底拿到 offer 了没？
  口径：正反馈 = 只有 offer。进了面试但淘汰是中间态，单独统计。

为什么必须分开：
早期信号和终局录取是两个不同的事件，样本量、噪声源都不同。
把"面试邀约"当成"录取"会虚高 r；把早期信号和终局混在一张表里
会得到一个谁也解释不了的中间值。**口径写在输出里，读者才知道 r 是什么意思。**

支持三种输入记录格式（自动嗅探，不用用户指定）：
- CSV：列名 id/company/role/jd_text/outcome/status/note 任选组合
- JSONL：每行一个 dict，字段同上
- JSON 数组：同上

关键约束：
- **只有含 JD 原文的记录才能算预测分**。没有 JD 原文的记录仍进漏斗统计
  （漏斗是硬数据），但不参与相关系数计算——否则会拿编出来的分数充数。
- 所有输出必须写明口径、样本量、以及"这不是录取概率"的边界。
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .calibrate import CalibrationReport, calibrate
from . import matching

# --------------------------------------------------------------------------
# 状态口径
# --------------------------------------------------------------------------

# 归一化状态。early 与 terminal 两种口径语义不同，各自用自己的一套：
# early 的"面试邀约"是还没结果的正向信号，terminal 的"面试淘汰"是已知失败。
# 正反馈判定因此也必须分开——只有 terminal 口径严格到"仅 offer"。
STATUS_OFFER = "offer"                                # 拿到 offer
STATUS_INTERVIEW = "interview"                        # early：面试邀约（还没结果）
STATUS_INTERVIEW_ELIMINATED = "interview_eliminated"  # terminal：进过面试但淘汰
STATUS_REPLIED = "replied"                            # HR 发起沟通 / 感兴趣 / 初筛通过
STATUS_APPLIED = "applied"                            # 仅投递 / 已读 / 入库 / 回执（无实质动作）
STATUS_REJECTED = "rejected"                          # 明确拒绝（简历关）
STATUS_SILENT = "silent"                              # 超期无反馈，结果未知

#: early 口径下的正反馈状态（招聘方有实质动作）
EARLY_POSITIVE = frozenset({STATUS_REPLIED, STATUS_INTERVIEW, STATUS_OFFER})
#: terminal 口径下的正反馈状态（只有拿到 offer 才算）
TERMINAL_POSITIVE = frozenset({STATUS_OFFER})

# 早期平台信号关键词 → 归一化状态。顺序敏感：先匹配更具体的。
#
# 判定原则（这条决定了 early 口径的 r 会不会虚高）：
# **只有招聘方明确做出的动作才算正反馈**，平台状态词不算。
# 「待联系」「待笔试通知」「待HR跟进」这类是平台把请求放进队列的标记，
# 招聘方本人还没动作 → 归 applied。
# 「HR发起沟通」「被标记有意向」「初筛通过」「面试邀约」才是对方真的动了 → 正反馈。
_EARLY_SIGNAL_RULES: list[tuple[str, tuple[str, ...]]] = [
    (STATUS_OFFER, ("offer", "录用", "发放offer", "接受offer")),
    (STATUS_INTERVIEW, ("面试邀约", "面试邀请", "约面", "发起面试", "面试")),
    (STATUS_REPLIED, ("hr沟通", "hr发起沟通", "发起沟通", "感兴趣", "有意向",
                       "初筛通过", "沟通中")),
    (STATUS_REJECTED, ("不合适", "已拒绝", "不予", "淘汰")),
]

# 终局结果文本 → 归一化状态
_TERMINAL_RULES: list[tuple[str, tuple[str, ...]]] = [
    (STATUS_OFFER, ("offer", "录用", "发放")),
    (STATUS_INTERVIEW_ELIMINATED, ("面试环节淘汰", "面试淘汰", "二面", "终面", "面试未通过")),
    (STATUS_SILENT, ("无反馈", "沉默", "超期")),
    (STATUS_REJECTED, ("简历筛选拒绝", "简历拒", "筛选拒绝", "拒绝", "不合适")),
]


def normalize_early_status(text: str) -> str:
    """把平台早期状态文本归一化。

    只有招聘方**真正有动作**才算正反馈；查看/已读/入库/回执都归 applied。
    """
    t = (text or "").strip()
    if not t:
        return STATUS_APPLIED
    for status, keys in _EARLY_SIGNAL_RULES:
        if any(k in t for k in keys):
            return status
    return STATUS_APPLIED


def normalize_terminal_outcome(text: str) -> str:
    """把终局结果文本归一化成 offer / interview / rejected / silent。"""
    t = (text or "").strip()
    if not t:
        return STATUS_SILENT
    for status, keys in _TERMINAL_RULES:
        if any(k in t for k in keys):
            return status
    return STATUS_REJECTED


def classify_outcome(text: str, mode: str) -> str:
    """按口径归一化状态。mode ∈ {early, terminal}。"""
    if mode == "terminal":
        return normalize_terminal_outcome(text)
    if mode == "early":
        return normalize_early_status(text)
    raise ValueError(f"未知口径：{mode}（只支持 early / terminal）")


# --------------------------------------------------------------------------
# 漏斗归因：简历关里多少是"你的问题"
# --------------------------------------------------------------------------

#: 外部/资格线因素——候选人难控，投再多也救不回来
EXTERNAL_FACTORS = (
    "hc", "冻结", "缩减", "收缩", "招满", "关闭", "取消", "名额", "学历", "本科", "硕士",
    "院校", "批次", "地点", "城市", "出差", "薪资", "优先已有", "竞争", "优先有",
    "已满", "暂停", "补招", "不接受", "现场经验", "行情相关", "合规项目",
)
#: 可控因素——改简历/补项目能挽回
CONTROLLABLE_FACTORS = (
    "缺少", "没有", "经验较少", "项目经历较少", "偏向学术", "学生demo",
    "笔试", "得分偏低", "未达到及格线",
)
#: 面试淘汰暴露的短板——面试前针对性准备能改
INTERVIEW_GAPS = (
    "偏保守", "创新性不足", "耗时过长", "结果出错", "理解不够深入", "偏差较大",
    "熟练度不足", "不扎实", "理解片面", "存在漏洞", "不够清晰", "不完善",
    "有偏差", "错误较多", "效率不达标", "同质化", "经验不足", "掌握薄弱",
)

ATTR_EXTERNAL = "不可控（HC/学历/地点/资格线）"
ATTR_CONTROLLABLE = "可控（改简历/补项目可挽回）"
ATTR_OTHER = "其他"


def attribute_rejection(note: str) -> str:
    """判断一条「简历关」拒绝的原因归属。

    归因靠回流备注的关键词分类，是**启发式**——备注是事后描述，可能有偏差。
    """
    n = (note or "").strip()
    if any(k in n.lower() for k in EXTERNAL_FACTORS):
        return ATTR_EXTERNAL
    if any(k in n for k in CONTROLLABLE_FACTORS):
        return ATTR_CONTROLLABLE
    return ATTR_OTHER


# --------------------------------------------------------------------------
# 岗位方向分类（按先到先得匹配，一个岗位只归一个方向）
# --------------------------------------------------------------------------

DIRECTIONS: list[tuple[str, tuple[str, ...]]] = [
    ("运营/增长", ("运营", "增长", "投放", "内容", "客服", "策划", "策略", "商家", "审核", "客户服务", "社区")),
    ("算法/AI", ("算法", "推荐", "视觉", "大模型", "模型", "slam", "nlp", "感知", "扫地机器人")),
    ("测试/质量", ("测试", "qa", "质量", "验证")),
    ("后端/服务端", ("后端", "服务端", "后台", "存储", "行情", "直播", "流媒体", "hpc", "运维开发")),
    ("移动/客户端", ("安卓", "android", "客户端", "车载", "ios", "app")),
    ("产品", ("产品", "实施顾问")),
    ("嵌入式/硬件", ("嵌入式", "硬件", "固件", "iot", "结构", "plc", "芯片", "器件", "mcu", "电池", "射频", "音频", "音质", "相机", "机械")),
    ("前端", ("前端", "h5")),
    ("金融/研究", ("研究", "资管", "投行", "证券", "投资", "理财", "基金", "信托", "行研", "拓展")),
    ("数据/数分", ("数据", "数分", "分析")),
    ("安全", ("安全", "攻防", "风控", "渗透")),
    ("生物医药", ("生物", "药", "临床", "cra")),
    ("解决方案/售前", ("解决方案", "售前", "投标")),
]


#: 通用词：命中只给 1 分（不足以单独决定方向）
_GENERIC_TERMS = frozenset({
    "运营", "分析", "研究", "策划", "策略", "管理", "服务", "内容", "工作", "项目",
})
#: 专有词：命中给 3 分（强烈指向该方向）
_SPECIFIC_TERMS = frozenset({
    "算法", "推荐", "视觉", "大模型", "模型", "后端", "服务端", "后台", "存储", "行情",
    "流媒体", "运维开发", "客户端", "安卓", "android", "车载", "嵌入式", "硬件", "固件",
    "iot", "plc", "芯片", "器件", "mcu", "电池", "射频", "音质", "相机", "机械", "前端",
    "h5", "资管", "投行", "证券", "理财", "基金", "信托", "行研", "数分", "攻防", "渗透",
    "临床", "cra", "售前", "投标", "投放", "客服", "商家", "测试", "qa", "质量", "产品",
    "增长", "slam", "nlp", "感知", "生物", "药",
})


def classify_direction(role: str) -> str:
    """把岗位名归到一个方向。

    用**加权计分**而非"先到先得"：通用词会互相抢位——
    「安全攻防研究员」含"研究"会被金融抢走，「安全运营分析师」含"运营"会被运营抢走。
    计分规则：命中一个**专有词**（攻防/投行/嵌入式…）给 3 分，
    命中一个**通用词**（研究/运营/分析…）给 1 分；同分时按本表顺序。
    """
    low = (role or "").lower()
    if not low.strip():
        return "其他"
    best_name = "其他"
    best_score = 0
    best_pos = 10**6
    for name, kws in DIRECTIONS:
        score = 0
        first_pos = 10**6
        for k in kws:
            pos = low.find(k)
            if pos < 0:
                continue
            score += 3 if k in _SPECIFIC_TERMS else 1
            first_pos = min(first_pos, pos)
        # 同分时看命中位置：岗位名里更靠前的词通常是主方向
        # （「安全运营分析师」→ 安全在前；「用户增长运营」→ 增长/运营在前）
        if score > best_score or (score == best_score and score > 0 and first_pos < best_pos):
            best_score = score
            best_name = name
            best_pos = first_pos
    return best_name


# --------------------------------------------------------------------------
# 记录读取（CSV / JSONL / JSON 数组，字段自动嗅探）
# --------------------------------------------------------------------------

#: 投递 ID 的候选列名
_ID_KEYS = ("id", "idx", "投递id", "投递ID", "record_id", "no")
#: 公司
_COMPANY_KEYS = ("company", "公司", "公司名称", "employer")
#: 岗位名
_ROLE_KEYS = ("role", "岗位", "岗位名称", "title", "position", "job_title")
#: JD 原文
_JD_KEYS = ("jd_text", "jd", "jd原文", "jd_原文", "job_description", "description", "原文")
#: 结果 / 状态文本
_OUTCOME_KEYS = ("outcome", "status", "status_text", "结果", "终局结果", "状态", "result")
#: 备注
_NOTE_KEYS = ("note", "备注", "回流备注", "remark", "comment")
#: 岗位族（可选，可由引擎推断）
_DOMAIN_KEYS = ("domain", "岗位族", "family")
#: 投递日期
_DATE_KEYS = ("apply_date", "date", "投递时间", "投递日期")


def _pick(row: dict, keys: Iterable[str]) -> str:
    for k in keys:
        if k in row and row[k] is not None:
            v = str(row[k]).strip()
            if v:
                return v
    return ""


def _norm_key(k: str) -> str:
    return (k or "").strip().lower().lstrip("﻿")


def _row_to_record(row: dict) -> dict:
    """把一行原始 dict 归一成内部记录结构。"""
    r = {_norm_key(k): ("" if v is None else str(v).strip()) for k, v in row.items()}
    return {
        "id": _pick(r, _ID_KEYS),
        "company": _pick(r, _COMPANY_KEYS),
        "role": _pick(r, _ROLE_KEYS),
        "jd_text": _pick(r, _JD_KEYS),
        "outcome_text": _pick(r, _OUTCOME_KEYS),
        "note": _pick(r, _NOTE_KEYS),
        "domain": _pick(r, _DOMAIN_KEYS),
        "date": _pick(r, _DATE_KEYS),
    }


def load_records(path: str | Path) -> list[dict]:
    """读投递记录，自动识别 CSV / JSONL / JSON 数组。"""
    p = Path(path)
    text = p.read_text(encoding="utf-8-sig")
    stripped = text.lstrip()
    if stripped.startswith("["):
        raw = json.loads(text)
        rows = raw if isinstance(raw, list) else [raw]
    elif stripped.startswith("{"):
        # 可能是 JSON 数组被换行拆开，也可能是一个 dict
        try:
            raw = json.loads(text)
            rows = raw if isinstance(raw, list) else [raw]
        except json.JSONDecodeError:
            rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        # CSV 或 JSONL：先试 JSONL，再退回 CSV
        rows = []
        ok = True
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                ok = False
                break
        if not ok:
            rows = list(csv.DictReader(text.splitlines()))
    return [_row_to_record(r) for r in rows if isinstance(r, dict)]


# --------------------------------------------------------------------------
# 打分 + 校准
# --------------------------------------------------------------------------


@dataclass
class ScoredRecord:
    """一条投递记录的完整分析结果。"""

    record: dict
    mode: str
    status: str = ""
    score: float | None = None
    n_reqs: int = 0
    n_custom: int = 0
    domain: str = "未识别"
    positive: bool = False
    attr: str = ""

    @property
    def id(self) -> str:
        return self.record.get("id", "")

    @property
    def company(self) -> str:
        return self.record.get("company", "")

    @property
    def role(self) -> str:
        return self.record.get("role", "")

    @property
    def outcome_text(self) -> str:
        return self.record.get("outcome_text", "")

    @property
    def note(self) -> str:
        return self.record.get("note", "")


def score_records(
    records: list[dict], profile: str, mode: str, llm=None
) -> list[ScoredRecord]:
    """给每条记录算预测匹配分，并按口径判定正反馈。

    没有 JD 原文的记录 score=None —— 它仍进漏斗统计，但不参与相关系数。
    """
    out: list[ScoredRecord] = []
    positives_map = EARLY_POSITIVE if mode == "early" else TERMINAL_POSITIVE
    for rec in records:
        sr = ScoredRecord(record=rec, mode=mode)
        sr.status = classify_outcome(rec.get("outcome_text", ""), mode)
        sr.positive = sr.status in positives_map
        jd = rec.get("jd_text", "")
        if jd.strip():
            reqs, _ = matching.extract_requirements(jd, llm)
            sr.n_reqs = len(reqs)
            sr.n_custom = sum(1 for r in reqs if r.key.startswith("custom:"))
            if reqs:
                matches, _ = matching.match(reqs, profile, llm)
                sr.score = matching.score(reqs, matches)
            doms = matching.detect_domains(jd)
            sr.domain = doms[0] if doms else "未识别"
        if sr.status == STATUS_REJECTED:
            sr.attr = attribute_rejection(sr.note)
        out.append(sr)
    return out


@dataclass
class ScoreSpread:
    """分数分布诊断：判断 r 低到底是引擎没区分度，还是数据本身无关联。"""

    min_score: float = 0.0
    max_score: float = 0.0
    median_score: float = 0.0
    buckets: Counter = field(default_factory=Counter)
    positive_median: float | None = None
    negative_median: float | None = None
    n_pos: int = 0
    n_neg: int = 0

    @property
    def spread(self) -> float:
        return self.max_score - self.min_score

    def diagnose(self) -> str:
        """给出一句可读判断。"""
        if self.n_pos == 0 or self.n_neg == 0:
            return "只有一类结果，算不出正负两组对比——先把正负样本都攒够。"
        gap = self.positive_median - self.negative_median
        if abs(gap) < 5:
            return (f"正负两组的分数中位数几乎一样（{self.positive_median:.0f} vs "
                    f"{self.negative_median:.0f}），分布几乎完全重叠——"
                    "**这更像「结果与岗位契合度本来就无关」，而不是引擎没区分度**。")
        if gap > 0:
            return (f"正反馈组中位分比非正反馈组高 {gap:.0f} 分，方向是对的，"
                    "但差距不够大，样本量不足以让 r 显著。")
        return (f"正反馈组中位分反而比非正反馈组低 {abs(gap):.0f} 分，方向是反的。"
                "两种可能：① 引擎打分口径有问题（该给高分的岗位没给）；"
                "② 这批结果本身与岗位契合度无关（换个更强的打分器也一样）。"
                "**先看下面的逐条明细里那些「低分却拿到 offer」的岗位**——"
                "如果它们明显是些门槛不高的岗位，那就是 ②。")


def diagnose_spread(scored: list[ScoredRecord]) -> ScoreSpread:
    """诊断预测分的分布，判断 r 低的成因。"""
    usable = [s for s in scored if s.score is not None]
    sp = ScoreSpread()
    if not usable:
        return sp
    scores = sorted(float(s.score) for s in usable)
    sp.min_score = scores[0]
    sp.max_score = scores[-1]
    mid = len(scores) // 2
    sp.median_score = scores[mid] if len(scores) % 2 else (scores[mid - 1] + scores[mid]) / 2
    for s in usable:
        sp.buckets[int(s.score // 20) * 20] += 1
    pos = sorted(float(s.score) for s in usable if s.positive)
    neg = sorted(float(s.score) for s in usable if not s.positive)
    sp.n_pos = len(pos)
    sp.n_neg = len(neg)
    if pos:
        sp.positive_median = pos[len(pos) // 2]
    if neg:
        sp.negative_median = neg[len(neg) // 2]
    return sp


@dataclass
class ReflowResult:
    """一次回流分析的完整结果。"""

    mode: str
    scored: list[ScoredRecord] = field(default_factory=list)
    report: CalibrationReport | None = None
    status_counts: Counter = field(default_factory=Counter)
    attr_counts: Counter = field(default_factory=Counter)
    direction_stats: dict[str, list[int]] = field(default_factory=dict)
    spread: ScoreSpread = field(default_factory=ScoreSpread)

    @property
    def total(self) -> int:
        return len(self.scored)

    @property
    def n_positive(self) -> int:
        return sum(1 for s in self.scored if s.positive)

    @property
    def scored_usable(self) -> list[ScoredRecord]:
        return [s for s in self.scored if s.score is not None]

    @property
    def positive_rate(self) -> float:
        return self.n_positive / self.total if self.total else 0.0


def analyze_reflow(records: list[dict], profile: str, mode: str, llm=None) -> ReflowResult:
    """跑完整回流分析：打分 → 校准 → 漏斗归因 → 方向统计。"""
    if mode not in ("early", "terminal"):
        raise ValueError(f"未知口径：{mode}（只支持 early / terminal）")
    scored = score_records(records, profile, mode, llm)
    usable = [s for s in scored if s.score is not None]
    scores = [float(s.score) for s in usable]
    positives = [s.positive for s in usable]
    report = calibrate(scores, positives) if len(scores) >= 5 else None

    res = ReflowResult(mode=mode, scored=scored, report=report)
    res.status_counts = Counter(s.status for s in scored)
    res.attr_counts = Counter(s.attr for s in scored if s.attr)

    dstat: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # 投递, 正反馈
    for s in scored:
        d = classify_direction(s.role)
        dstat[d][0] += 1
        if s.positive:
            dstat[d][1] += 1
    res.direction_stats = dict(dstat)
    res.spread = diagnose_spread(scored)
    return res


# --------------------------------------------------------------------------
# 报告渲染
# --------------------------------------------------------------------------

_MODE_LABEL = {
    "early": "早期互动信号（HR 有没有理我）",
    "terminal": "终局录取（有没有拿到 offer）",
}
_MODE_POSITIVE_DESC = {
    "early": "正反馈 = HR 沟通 / 感兴趣 / 初筛通过 / 面试邀约 / offer",
    "terminal": "正反馈 = 只有拿到 offer（进面试但淘汰是中间态，单列）",
}


def render_report(
    res: ReflowResult,
    *,
    title: str = "投递回流校准报告",
    data_note: str = "",
    profile_label: str = "你的经历",
) -> str:
    """把 ReflowResult 渲染成 markdown 报告。"""
    L: list[str] = []
    L.append(f"# {title}\n")
    L.append(f"> 口径：**{_MODE_LABEL[res.mode]}**　｜　{_MODE_POSITIVE_DESC[res.mode]}")
    if data_note:
        L.append(f"> 数据：{data_note}")
    L.append(f"> 匹配分来源：{profile_label} × 各条 JD 原文（规则引擎，无模型 API）\n")

    # 1. 漏斗
    L.append("## 1. 漏斗（硬数据，不依赖任何预测分）\n")
    total = res.total
    L.append(f"- 总投递：**{total}**")
    if res.mode == "terminal":
        order = [STATUS_OFFER, STATUS_INTERVIEW_ELIMINATED, STATUS_REJECTED, STATUS_SILENT]
        names = {
            STATUS_OFFER: "拿到 offer",
            STATUS_INTERVIEW_ELIMINATED: "进面试但淘汰",
            STATUS_REJECTED: "简历关拒绝",
            STATUS_SILENT: "沉默（结果未知）",
        }
    else:
        order = [STATUS_OFFER, STATUS_INTERVIEW, STATUS_REPLIED, STATUS_APPLIED, STATUS_SILENT]
        names = {
            STATUS_OFFER: "offer",
            STATUS_INTERVIEW: "面试邀约",
            STATUS_REPLIED: "HR 有实质沟通",
            STATUS_APPLIED: "仅投递/已读，无动作",
            STATUS_SILENT: "沉默（结果未知）",
        }
    for k in order:
        n = res.status_counts.get(k, 0)
        if n:
            L.append(f"  - {names[k]}：{n}（{n / total * 100:.1f}%）")
    L.append(f"\n- **正反馈率：{res.n_positive}/{total} = {res.positive_rate * 100:.1f}%**")
    if res.mode == "terminal":
        rej = res.status_counts.get(STATUS_REJECTED, 0)
        itv = res.status_counts.get(STATUS_INTERVIEW_ELIMINATED, 0)
        off = res.status_counts.get(STATUS_OFFER, 0)
        if rej:
            L.append(f"- 简历通过率（进面试+offer）：{(off + itv) / total * 100:.1f}%")
        if off + itv:
            L.append(f"- 面试→offer 转化：{off / (off + itv) * 100:.1f}%")
    L.append("")

    # 2. 校准
    L.append("## 2. 校准：预测匹配分 ↔ 真实结果\n")
    usable = res.scored_usable
    if res.report is None:
        L.append(f"- 有效样本只有 {len(usable)} 条，不足 5 条，算不出可信的相关系数。")
        L.append("- 继续积累投递与回流记录，攒够 5 条以上再回来看。\n")
    else:
        rep = res.report
        L.append(f"- 参与相关系数计算的样本：**{rep.n}**"
                 f"（总记录 {total}，其中 {total - len(usable)} 条没有 JD 原文，无法算预测分）")
        L.append(f"- 整体正反馈率：{rep.positive_rate}")
        L.append(f"- **Pearson r = {rep.correlation}**")
        L.append(f"\n> {rep.verdict}\n")
        L.append("### 分桶正反馈率\n")
        L.append("| 匹配分区间 | 记录数 | 正反馈数 | 正反馈率 |")
        L.append("| --- | --- | --- | --- |")
        for b in rep.buckets:
            if b.n == 0:
                L.append(f"| {b.lo}-{b.hi} | 0 | 0 | — |")
            else:
                L.append(f"| {b.lo}-{b.hi} | {b.n} | {b.positives} | {b.positives / b.n * 100:.1f}% |")
        L.append("")

    # 3. 分数分布诊断（回答"r 低到底怪谁"）
    sp = res.spread
    if sp.n_pos and sp.n_neg:
        L.append("### r 低的时候，先看分布再下结论\n")
        L.append(f"- 预测分区间：{sp.min_score:.0f} ~ {sp.max_score:.0f}（跨度 {sp.spread:.0f} 分）"
                 f"，全部 {sp.n_pos + sp.n_neg} 条中位 {sp.median_score:.0f} 分")
        L.append(f"- **正反馈组中位分 {sp.positive_median:.0f}** vs "
                 f"**非正反馈组中位分 {sp.negative_median:.0f}**")
        L.append("")
        L.append(f"> {sp.diagnose()}\n")
        L.append("> 这一步很重要：**r ≈ 0 有两种完全不同的成因**——"
                 "① 引擎打分没有区分度（它该给高分的没给）；"
                 "② 结果与岗位契合度本来就无关（数据里就是这样，换个更强的模型也一样）。"
                 "看正负两组的分数分布重叠不重叠，才能判断该修引擎还是该认这个数据。\n")

    # 4. 漏斗归因
    if res.attr_counts:
        L.append("## 3. 简历关归因：多少是「你的问题」\n")
        L.append("| 归因 | 条数 | 占简历关 |")
        L.append("| --- | --- | --- |")
        rej = res.status_counts.get(STATUS_REJECTED, 0) or 1
        for k, v in res.attr_counts.most_common():
            L.append(f"| {k} | {v} | {v / rej * 100:.0f}% |")
        L.append("")
        ext = res.attr_counts.get(ATTR_EXTERNAL, 0)
        ctl = res.attr_counts.get(ATTR_CONTROLLABLE, 0)
        if rej:
            L.append(f"**结论：简历关 {rej} 条里，{ext} 条（{ext / rej * 100:.0f}%）是外部/资格线因素**"
                     "（HC 冻结、岗位招满、学历门槛、地点冲突、名额已满），跟简历写得好不好没关系；"
                     f"真正能靠改简历/补项目挽回的只有 {ctl} 条（{ctl / rej * 100:.0f}%）。\n")

    # 4. 方向对比
    if res.direction_stats:
        L.append("## 4. 方向对比：往哪投回报高\n")
        L.append("| 方向 | 投递 | 正反馈 | 正反馈率 | 样本可信度 |")
        L.append("| --- | --- | --- | --- | --- |")
        for d, (n, p) in sorted(res.direction_stats.items(), key=lambda kv: (-kv[1][0], kv[0])):
            if n >= 5:
                trust = "可用"
            elif n >= 3:
                trust = "偏弱（n<5）"
            else:
                trust = "**仅供参考**（n<3）"
            L.append(f"| {d} | {n} | {p} | {p / n * 100:.1f}% | {trust} |")
        L.append("")
        L.append("> ⚠️ 只有「投递 ≥ 5 条」的方向才谈得上方向性参考。"
                 "n<3 的行（正反馈率 100% 之类）纯属巧合，别当结论。\n")

    # 5. 引擎行为
    if usable:
        n_custom = sum(s.n_custom for s in usable)
        n_reqs = sum(s.n_reqs for s in usable)
        L.append("## 5. 引擎在这批 JD 上的行为\n")
        L.append(f"- 平均抽出能力项：**{n_reqs / len(usable):.1f}** 个/JD")
        L.append(f"- custom（词表未覆盖）项占比：**{n_custom / max(1, n_reqs) * 100:.1f}%**")
        L.append(f"- 抽不出任何能力项的 JD：**{sum(1 for s in res.scored if s.score is None)}** 条")
        L.append("")

    # 6. 逐条明细
    if usable:
        L.append("## 6. 逐条明细（按预测分排序）\n")
        L.append("| ID | 公司 | 岗位 | 预测分 | 能力项 | custom | 归一状态 |")
        L.append("| --- | --- | --- | --- | --- | --- | --- |")
        for s in sorted(usable, key=lambda x: -(x.score or 0)):
            L.append(f"| {s.id} | {s.company} | {s.role} | {s.score:.1f} | "
                     f"{s.n_reqs} | {s.n_custom} | {s.status} |")
        L.append("")

    # 7. 边界
    L.append("## 7. 边界（必须说清）\n")
    L.append("- **匹配分不是录取概率。** 这里的 r 只回答「匹配分能不能预测这个口径下的正反馈」，"
             "不代表对任意人、任意岗位都成立。")
    L.append("- 归因靠回流备注的关键词分类，是**启发式**；备注是事后描述，可能有偏差。")
    if res.mode == "early":
        L.append("- 早期信号 ≠ 终局结果。「HR 理了我」与「我拿到 offer」是两个事件，"
                 "早期 r 高不代表能预测录取；想看终局口径请用 `--mode terminal`。")
    else:
        L.append("- 只有拿到 offer 才算正反馈，样本量小、offer 率低时 r 的置信区间很宽，"
                 "n<30 基本只能当方向性参考。")
    if total - len(usable) > 0:
        L.append(f"- 有 {total - len(usable)} 条记录没有 JD 原文，只进了漏斗统计、没进相关系数计算。")
    L.append("")
    return "\n".join(L)


def render_console_summary(res: ReflowResult) -> str:
    """控制台摘要（与报告同口径）。"""
    L = []
    L.append("=" * 56)
    L.append(f"投递回流校准　口径：{_MODE_LABEL[res.mode]}")
    L.append("=" * 56)
    L.append(f"总记录 {res.total} 条 | 正反馈 {res.n_positive} 条 ({res.positive_rate * 100:.1f}%)")
    usable = res.scored_usable
    L.append(f"参与相关系数计算 {len(usable)} 条（{res.total - len(usable)} 条缺 JD 原文未参与）")
    if res.report is not None:
        L.append("")
        L.append(f"预测分 ↔ 真实结果：Pearson r = {res.report.correlation}  (n={res.report.n})")
        L.append("分桶正反馈率：")
        for b in res.report.buckets:
            if b.n:
                bar = "#" * int(b.positive_rate * 30)
                L.append(f"  {b.lo:>3}-{b.hi:<3} n={b.n:<3} 率={b.positive_rate:<5} {bar}")
        L.append("")
        L.append(f"结论：{res.report.verdict}")
    else:
        L.append("")
        L.append("有效样本不足 5 条，算不出可信的相关系数。")
    if res.attr_counts:
        L.append("")
        L.append("简历关归因：")
        for k, v in res.attr_counts.most_common():
            L.append(f"  {k:<28} {v:>2} 条")
    return "\n".join(L)
