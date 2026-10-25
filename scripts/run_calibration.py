# -*- coding: utf-8 -*-
"""个人真实投递校准链路（私有，不入库）。

读取 data/calibration/applications.json（40 条真实投递：含英文 JD 原文 jd_text_en +
忠实中文翻译 jd_text、真实状态 status_text、岗位族 domain）与 profile.txt（陈默真实简历），
走完整 career-loop 流水线：add-profile -> add-jd -> apply（自动算预测匹配分）-> log（回填真实状态）
-> calibrate（算匹配分能否预测真实互动）。

数据真实性：
- 预测匹配分现在用【真实简历 × 真实 JD 中文版】计算，不是代理。
- JD 英文原文由用户提供；因 career-loop 词表是中文、英文 JD 直接抽需求会退化（只抽 3-4 项、全 100%），
  故把英文 JD 忠实翻译成中文（同一内容，仅换引擎母语）以便正确抽取能力项。英文原文保留在 jd_text_en 供审计。
- 真实状态 status_text 由用户逐条提供；映射规则见 map_status()。
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
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from career_loop import calibrate as calib_mod  # noqa: E402
from career_loop import matching  # noqa: E402
from career_loop import store  # noqa: E402

DATA_DIR = ROOT / "data" / "calibration"
APPS = DATA_DIR / "applications.json"
PROFILE = DATA_DIR / "profile.txt"
DEFAULT_DB = DATA_DIR / "loop.db"


def map_status(status_text: str) -> str:
    """把平台侧早期状态映射为 career-loop 的正式状态。

    只有招聘方真正有动作（沟通/感兴趣/有意向/初筛通过/面试邀约）才算正反馈（replied/interview）。
    仅查看/已读/入库/系统回执/待处理 都只是 'applied'，不算正反馈。
    """
    t = status_text
    if "面试" in t:
        return "interview"
    if any(k in t for k in ("沟通", "感兴趣", "有意向", "初筛通过")):
        return "replied"
    return "applied"


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

    scores, positives, domains, channels = [], [], [], []
    funnel_pos, funnel_by_domain = Counter(), Counter()
    n_pos_total = 0

    for a in apps:
        jd_text = a["jd_text"]  # 真实 JD 中文版
        jid = store.add_jd(a["role"], jd_text, [], args.db)
        reqs, _ = matching.extract_requirements(jd_text, None)
        matches, _ = matching.match(reqs, profile_text, None)
        fit = matching.score(reqs, matches)
        aid = store.record_application(jid, pid, fit, args.db)
        status = map_status(a["status_text"])
        store.set_status(aid, status, a["status_text"], args.db)

        scores.append(fit)
        positive = status in store.POSITIVE_STATUSES
        positives.append(positive)
        domains.append(a["domain"])
        channels.append(a["channel"])
        if positive:
            n_pos_total += 1
            funnel_by_domain[a["domain"]] += 1
        print(f"  #{aid:>2} {a['role'][:22]:<22} fit={fit:>5}%  -> {status:<9} ({a['status_text']})")

    # ---- 真实互动漏斗（不依赖任何预测分）----
    print("\n===== 真实互动漏斗（硬数据，不依赖预测匹配分）=====")
    print(f"总投递：{len(apps)}")
    print(f"正反馈（HR沟通/感兴趣/初筛通过/面试邀约）：{n_pos_total}  "
          f"({n_pos_total / len(apps):.1%})")
    print("按岗位族的正反馈：")
    for d, c in funnel_by_domain.most_common():
        tot = sum(1 for x in domains if x == d)
        print(f"  {d:<12} {c}/{tot}  ({c / tot:.1%})")
    print("按渠道：")
    for ch, c in Counter(channels).most_common():
        print(f"  {ch:<10} n={c}")

    # ---- 校准（真实预测分 × 真实互动）----
    print("\n===== 校准：真实匹配分 ↔ 真实互动 =====")
    if len(scores) < 5:
        print("样本太少。"); return 1
    rep = calib_mod.calibrate(scores, positives)
    print(f"样本量 {rep.n}　整体正反馈率 {rep.positive_rate}")
    print(f"匹配分 ↔ 真实结果 相关系数 r = {rep.correlation}  （真实简历 × 真实 JD）")
    print("分桶正反馈率：")
    for b in rep.buckets:
        bar = "#" * int(b.positive_rate * 30)
        print(f"  {b.lo:>3}-{b.hi:<3}  n={b.n:<3}  率={b.positive_rate:<5} {bar}")
    print(f"\n结论：{rep.verdict}")

    out = DATA_DIR / "calibration_report.md"
    out.write_text(
        "# 个人投递校准报告（真实简历 × 真实 JD）\n\n"
        f"- 数据日期：2026-10-25，样本 {len(apps)} 条真实投递\n"
        f"- 正反馈率（真实）：{n_pos_total}/{len(apps)} = {n_pos_total/len(apps):.1%}\n"
        f"- 校准 r = {rep.correlation}（预测分=真实简历×真实JD中文版；JD英文原文保留在 applications.json 供审计）\n"
        f"- 局限：早期互动信号，非终局 offer/拒信\n\n"
        "## 互动漏斗（真实）\n"
        + "\n".join(f"- {d}: {c}/{sum(1 for x in domains if x==d)}" for d, c in funnel_by_domain.most_common())
        + "\n\n## 分桶\n"
        + "\n".join(f"- {b.lo}-{b.hi}: n={b.n} 率={b.positive_rate}" for b in rep.buckets)
        + "\n",
        encoding="utf-8",
    )
    print(f"\n报告已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
