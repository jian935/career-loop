# -*- coding: utf-8 -*-
"""看板数据源：把「漏斗 / 校准 / 缺口」三块算成**纯数据**，Streamlit 只负责画。

为什么要多这一层，而不是在 dashboard.py 里直接算：

1. **能单测**。看板逻辑最容易出的问题是口径错（比如把 já 投递的当成正反馈），
   而这类 bug 在图表上根本看不出来——图照样画得出来。把计算抽到这里，
   没有 streamlit 也能跑测试。
2. **口径只有一份**。CLI 的 reflow 报告、Markdown 交付物、网页 demo 都从这里或其
   上游 reflow.py 取数，不会出现「报告里 r=-0.06、看板上 r=0.21」这种自打脸。
3. **来源必须显式**。数据到底是你自己的真实投递，还是我编的演示数据，
   决定了这张图能不能被当证据用。这条信息放在数据里，看板**躲不掉**它。
"""

from __future__ import annotations

import html
import random
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import recommend as rec_mod
from . import reflow as rf
from . import store
from .calibrate import CalibrationReport, CorrelationCI, calibrate, pearson_ci

ROOT = Path(__file__).resolve().parent.parent

#: 数据来源标识
SRC_DB = "db"
SRC_RECORDS = "records"
SRC_DEMO = "demo"

SOURCE_LABEL = {
    SRC_DB: "本地数据库（你自己的投递记录）",
    SRC_RECORDS: "回流记录文件（你自己导出的投递台账）",
    SRC_DEMO: "⚠️ 演示数据（仓库自带的编造样本）",
}

#: 演示数据用到的两个文件（都在 examples/ 下，README 里标注了是编的）
DEMO_RECORDS = ROOT / "examples" / "reflow_demo_records.csv"
DEMO_PROFILE = ROOT / "examples" / "profile_me.md"

#: 随机抖动的种子。散点上 y=0/1 两条线会把点全叠在一起，需要抖开；
#: 固定种子 → 同一份数据每次画出来形状一致（截图、对拍、写进单测都能复现）。
JITTER_SEED = 20261025


@dataclass
class FunnelStage:
    key: str
    label: str
    n: int
    total: int

    @property
    def rate(self) -> float:
        return self.n / self.total if self.total else 0.0


@dataclass
class BoardRow:
    """一条投递记录在看板上的形态。"""

    id: str
    title: str
    company: str
    score: Optional[float]
    status: str
    positive: bool
    note: str = ""

    @property
    def status_label(self) -> str:
        for names in rf.STATUS_NAMES.values():
            if self.status in names:
                return names[self.status]
        return self.status

    @property
    def label(self) -> str:
        head = f"{self.company}·" if self.company else ""
        return f"{head}{self.title or self.id or '（未命名）'}"


@dataclass
class ScatterPoint:
    label: str
    score: float
    positive: bool
    jitter: float


@dataclass
class GapItem:
    key: str
    label: str
    gained: int
    unlocked: list[str]
    fix: str = ""


@dataclass
class BoardData:
    """看板所需的全部数据。dashboard.py 只把这个对象画出来，不做任何计算。"""

    source: str = SRC_DEMO
    mode: str = "early"
    rows: list[BoardRow] = field(default_factory=list)
    funnel: list[FunnelStage] = field(default_factory=list)
    report: Optional[CalibrationReport] = None
    ci: Optional[CorrelationCI] = None
    scatter: list[ScatterPoint] = field(default_factory=list)
    gaps: list[GapItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def source_label(self) -> str:
        return SOURCE_LABEL.get(self.source, self.source)

    @property
    def is_demo(self) -> bool:
        return self.source == SRC_DEMO

    @property
    def total(self) -> int:
        return len(self.rows)

    @property
    def n_positive(self) -> int:
        return sum(1 for r in self.rows if r.positive)

    @property
    def positive_rate(self) -> float:
        return self.n_positive / self.total if self.total else 0.0

    @property
    def scored_rows(self) -> list[BoardRow]:
        return [r for r in self.rows if r.score is not None]

    @property
    def mode_label(self) -> str:
        return rf.MODE_LABEL.get(self.mode, self.mode)

    @property
    def positive_desc(self) -> str:
        return rf.MODE_POSITIVE_DESC.get(self.mode, "")


# --------------------------------------------------------------------------
# 读数据：三种来源，统一成 BoardData
# --------------------------------------------------------------------------


def _rows_from_db(db: Optional[str]) -> tuple[list[BoardRow], list[str]]:
    """从 SQLite 读投递记录。

    分数用**入库时的 fit_score**（看 fairness：那是你当时真正看到的分数），
    不在看板里重算——重算会引入"引擎改版导致历史分数对不上"的解释成本。
    """
    warnings: list[str] = []
    try:
        apps = store.list_applications_detail(db)
    except Exception as exc:  # 库不存在 / 表没建 / 权限问题，一律降级而不是崩掉
        return [], [f"读本地数据库失败（{type(exc).__name__}），已跳过这个来源。"]
    # positive 不在这里判：口径（early/terminal）由 _finalize 统一重判，避免两边跑偏。
    rows: list[BoardRow] = []
    for a in apps:
        status = str(a.get("status") or "applied")
        rows.append(
            BoardRow(
                id=str(a.get("id", "")),
                title=str(a.get("jd_title") or ""),
                company="",
                score=float(a["fit_score"]) if a.get("fit_score") is not None else None,
                status=status,
                positive=False,
                note=str(a.get("note") or ""),
            )
        )
    if not rows:
        warnings.append("本地数据库里还没有投递记录（`career-loop apply` 或 reflow --db-write 写入）。")
    return rows, warnings


def _rows_from_reflow(
    records_path: str | Path, profile_path: str | Path, mode: str, llm=None
) -> tuple[list[BoardRow], list[str]]:
    """从回流台账跑一遍 reflow 管线（漏斗/归因/方向全部复用 reflow 的口径）。"""
    warnings: list[str] = []
    profile = Path(profile_path).read_text(encoding="utf-8") if profile_path else ""
    if not profile.strip():
        return [], ["没有提供经历文件，无法给 JD 打分——只有漏斗，算不出相关系数。"]
    records = rf.load_records(records_path)
    if not records:
        return [], [f"没读到任何记录：{records_path}"]
    res = rf.analyze_reflow(records, profile, mode, llm)
    rows = [
        BoardRow(
            id=s.id,
            title=s.role,
            company=s.company,
            score=s.score,
            status=s.status,
            positive=s.positive,
            note=s.note,
        )
        for s in res.scored
    ]
    n_no_score = sum(1 for s in res.scored if s.score is None)
    if n_no_score:
        warnings.append(
            f"{n_no_score} 条记录没有 JD 原文，只进漏斗、不进相关系数（不拿编出来的分数充数）。"
        )
    return rows, warnings


def _finalize(
    rows: list[BoardRow], source: str, mode: str, *, profile: str = "",
    jd_pairs: Optional[list[tuple[str, str]]] = None, top_gaps: int = 8,
    gap_jd_limit: int = 24, llm=None, extra_warnings: Optional[list[str]] = None,
) -> BoardData:
    """把一批行封装成 BoardData：漏斗 → 校准 → 置信区间 → 散点 → 缺口。"""
    board = BoardData(source=source, mode=mode, rows=rows)
    if extra_warnings:
        board.warnings.extend(extra_warnings)

    # mode → positive 重判（DB 源读进来时按 early 判过一次，在这里统一）
    positives_set = rf.TERMINAL_POSITIVE if mode == "terminal" else rf.EARLY_POSITIVE
    for r in rows:
        r.positive = r.status in positives_set

    # 1. 漏斗
    counts = Counter(r.status for r in rows)
    board.funnel = [
        FunnelStage(key=k, label=rf.STATUS_NAMES.get(mode, {}).get(k, k),
                    n=counts.get(k, 0), total=board.total)
        for k in rf.FUNNEL_ORDER.get(mode, [])
        if counts.get(k, 0) > 0
    ]

    # 2. 校准 + 3. 置信区间（只用有分数的行）
    usable = board.scored_rows
    if len(usable) >= 5:
        scores = [float(r.score) for r in usable]
        pos = [r.positive for r in usable]
        board.report = calibrate(scores, pos)
        board.ci = pearson_ci(scores, pos)
    elif usable:
        board.warnings.append(
            f"只有 {len(usable)} 条带分数的记录，不足 5 条，算不出相关系数。"
        )

    # 4. 散点（含确定性抖动）
    rng = random.Random(JITTER_SEED)
    board.scatter = [
        ScatterPoint(
            label=r.label,
            score=float(r.score),
            positive=r.positive,
            jitter=(1.0 if r.positive else 0.0) + rng.uniform(-0.16, 0.16),
        )
        for r in usable
    ]

    # 5. 缺口排行：补哪一项能力，能多解锁几个 JD
    if not jd_pairs:
        board.warnings.append("没有可用的 JD 原文，跳过缺口排行。")
    elif not profile.strip():
        board.warnings.append("没有经历文本，跳过缺口排行。")
    else:
        pairs = jd_pairs[:gap_jd_limit]
        if len(jd_pairs) > gap_jd_limit:
            board.warnings.append(
                f"JD 太多，缺口排行只用了前 {gap_jd_limit} 份"
                "（该算法对每个候选能力项都要重算一遍，复杂度随 JD 数平方增长）。"
            )
        try:
            lev = rec_mod.gap_leverage(profile, pairs, threshold=70.0, llm=llm)
        except Exception as exc:  # 缺口排行是锦上添花，崩了不能拖垮整个看板
            board.warnings.append(f"缺口排行计算失败（{type(exc).__name__}），其余面板不受影响。")
            lev = []
        board.gaps = [
            GapItem(key=it["key"], label=it["label"], gained=it["gained"],
                    unlocked=it["jds"], fix=it.get("fix", ""))
            for it in lev
            if it["gained"] > 0
        ][:top_gaps]
        if not board.gaps:
            board.warnings.append("当前没有「补一项就能跨过 70% 线」的缺口（缺口较均衡）。")

    return board


def build_board(
    source: str = "auto",
    *,
    db: Optional[str] = None,
    records_path: Optional[str] = None,
    profile_path: Optional[str] = None,
    mode: str = "early",
    llm=None,
    top_gaps: int = 8,
    gap_jd_limit: int = 24,
) -> BoardData:
    """按优先级挑一个数据源，产出 BoardData。

    auto 的顺序：**显式指定 > 本地库 > 演示数据**。
    演示数据必须写在明面上——它是我编的，用来演示图会长什么样，不是证据。
    """
    if mode not in ("early", "terminal"):
        raise ValueError(f"未知口径：{mode}（只支持 early / terminal）")

    if source == "auto":
        source = SRC_RECORDS if records_path else (SRC_DB if _db_has_rows(db) else SRC_DEMO)

    if source == SRC_DEMO:
        rows, warns = _rows_from_reflow(DEMO_RECORDS, DEMO_PROFILE, mode, llm)
        warns = [*warns, "⚠️ 这份演示数据是**编造**的，用来演示面板长什么样；"
                         "它跑出来的 r 高低不代表引擎的真实表现。"]
        profile = DEMO_PROFILE.read_text(encoding="utf-8") if DEMO_PROFILE.exists() else ""
        pairs = _pairs_from_rows(DEMO_RECORDS)
        return _finalize(rows, SRC_DEMO, mode, profile=profile, jd_pairs=pairs,
                         top_gaps=top_gaps, gap_jd_limit=gap_jd_limit, llm=llm,
                         extra_warnings=warns)

    if source == SRC_DB:
        rows, warns = _rows_from_db(db)
        detail = _db_detail(db)
        profile = detail["profile"]
        pairs = detail["pairs"]
        return _finalize(rows, SRC_DB, mode, profile=profile, jd_pairs=pairs,
                         top_gaps=top_gaps, gap_jd_limit=gap_jd_limit, llm=llm,
                         extra_warnings=warns)

    if source == SRC_RECORDS:
        if not records_path:
            return BoardData(source=SRC_RECORDS, mode=mode,
                             warnings=["没有指定回流记录文件（--records）。"])
        rows, warns = _rows_from_reflow(records_path, profile_path or "", mode, llm)
        profile = Path(profile_path).read_text(encoding="utf-8") if profile_path else ""
        pairs = _pairs_from_rows(records_path)
        return _finalize(rows, SRC_RECORDS, mode, profile=profile, jd_pairs=pairs,
                         top_gaps=top_gaps, gap_jd_limit=gap_jd_limit, llm=llm,
                         extra_warnings=warns)

    raise ValueError(f"未知数据源：{source}（支持 db / records / demo）")


def _db_has_rows(db: Optional[str]) -> bool:
    try:
        return bool(store.list_applications_detail(db))
    except Exception:
        return False


def _db_detail(db: Optional[str]) -> dict:
    """从库里取「经历原文 + JD 原文」，给缺口排行用。"""
    try:
        apps = store.list_applications_detail(db)
    except Exception:
        return {"profile": "", "pairs": []}
    profile = ""
    pairs: list[tuple[str, str]] = []
    for a in apps:
        if not profile and a.get("profile_text"):
            profile = str(a["profile_text"])
        text = str(a.get("jd_text") or "").strip()
        if text:
            pairs.append((str(a.get("jd_title") or "未命名岗位"), text))
    return {"profile": profile, "pairs": pairs}


def _pairs_from_rows(records_path: str | Path) -> list[tuple[str, str]]:
    """从回流台账里抽出 (岗位名, JD 原文) 对。"""
    out: list[tuple[str, str]] = []
    for rec in rf.load_records(records_path):
        text = (rec.get("jd_text") or "").strip()
        if text:
            out.append((rec.get("role") or "未命名岗位", text))
    return out


# --------------------------------------------------------------------------
# SVG 图：为什么自己画而不用 pandas/altair
# --------------------------------------------------------------------------
#
# 1. 少一层依赖。跟着 streamlit 一起装的 pandas 版本是这个环境里最大的变量，
#    少依赖一个就少一处「别人装不上」。
# 2. 能在没有 streamlit 的环境里测试。图是纯字符串函数，
#    单测可以直接断言「恶意注入的标签被转义了」「漏斗顺序和口径一致」——
#    **图表是看板最容易悄悄出错的地方**：图照样画得出来，但画的可能不是你要的那个数。
# 3. 图上的每一行字都可控：口径、样本量、置信区间直接写在图里，截图发出去不会丢上下文。

FONT = "system-ui,-apple-system,'Microsoft YaHei','PingFang SC',sans-serif"
C_POS = "#0d9488"      # 正反馈（青）
C_NEG = "#94a3b8"      # 无正反馈（灰）
C_BAR = "#6366f1"      # 漏斗条（靛）
C_TREND = "#f59e0b"    # 分桶正反馈率折线（琥珀）
C_INK = "#1f2937"
C_MUTE = "#6b7280"
C_GRID = "#e5e7eb"


def _esc(s: object) -> str:
    """HTML 转义。

    JD 文本和岗位名是**外部输入**（用户粘贴的 JD 里可能带 `<` `&` 甚至 `<script>`），
    拼进 SVG 之前必须转义。这一行不加就是一个 XSS —— 看板虽然只跑在本机，
    但导出 SVG 分享出去就到别人浏览器里了。
    """
    return html.escape(str(s), quote=True)


def render_funnel_svg(board: BoardData, *, width: int = 680) -> str:
    """投递漏斗：横条 + 条数 + 占比。顺序就是 reflow 口径里定义的顺序。"""
    if not board.funnel:
        return '<p style="color:#6b7280">没有可画的漏斗数据。</p>'
    row_h, pad_l, pad_r, pad_t = 36, 168, 96, 30
    height = pad_t + row_h * len(board.funnel) + 26
    max_n = max(f.n for f in board.funnel) or 1
    inner = width - pad_l - pad_r
    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="{FONT}">',
        f'<text x="0" y="16" fill="{C_INK}" font-size="13" font-weight="600">'
        f'投递漏斗（{_esc(board.mode_label)}，共 {board.total} 条）</text>',
    ]
    for i, f in enumerate(board.funnel):
        y = pad_t + i * row_h
        w = max(2, int(f.n / max_n * inner))
        parts.append(
            f'<text x="0" y="{y + 18}" fill="{C_INK}" font-size="13">{_esc(f.label)}</text>'
        )
        parts.append(
            f'<rect x="{pad_l}" y="{y + 5}" width="{w}" height="18" rx="4" fill="{C_BAR}" '
            f'opacity="{0.45 + 0.55 * (f.n / max_n):.2f}"/>'
        )
        parts.append(
            f'<text x="{pad_l + w + 10}" y="{y + 19}" fill="{C_MUTE}" font-size="12">'
            f'{f.n} 条 · {f.rate * 100:.1f}%</text>'
        )
    parts.append(
        f'<text x="0" y="{height - 6}" fill="{C_MUTE}" font-size="11">'
        f'正反馈口径：{_esc(board.positive_desc)}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def render_scatter_svg(board: BoardData, *, width: int = 680, height: int = 300) -> str:
    """匹配分 × 是否正反馈 散点图，叠一条分桶正反馈率。

    散点本身看的是「每个点的位置」，分桶折线看的是「整体趋势」——
    两样放一起，是因为**点很稀疏时只看点会得出错觉**，必须有趋势线兜底。
    """
    if not board.scatter:
        return '<p style="color:#6b7280">没有带分数的记录，画不出散点。</p>'
    pad_l, pad_r, pad_t, pad_b = 40, 16, 26, 44
    pw = width - pad_l - pad_r
    ph = height - pad_t - pad_b
    y_pos = pad_t + ph * 0.28
    y_neg = pad_t + ph * 0.72

    def sx(v: float) -> float:
        return pad_l + max(0.0, min(100.0, float(v))) / 100 * pw

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="{FONT}">',
    ]
    # 标题行：把 r 和置信区间写进图里，截图不会丢口径
    head = "匹配分 × 正反馈"
    if board.ci:
        head += f"　{_esc(board.ci.text)}"
    parts.append(f'<text x="0" y="15" fill="{C_INK}" font-size="13" font-weight="600">{head}</text>')

    # 网格 + x 轴
    for t in range(0, 101, 20):
        x = sx(t)
        parts.append(f'<line x1="{x:.1f}" y1="{pad_t}" x2="{x:.1f}" y2="{pad_t + ph}" '
                     f'stroke="{C_GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{x:.1f}" y="{pad_t + ph + 16}" fill="{C_MUTE}" font-size="11" '
                     f'text-anchor="middle">{t}</text>')
    parts.append(f'<text x="{pad_l + pw / 2:.0f}" y="{height - 8}" fill="{C_MUTE}" font-size="11" '
                 f'text-anchor="middle">预测匹配分</text>')
    for y, name in ((y_pos, "有正反馈"), (y_neg, "无正反馈")):
        parts.append(f'<text x="0" y="{y + 4:.1f}" fill="{C_MUTE}" font-size="11">{name}</text>')

    # 分桶正反馈率折线（有 report 才画）
    if board.report:
        pts = []
        for b in board.report.buckets:
            if b.n:
                pts.append((sx((b.lo + b.hi) / 2), pad_t + ph - b.positive_rate * ph, b))
        if len(pts) >= 2:
            d = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y, _) in enumerate(pts))
            parts.append(f'<path d="{d}" fill="none" stroke="{C_TREND}" stroke-width="2" '
                         f'stroke-dasharray="5,3" opacity="0.9"/>')
            for x, y, b in pts:
                parts.append(f'<rect x="{x - 3.5:.1f}" y="{y - 3.5:.1f}" width="7" height="7" '
                             f'fill="{C_TREND}"><title>{_esc(b.lo)}-{_esc(b.hi)} 分：'
                             f'{b.n} 条，正反馈率 {b.positive_rate * 100:.1f}%</title></rect>')

    # 散点（y 轴抖动纯粹为了不重叠，不代表任何数值）
    for p in board.scatter:
        x = sx(p.score)
        y = y_pos if p.positive else y_neg
        y += p.jitter * ph * 0.30
        color = C_POS if p.positive else C_NEG
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}" fill-opacity="0.75" '
            f'stroke="#ffffff" stroke-width="1">'
            f'<title>{_esc(p.label)}　{float(p.score):.1f} 分　'
            f'{"有正反馈" if p.positive else "无正反馈"}</title></circle>'
        )
    parts.append("</svg>")
    return "".join(parts)


def render_gaps_svg(board: BoardData, *, width: int = 680) -> str:
    """缺口排行：补哪一项能力，能多解锁几个 JD（横向条形）。"""
    if not board.gaps:
        return '<p style="color:#6b7280">当前没有「补一项就能跨过 70% 线」的缺口。</p>'
    row_h, pad_l, pad_r, pad_t = 34, 210, 60, 30
    height = pad_t + row_h * len(board.gaps) + 10
    max_g = max(g.gained for g in board.gaps) or 1
    inner = width - pad_l - pad_r
    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="{FONT}">',
        f'<text x="0" y="16" fill="{C_INK}" font-size="13" font-weight="600">'
        f'最划算的补强：补上它能多解锁几个 JD</text>',
    ]
    for i, g in enumerate(board.gaps):
        y = pad_t + i * row_h
        w = max(2, int(g.gained / max_g * inner))
        tip = f"{g.label}：+{g.gained} 个岗位"
        if g.unlocked:
            tip += "\n" + "\n".join(g.unlocked[:6])
        if g.fix:
            tip += f"\n怎么补：{g.fix}"
        parts.append(f'<text x="0" y="{y + 18}" fill="{C_INK}" font-size="13">{_esc(g.label)}</text>')
        parts.append(f'<rect x="{pad_l}" y="{y + 5}" width="{w}" height="18" rx="4" '
                     f'fill="{C_POS}" opacity="0.85"><title>{_esc(tip)}</title></rect>')
        parts.append(f'<text x="{pad_l + w + 10}" y="{y + 19}" fill="{C_MUTE}" font-size="12">'
                     f'+{g.gained}</text>')
    parts.append("</svg>")
    return "".join(parts)
