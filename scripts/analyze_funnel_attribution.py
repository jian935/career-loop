# -*- coding: utf-8 -*-
"""终局漏斗归因与方向性分析（兼容入口）。

与 `calibrate_admission.py` 的分工：
- calibrate_admission.py 回答「匹配分能不能预测录取」（r 与分桶）；
- 本脚本回答「结果卡在哪、哪些是可控的、往哪个方向投」（漏斗归因 + 方向对比）。

归因关键词表与方向分类已抽到 `career_loop/reflow.py`（与 CLI `career-loop reflow`
同一套代码），本脚本只负责报告版式——**避免两处口径漂移**。

数据定位：与 D001–D040 同源同格式（时间连续、字段同构），
按**样例/验证数据**处理——用来验证分析流程与观察引擎行为，
不作为作者真实求职记录对外宣称。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from career_loop import reflow as rf  # noqa: E402

DEFAULT_CSV = ROOT / "data" / "calibration" / "final_outcomes_202609.csv"
DEFAULT_OUT = ROOT / "data" / "calibration" / "funnel_attribution_report.md"

DATA_NOTE = (
    "样例/验证数据（与 D001–D040 同源同格式、时间连续）。"
    "用途：验证分析流程可跑通，并观察引擎在真实中文 JD 上的行为。"
    "**不**作为作者真实求职记录对外宣称。"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(DEFAULT_CSV))
    ap.add_argument("--profile", default=str(ROOT / "data" / "calibration" / "profile.txt"))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"记录文件不存在：{csv_path}", file=sys.stderr)
        return 1
    records = rf.load_records(csv_path)
    if not records:
        print(f"没读到任何记录：{csv_path}", file=sys.stderr)
        return 1

    profile = Path(args.profile)
    profile_text = profile.read_text(encoding="utf-8") if profile.exists() else ""
    res = rf.analyze_reflow(records, profile_text, "terminal", None)

    # ---- 控制台摘要（与旧版同口径）----
    sc = res.status_counts
    total = res.total
    offer = sc.get(rf.STATUS_OFFER, 0)
    interview = sc.get(rf.STATUS_INTERVIEW_ELIMINATED, 0)
    rejected = sc.get(rf.STATUS_REJECTED, 0)
    silent = sc.get(rf.STATUS_SILENT, 0)

    print("=" * 56)
    print("终局漏斗归因（D041–D090）")
    print("=" * 56)
    print(f"总投递 {total} | offer {offer} | 面试淘汰 {interview} | 简历关 {rejected} | 沉默 {silent}")
    if total:
        print(f"简历通过率 {(offer + interview) / total * 100:.1f}% | "
              f"面试→offer {offer / (offer + interview) * 100:.1f}%" if offer + interview
              else f"简历通过率 {(offer + interview) / total * 100:.1f}% | 面试→offer —")
    print()
    print("简历关归因：")
    for k, v in res.attr_counts.most_common():
        print(f"   {k:<28} {v:>2} 条 ({v / rejected * 100:.0f}%)" if rejected
              else f"   {k:<28} {v:>2} 条")
    print()
    print("方向对比：")
    for d, (n, p) in sorted(res.direction_stats.items(), key=lambda kv: (-kv[1][0], kv[0])):
        print(f"   {d:<14} 投{n:>2} 正反馈{p:>2}  {p / n * 100:5.1f}%")

    out = Path(args.out)
    out.write_text(
        rf.render_report(
            res,
            title="终局漏斗归因与方向性分析（D041–D090）",
            data_note=DATA_NOTE,
        ),
        encoding="utf-8",
    )
    print()
    print(f"报告已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
