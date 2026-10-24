"""Streamlit 看板：投递漏斗 + 校准曲线。无数据时用示例数据演示。"""

from __future__ import annotations

import os
import sqlite3

import streamlit as st

from . import calibrate as calib_mod
from . import store


def _load(db: str | None):
    try:
        rows = store.calibration_rows(db)
    except Exception:
        rows = []
    if not rows:
        # 演示：没有真实数据时读示例
        demo = os.path.join(os.path.dirname(__file__), "..", "data", "demo_applications.jsonl")
        try:
            import json
            from pathlib import Path
            rows = []
            for line in Path(demo).read_text(encoding="utf-8").splitlines():
                if line.strip():
                    d = json.loads(line)
                    rows.append(store.CalibrationRow(0, float(d["fit_score"]), bool(d["positive"]), ""))
        except Exception:
            rows = []
    return rows


def main() -> None:
    st.set_page_config(page_title="career-loop", layout="wide")
    db = os.getenv("CAREER_LOOP_DB")
    st.title("career-loop · 求职漏斗校准看板")

    rows = _load(db)
    if not rows:
        st.warning("还没有数据，先 `career-loop apply` 记录投递，或 `calibrate --data data/demo_applications.jsonl` 看演示。")
        return

    scores = [r.fit_score for r in rows]
    positives = [r.positive for r in rows]
    report = calib_mod.calibrate(scores, positives)

    c1, c2, c3 = st.columns(3)
    c1.metric("样本量", report.n)
    c2.metric("正反馈率", f"{report.positive_rate:.0%}")
    c3.metric("相关系数 r", f"{report.correlation}")

    st.subheader("分桶正反馈率（匹配分越高，真的越容易收到回复吗？）")
    data = [{"区间": f"{b.lo}-{b.hi}", "样本": b.n, "正反馈率": b.positive_rate} for b in report.buckets]
    st.bar_chart({d["区间"]: d["正反馈率"] for d in data})

    st.subheader("结论")
    st.info(report.verdict)

    st.subheader("投递明细")
    st.table({
        "匹配分": scores,
        "是否正反馈": ["✅" if p else "—" for p in positives],
    })


if __name__ == "__main__":
    main()
