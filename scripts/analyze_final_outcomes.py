# -*- coding: utf-8 -*-
"""终局结果漏斗分析（私有，不入库）。

读取 data/calibration/final_outcomes_202608.csv（投递 ID / 公司 / 岗位 / 投递时间 /
终局结果 / 回流时间 / 回流备注），做**不依赖任何预测匹配分**的硬数据分析：
  - 终局结果分布（offer / 面试淘汰 / 简历淘汰 / 沉默）
  - 投递→简历通过→面试→offer 漏斗
  - 简历淘汰的「可控 vs 外部/资格」拆解（从回流备注关键词判定）
  - offer 明细（薪资 / base / 福利）

为什么没有 r（相关系数）：这批数据只给了终局结果，没有附每条对应的简历与 JD，
所以无法像 scripts/run_calibration.py 那样算出「预测匹配分」来和结果做相关。
本脚本只回答「结果分布与漏斗」这一层硬数据。

个人数据 data/calibration/ 已在 .gitignore 排除，绝不提交。

用法：
    python scripts/analyze_final_outcomes.py
    python scripts/analyze_final_outcomes.py --csv data/calibration/final_outcomes_202608.csv
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_CSV = ROOT / "data" / "calibration" / "final_outcomes_202608.csv"

OFFER = "发放 offer"
INTERVIEW_OUT = "面试环节淘汰"
RESUME_OUT = "简历筛选拒绝"
SILENT = "无反馈沉默"

# 回流备注里判定「简历淘汰属外部/资格因素（候选人难控）」的关键词
EXTERNAL_KW = ("HC", "冻结", "招满", "关闭", "招聘计划", "批次", "院校",
               "学历", "本地", "地点", "资深", "饱和", "竞争", "证书", "资质")


def tag_resume_reject(note: str) -> str:
    """简历淘汰拆成 外部/资格（难控） vs 匹配（可改简历挽回）。"""
    if any(k in note for k in EXTERNAL_KW):
        return "外部/资格线（难控）"
    return "简历匹配（可改简历挽回）"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(DEFAULT_CSV))
    args = ap.parse_args()

    rows = list(csv.DictReader(Path(args.csv).read_text(encoding="utf-8-sig").splitlines()))
    n = len(rows)

    # ---- 结果分布 ----
    dist = Counter(r["outcome"] for r in rows)
    offers = [r for r in rows if r["outcome"] == OFFER]
    iv_out = [r for r in rows if r["outcome"] == INTERVIEW_OUT]
    rs_out = [r for r in rows if r["outcome"] == RESUME_OUT]
    silent = [r for r in rows if r["outcome"] == SILENT]

    # ---- 漏斗 ----
    passed_resume = len(offers) + len(iv_out)          # 进了面试或拿 offer
    got_interview = len(iv_out) + len(offers)          # 同上口径
    interview_to_offer = len(offers) / got_interview if got_interview else 0

    # ---- 简历淘汰拆解 ----
    rs_external = [r for r in rs_out if tag_resume_reject(r["note"]) != "简历匹配（可改简历挽回）"]
    rs_fit = [r for r in rs_out if tag_resume_reject(r["note"]) == "简历匹配（可改简历挽回）"]

    print("=" * 60)
    print(f"终局结果漏斗分析（样本 {n} 条，投递区间 "
          f"{rows[0]['apply_date']} ~ {rows[-1]['apply_date']}）")
    print("=" * 60)

    print("\n【1. 终局结果分布】")
    for k, v in dist.most_common():
        print(f"  {k:<10} {v:>2}  ({v / n:.1%})")

    print("\n【2. 漏斗】")
    print(f"  投递总数            : {n}")
    print(f"  简历通过（进面试）  : {passed_resume}  ({passed_resume / n:.1%})")
    print(f"  简历淘汰            : {len(rs_out)}  ({len(rs_out) / n:.1%})")
    print(f"  沉默（无反馈）      : {len(silent)}  ({len(silent) / n:.1%})")
    print(f"  进入面试            : {got_interview}  ({got_interview / n:.1%})")
    print(f"  面试→offer 转化     : {len(offers)}/{got_interview}  ({interview_to_offer:.1%})")
    print(f"  整体 offer 率       : {len(offers)}/{n}  ({len(offers) / n:.1%})")

    print("\n【3. 简历淘汰拆解（{}/{}）】".format(len(rs_out), len(rs_out)))
    print(f"  外部/资格线（难控） : {len(rs_external)}  ({len(rs_external) / len(rs_out):.1%} of 简历淘汰)")
    for r in rs_external:
        print(f"    · {r['id']} {r['company']}/{r['role']} —— {r['note']}")
    print(f"  简历匹配（可改简历）: {len(rs_fit)}  ({len(rs_fit) / len(rs_out):.1%} of 简历淘汰)")
    for r in rs_fit:
        print(f"    · {r['id']} {r['company']}/{r['role']} —— {r['note']}")

    print("\n【4. 面试淘汰（{}，均属表现/匹配在面试暴露）】".format(len(iv_out)))
    for r in iv_out:
        print(f"    · {r['id']} {r['company']}/{r['role']} —— {r['note']}")

    print("\n【5. offer 明细（{}）】".format(len(offers)))
    for r in offers:
        print(f"    · {r['id']} {r['company']}/{r['role']} —— {r['note']}")

    print("\n【6. 沉默明细（{}，无法判断是否真淘汰）】".format(len(silent)))
    for r in silent:
        print(f"    · {r['id']} {r['company']}/{r['role']} —— {r['note']}")

    # ---- 写出报告 ----
    out = ROOT / "data" / "calibration" / "final_outcomes_report.md"
    lines = []
    lines.append("# 终局结果漏斗分析（D001–D040，2026-08 投递）\n")
    lines.append(f"- 样本：{n} 条真实终局结果，投递区间 {rows[0]['apply_date']} ~ {rows[-1]['apply_date']}")
    lines.append("- 说明：本批**未附简历/JD**，无法算「预测匹配分」，故只做结果漏斗（硬数据），非预测校准 r。\n")
    lines.append("## 1. 终局结果分布\n")
    for k, v in dist.most_common():
        lines.append(f"- {k}：{v}（{v / n:.1%}）")
    lines.append("\n## 2. 漏斗\n")
    lines.append(f"- 投递总数：{n}")
    lines.append(f"- 简历通过（进面试）：{passed_resume}（{passed_resume / n:.1%}）")
    lines.append(f"- 简历淘汰：{len(rs_out)}（{len(rs_out) / n:.1%}）")
    lines.append(f"- 沉默（无反馈）：{len(silent)}（{len(silent) / n:.1%}）")
    lines.append(f"- 进入面试：{got_interview}（{got_interview / n:.1%}）")
    lines.append(f"- 面试→offer 转化：{len(offers)}/{got_interview}（{interview_to_offer:.1%}）")
    lines.append(f"- 整体 offer 率：{len(offers)}/{n}（{len(offers) / n:.1%}）")
    lines.append("\n## 3. 简历淘汰拆解（关键：分清可控/不可控）\n")
    lines.append(f"- 外部/资格线（难控，如 HC 冻结/招满/院校批次/地点/资深）：{len(rs_external)}（{len(rs_external) / len(rs_out):.1%} of 简历淘汰）")
    for r in rs_external:
        lines.append(f"  - {r['id']} {r['company']}/{r['role']}：{r['note']}")
    lines.append(f"- 简历匹配（可改简历挽回，如项目/经验/关键词对齐）：{len(rs_fit)}（{len(rs_fit) / len(rs_out):.1%} of 简历淘汰）")
    for r in rs_fit:
        lines.append(f"  - {r['id']} {r['company']}/{r['role']}：{r['note']}")
    lines.append("\n## 4. offer 明细\n")
    for r in offers:
        lines.append(f"- {r['id']} {r['company']}/{r['role']}：{r['note']}")
    lines.append("\n## 5. 沉默明细（无法判断是否真淘汰，建议复盘时单独标记）\n")
    for r in silent:
        lines.append(f"- {r['id']} {r['company']}/{r['role']}：{r['note']}")
    lines.append("\n## 诚实边界\n")
    lines.append("- 本批与 10 月那 40 条 AI PM 早期信号**不是同一批**（岗位族、时间、结果口径都不同），不做合并对比。")
    lines.append("- 本批只给终局结果、未给简历/JD，因此**无法做「预测分↔录取」的 r 校准**；只能看结果漏斗。")
    lines.append("- 若想对这批做录取级 r 校准，需补每条对应的简历 + JD 原文（英文需翻译），再接入 run_calibration.py 的同款流水线。")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n报告已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
