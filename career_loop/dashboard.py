# -*- coding: utf-8 -*-
"""Streamlit 看板：投递漏斗 + 匹配分×正反馈散点（带置信区间）+ 缺口排行。

**这一层只负责画。** 所有数字来自 `dashdata.build_board()`，这里不重算任何东西——
这样「看板上的数」和「CLI 报告里的数」不可能对不上。

跑起来：
    career-loop dashboard                       # 自动挑数据源
    career-loop dashboard --records 台账.csv --profile 我的经历.md
    streamlit run career_loop/dashboard.py      # 直接跑也行
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import streamlit as st
except ImportError as exc:  # pragma: no cover - 只在没装 UI 依赖时走到
    raise SystemExit(
        "看板需要 streamlit：`pip install \"career-loop[ui]\"`（等价于 pip install streamlit）。\n"
        "核心功能（eval / calibrate / match / reflow / daily）不需要它。"
    ) from exc

# `streamlit run dashboard.py` 会把本文件当顶层脚本执行，包上下文丢失，
# 相对导入会失败。这里两种运行方式都要能跑。
try:
    from . import dashdata
except ImportError:  # pragma: no cover - 仅直接运行脚本时走到
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from career_loop import dashdata


def _svg(svg: str, height: int) -> None:
    """把 SVG 塞进 iframe 渲染。

    为什么不用 st.image / altair：这条路只依赖 streamlit 本体，
    少一层 pandas/altair 版本兼容问题；图是现成的字符串，截图分享也不会跑样。
    （早先用的是 st.components.v1.html，官方已标记在 2026-06-01 后移除，
    st.iframe 从很早的版本就有，两边都留得住。）
    """
    st.iframe(svg, height=height)


def _sidebar() -> dict:
    st.sidebar.header("数据源")
    st.sidebar.caption(
        "自动：**显式记录 > 本地库 > 演示数据**。演示数据是编的，只用来看面板长什么样。"
    )
    source = st.sidebar.selectbox(
        "数据来源",
        ["auto", "records", "db", "demo"],
        index=0,
        format_func=lambda s: {
            "auto": "自动（推荐）",
            "records": "回流记录文件",
            "db": "本地数据库",
            "demo": "演示数据（编造）",
        }[s],
    )
    mode = st.sidebar.radio(
        "正反馈口径",
        ["early", "terminal"],
        index=0,
        format_func=lambda m: dashdata.rf.MODE_LABEL.get(m, m),
        help=dashdata.rf.MODE_POSITIVE_DESC["early"],
    )
    records = st.sidebar.text_input(
        "回流记录文件（CSV/JSONL）",
        value=os.getenv("CAREER_LOOP_BOARD_RECORDS", ""),
        placeholder="例如 examples/reflow_demo_records.csv",
    )
    profile = st.sidebar.text_input(
        "经历文件",
        value=os.getenv("CAREER_LOOP_BOARD_PROFILE", "examples/profile_me.md"),
    )
    top_gaps = st.sidebar.slider("缺口排行显示条数", 3, 15, 8)
    return {
        "source": source,
        "mode": mode,
        "records": records.strip(),
        "profile": profile.strip(),
        "top_gaps": top_gaps,
    }


@st.cache_data(show_spinner="正在重算（同样的输入只算一次，换数据源才会重跑）")
def _compute(source: str, records: str, profile: str, mode: str, top_gaps: int):
    return dashdata.build_board(
        source,
        db=os.getenv("CAREER_LOOP_DB") or None,
        records_path=records or None,
        profile_path=profile or None,
        mode=mode,
        top_gaps=top_gaps,
    )


def _metrics(board: dashdata.BoardData) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("总投递", board.total)
    c2.metric("正反馈率", f"{board.positive_rate * 100:.1f}%")
    r = board.report.correlation if board.report else None
    c3.metric("相关系数 r", "—" if r is None else f"{r:+.3f}",
              help="Pearson：匹配分 ↔ 该口径下是否正反馈。不是录取概率。")
    ci = board.ci
    c4.metric("95% 置信区间",
              "—" if not ci or not ci.available else f"[{ci.lo:+.3f}, {ci.hi:+.3f}]",
              help="成对 bootstrap（固定种子，可复现）。区间跨 0 = 不能排除「两者无关」。")


def _panel_calibration(board: dashdata.BoardData) -> None:
    st.subheader("匹配分 × 是否正反馈")
    _svg(dashdata.render_scatter_svg(board), 330)
    st.caption(
        "点的纵坐标只是为了不叠在一起而做的抖动，不代表数值。"
        "琥珀虚线是分桶正反馈率（样本稀疏时只看点容易被单个点带偏）。"
    )
    ci = board.ci
    if ci and ci.available:
        st.write(f"**{ci.text}**")
        if ci.crosses_zero:
            st.warning(ci.verdict())
        else:
            st.success(ci.verdict())
    elif ci:
        st.warning(ci.verdict())
    if board.report:
        rows = [
            {"匹配分区间": f"{b.lo}-{b.hi}", "记录数": b.n,
             "正反馈数": b.positives, "正反馈率": f"{b.positive_rate * 100:.1f}%"}
            for b in board.report.buckets
        ]
        st.table(rows)
        st.info(f"引擎给的整体结论：{board.report.verdict}")


def _panel_details(board: dashdata.BoardData) -> None:
    rows = [
        {"岗位": r.label, "预测分": "—" if r.score is None else f"{float(r.score):.1f}",
         "状态": r.status_label, "正反馈": "✅" if r.positive else "—",
         "备注": r.note}
        for r in sorted(board.rows, key=lambda x: -(x.score or -1))
    ]
    # 这里仍用 use_container_width：pyproject 承诺 streamlit>=1.30，
    # 而替代它的 width="stretch" 要更新版本才有，换成它会把老环境挡在门外。
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _panel_limits(board: dashdata.BoardData) -> None:
    st.markdown(
        f"""
**这张图能说明什么、不能说明什么**

- 口径：**{board.mode_label}**（{board.positive_desc}）。换口径要重算，数字不可跨口径比较。
- **匹配分不是录取概率。** r 只回答「匹配分能不能预测这个口径下的正反馈」。
- 早期口径 ≠ 终局：「HR 理了我」和「我拿到 offer」是两个事件，前者的 r 高不代表后者也成立。
- 相关系数对样本量极其敏感。低于 8 条不给置信区间——那个量级下任何数字都可能来自一两次偶然。
- 数据来源：**{board.source_label}**。演示数据是编造的，不能当证据用。
"""
    )


def main() -> None:
    st.set_page_config(page_title="career-loop 看板", layout="wide", page_icon="🔁")
    st.title("career-loop · 投递校准看板")
    st.caption("把「我觉得我很匹配」变成一张能被打脸的图。")

    cfg = _sidebar()
    if not cfg["records"] and cfg["source"] == "records":
        st.error("选了「回流记录文件」但没填路径。")
        return
    board = _compute(cfg["source"], cfg["records"], cfg["profile"],
                     cfg["mode"], cfg["top_gaps"])

    if board.is_demo:
        st.error(
            "⚠️ 当前读到的是**演示数据**（仓库自带的编造样本），只用来演示面板长什么样。"
            "它跑出来的 r 高低与引擎的真实表现无关——**别拿这张图上的数字当证据**。"
            "接自己的数据：`career-loop dashboard --records 你的台账.csv --profile 你的经历.md`"
        )
    for w in board.warnings:
        st.caption("· " + w)

    if not board.rows:
        st.warning(
            "没有任何记录。先 `career-loop reflow --records 台账.csv --profile 经历.md` "
            "跑一遍回流，或者直接看演示数据。"
        )
        return

    _metrics(board)
    st.divider()

    t_funnel, t_calib, t_gaps, t_detail, t_limit = st.tabs(
        ["漏斗", "校准", "缺口排行", "明细", "边界"]
    )

    with t_funnel:
        _svg(dashdata.render_funnel_svg(board),
             60 + 36 * max(1, len(board.funnel)) + 30)
        st.caption("漏斗是**硬数据**，不依赖任何预测分——先确认这一层对不对，再看相关系数。")

    with t_calib:
        _panel_calibration(board)

    with t_gaps:
        st.subheader("下一步该补什么")
        _svg(dashdata.render_gaps_svg(board), 60 + 34 * max(1, len(board.gaps)) + 10)
        if board.gaps:
            rows = [
                {"能力项": g.label, "可多解锁": g.gained,
                 "具体岗位": "、".join(g.unlocked[:4]), "怎么补": g.fix}
                for g in board.gaps
            ]
            st.dataframe(rows, use_container_width=True, hide_index=True)

    with t_detail:
        st.subheader("逐条明细")
        _panel_details(board)

    with t_limit:
        _panel_limits(board)


if __name__ == "__main__":
    main()
