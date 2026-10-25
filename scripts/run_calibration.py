# -*- coding: utf-8 -*-
"""个人真实投递校准链路（私有，不入库）。

读取 data/calibration/applications.json（40 条真实投递：含英文 JD 原文 jd_text_en +
忠实中文翻译 jd_text、真实状态 status_text、岗位族 domain）与 profile.txt（真实简历），
走完整 career-loop 流水线：add-profile -> add-jd -> apply（自动算预测匹配分）-> log（回填真实状态）
-> calibrate（算匹配分能否预测真实互动）。

核心逻辑已抽到 `career_loop/reflow.py`（与 CLI `career-loop reflow --mode early` 同一套代码），
本脚本保留是因为它额外做了两件事：把记录写进 SQLite、打印逐条明细。

数据真实性：
- 预测匹配分用【真实简历 × 真实 JD 中文版】计算，不是代理。
- JD 英文原文由用户提供；因 career-loop 词表是中文、英文 JD 直接抽需求会退化（只抽 3-4 项、全 100%），
  故把英文 JD 忠实翻译成中文（同一内容，仅换引擎母语）以便正确抽取能力项。英文原文保留在 jd_text_en 供审计。
- 真实状态 status_text 由用户逐条提供；映射规则见 career_loop.reflow.normalize_early_status。
- 唯一剩余局限：这 40 条都是「已投递当天」的早期平台状态，是招聘方是否理你的早期信号，不是终局 offer/拒信。
  所以校准回答的是「匹配分能否预测早期互动」，而非「能否预测最终录取」。

个人数据（applications.json / profile.txt / loop.db / calibration_report.md）已在 .gitignore 排除，绝不提交。

用法：
    python scripts/run_calibration.py
    python scripts/run_calibration.py --db data/calibration/loop.db
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from career_loop import matching  # noqa: E402
from career_loop import reflow as rf  # noqa: E402
from career_loop import store  # noqa: E402

DATA_DIR = ROOT / "data" / "calibration"
APPS = DATA_DIR / "applications.json"
PROFILE = DATA_DIR / "profile.txt"
DEFAULT_DB = DATA_DIR / "loop.db"


def _reset(db: str) -> None:
    """清空三张表，保证重跑幂等（个人校准每次都应从干净状态算）。"""
    conn = sqlite3.connect(db)
    conn.executescript(
        "DELETE FROM applications; DELETE FROM jds; DELETE FROM profiles;"
    )
    conn.commit()
    conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--profile", default=str(PROFILE))
    args = ap.parse_args()

    apps = json.loads(APPS.read_text(encoding="utf-8"))
    profile_text = Path(args.profile).read_text(encoding="utf-8")

    _reset(args.db)
    store.init(args.db)
    pid = store.add_profile("陈默（真实简历）", profile_text, args.db)
    print(f"[init] profile #{pid} 已写入 {args.db}")

    # 统一走 reflow：同一套状态映射与打分口径
    records = [
        {
            "id": a.get("idx", ""),
            "company": a.get("company", ""),
            "role": a.get("role", ""),
            "jd_text": a.get("jd_text", ""),
            "outcome_text": a.get("status_text", ""),
            "note": a.get("status_text", ""),
            "domain": a.get("domain", ""),
            "date": a.get("date", ""),
        }
        for a in apps
    ]
    res = rf.analyze_reflow(records, profile_text, "early", None)

    # ---- 写 SQLite（apply → log 的等价批量版）----
    for s in res.scored:
        jid = store.add_jd(s.role, s.record.get("jd_text", ""), [], args.db)
        reqs, _ = matching.extract_requirements(s.record.get("jd_text", ""), None)
        aid = store.record_application(jid, pid, s.score or 0.0, args.db)
        store.set_status(aid, s.status, s.record.get("status_text", ""), args.db)
        print(f"  fit={s.score:>5}%  -> {s.status:<9} ({s.record.get('status_text', '')})")

    # ---- 真实互动漏斗（不依赖任何预测分）----
    domains = [s.record.get("domain", "") for s in res.scored]
    channels = [a.get("channel", "") for a in apps]
    funnel_by_domain: Counter = Counter()
    for s in res.scored:
        if s.positive:
            funnel_by_domain[s.record.get("domain", "")] += 1

    print("\n===== 真实互动漏斗（硬数据，不依赖预测匹配分）=====")
    print(f"总投递：{len(apps)}")
    print(f"正反馈（HR沟通/感兴趣/初筛通过/面试邀约）：{res.n_positive}  "
          f"({res.positive_rate:.1%})")
    print("按岗位族的正反馈：")
    for d, c in funnel_by_domain.most_common():
        tot = sum(1 for x in domains if x == d)
        print(f"  {d:<12} {c}/{tot}  ({c / tot:.1%})")
    print("按渠道：")
    for ch, c in Counter(channels).most_common():
        print(f"  {ch:<10} n={c}")

    # ---- 校准（真实预测分 × 真实互动）----
    print("\n===== 校准：真实匹配分 ↔ 真实互动 =====")
    if res.report is None:
        print("样本太少。")
        return 1
    print(rf.render_console_summary(res))

    out = DATA_DIR / "calibration_report.md"
    out.write_text(
        rf.render_report(
            res,
            title="个人投递校准报告（真实简历 × 真实 JD）",
            data_note=(
                f"数据日期：2026-10-25，样本 {len(apps)} 条真实投递。"
                "局限：早期互动信号，非终局 offer/拒信。"
            ),
        ),
        encoding="utf-8",
    )
    print(f"\n报告已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
