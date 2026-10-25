# -*- coding: utf-8 -*-
"""终局录取级校准（兼容入口）：真实简历 × 真实 JD 原文 → 预测分 ↔ 真实 offer。

核心逻辑已抽到 `career_loop/reflow.py`（与 CLI `career-loop reflow` 同一套代码），
本脚本保留是为了兼容旧用法，也给完整报告（漏斗归因 + 方向对比 + 逐条明细）一个入口。

口径（与 career_loop/calibrate.py 一致）：
- 正反馈 = 拿到 offer（终局口径，比"面试邀约"更严格）
- r = Pearson(预测匹配分, 是否拿到 offer)
- 分桶 = 20 分一档，看每档的 offer 率

诚实边界：
- 数据是**样例/验证数据**（D001–D040 批次用户已确认为样例），本批 D041–D090
  与之同源同格式（时间连续、字段同构），同样按样例处理：
  用来验证「分析流水线能不能跑通」和「引擎在中文真实 JD 上的行为」，
  **不**作为作者真实求职记录对外宣称。
- 匹配分用的是**真实简历**（中文），JD 是**真实中文 JD 原文**，
  因此这批中文数据的分数分布与之前英文公开集不同，不可跨集比较 r。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from career_loop import reflow as rf  # noqa: E402

DEFAULT_CSV = ROOT / "data" / "calibration" / "final_outcomes_202609.csv"
DEFAULT_PROFILE = ROOT / "data" / "calibration" / "profile.txt"
DEFAULT_OUT = ROOT / "data" / "calibration" / "admission_calibration_report.md"

DATA_NOTE = (
    "样例/验证数据（D041–D090，与 D001–D040 同源同格式、时间连续）。"
    "用途：验证分析流水线在**带 JD 原文 + 终局结果**的数据上能跑通，"
    "并观察引擎在**真实中文 JD** 上的行为。**不**作为作者真实求职记录对外宣称。"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(DEFAULT_CSV))
    ap.add_argument("--profile", default=str(DEFAULT_PROFILE))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"记录文件不存在：{csv_path}", file=sys.stderr)
        return 1
    profile = Path(args.profile).read_text(encoding="utf-8")
    if not profile.strip():
        print("简历为空，无法打分", file=sys.stderr)
        return 1

    records = rf.load_records(csv_path)
    if not records:
        print(f"没读到任何记录：{csv_path}", file=sys.stderr)
        return 1

    res = rf.analyze_reflow(records, profile, "terminal", None)

    out = Path(args.out)
    out.write_text(
        rf.render_report(
            res,
            title="终局录取级校准报告（真实简历 × 真实中文 JD）",
            data_note=DATA_NOTE,
        ),
        encoding="utf-8",
    )

    print(rf.render_console_summary(res))
    print()
    print(f"报告已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
