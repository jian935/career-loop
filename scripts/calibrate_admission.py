# -*- coding: utf-8 -*-
"""终局录取级校准：真实简历 × 真实 JD 原文 → 预测分 ↔ 真实结果。

与 `run_calibration.py` 的区别：
- run_calibration.py 用的是**早期平台信号**（已读/沟通/面试），没有终局结果；
- 本脚本处理**带 JD 原文 + 终局结果**的记录，因此能回答一个更硬的问题：
  「匹配分能不能预测到最终拿到 offer？」

口径（与 career_loop/calibrate.py 一致）：
- 正反馈 = 拿到 offer（终局口径，比"面试邀约"更严格）
- r = Pearson(预测匹配分, 是否拿到 offer)
- 分桶 = 20 分一档，看每档的 offer 率

诚实边界：
- 数据是**样例/验证数据**（D001–D040 批次用户已确认为样例），本批 D041–D090
  与之同源同格式（时间连续、字段同构），同样按样例处理：
  用来验证「分析流水线能不能跑通」和「引擎在中文真实 JD 上的行为」，
  **不**作为作者真实求职记录对外宣称。
- 匹配分用的是**真实简历**（陈默，中文），JD 是**真实中文 JD 原文**，
  因此这批中文数据的分数分布与之前英文公开集不同，不可跨集比较 r。
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from career_loop import matching
from career_loop.calibrate import calibrate, pearson

DEFAULT_CSV = ROOT / "data" / "calibration" / "final_outcomes_202609.csv"
DEFAULT_PROFILE = ROOT / "data" / "calibration" / "profile.txt"
DEFAULT_OUT = ROOT / "data" / "calibration" / "admission_calibration_report.md"

# 终局结果 → 是否算"正反馈"（终局口径：只有 offer 算）
OFFER_OUTCOMES = {"发放offer"}
# 进了面试但没 offer：中间态，分析时单列
INTERVIEW_OUTCOMES = {"面试环节淘汰"}
# 沉默：结果未知，单列
SILENT_OUTCOMES = {"无反馈沉默"}


def load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def classify(outcome: str) -> str:
    """把终局结果分成 offer / 面试淘汰 / 简历淘汰 / 沉默。"""
    if outcome in OFFER_OUTCOMES:
        return "offer"
    if outcome in INTERVIEW_OUTCOMES:
        return "interview"
    if outcome in SILENT_OUTCOMES:
        return "silent"
    return "rejected"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(DEFAULT_CSV))
    ap.add_argument("--profile", default=str(DEFAULT_PROFILE))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    rows = load_rows(Path(args.csv))
    profile = Path(args.profile).read_text(encoding="utf-8")
    if not profile.strip():
        print("简历为空，无法打分", file=sys.stderr)
        return 1

    # ---- 逐条算预测分 ----
    scored: list[dict] = []
    for r in rows:
        jd = r.get("jd_text") or ""
        if not jd.strip():
            continue
        reqs, _ = matching.extract_requirements(jd, None)
        if not reqs:
            scored.append({**r, "score": None, "n_reqs": 0, "n_custom": 0,
                           "bucket": "无能力项", "cls": classify(r["outcome"])})
            continue
        matches, _ = matching.match(reqs, profile, None)
        score = matching.score(reqs, matches)
        n_custom = sum(1 for x in reqs if x.key.startswith("custom:"))
        scored.append({
            **r,
            "score": score,
            "n_reqs": len(reqs),
            "n_custom": n_custom,
            "bucket": f"{int(score // 20) * 20}-{int(score // 20) * 20 + 20}",
            "cls": classify(r["outcome"]),
        })

    usable = [s for s in scored if s["score"] is not None]
    scores = [float(s["score"]) for s in usable]
    positives = [s["cls"] == "offer" for s in usable]

    # ---- 校准 ----
    report = calibrate(scores, positives)

    # ---- 分组统计 ----
    by_bucket: dict[str, list[dict]] = defaultdict(list)
    for s in usable:
        by_bucket[s["bucket"]].append(s)
    by_cls = Counter(s["cls"] for s in scored)
    by_domain: dict[str, list[dict]] = defaultdict(list)
    for s in usable:
        doms = matching.detect_domains(s["jd_text"]) if hasattr(matching, "detect_domains") else []
        dom = doms[0] if doms else "未识别"
        by_domain[dom].append(s)

    # ---- 输出 ----
    L: list[str] = []
    L.append("# 终局录取级校准报告（真实简历 × 真实中文 JD）\n")
    L.append("> 数据定位：样例/验证数据（D041–D090，与 D001–D040 同源同格式、时间连续）。")
    L.append("> 用途：验证分析流水线在**带 JD 原文 + 终局结果**的数据上能跑通，")
    L.append("> 并观察引擎在**真实中文 JD** 上的行为。**不**作为作者真实求职记录对外宣称。\n")

    L.append("## 1. 结果分布（硬数据）\n")
    total = len(scored)
    L.append(f"- 总记录：**{total}**")
    for k in ("offer", "interview", "rejected", "silent"):
        n = by_cls.get(k, 0)
        L.append(f"  - {k:<10} {n:>3} 条（{n / total * 100:.1f}%）")
    L.append(f"\n- **offer 率：{by_cls.get('offer', 0) / total * 100:.1f}%**")
    L.append(f"- 简历通过率（进面试+offer）：{(by_cls.get('offer', 0) + by_cls.get('interview', 0)) / total * 100:.1f}%")
    L.append(f"- 面试→offer 转化："
             + (f"{by_cls.get('offer', 0) / (by_cls.get('offer', 0) + by_cls.get('interview', 0)) * 100:.1f}%"
                if by_cls.get('offer', 0) + by_cls.get('interview', 0) else "—"))
    L.append("")

    L.append("## 2. 校准：预测匹配分 ↔ 真实 offer\n")
    L.append(f"- 样本量：**{report.n}**（终局口径，只有 offer 算正反馈）")
    L.append(f"- 整体 offer 率：{report.positive_rate}")
    L.append(f"- **Pearson r = {report.correlation}**")
    L.append(f"\n> {report.verdict}\n")

    L.append("### 分桶 offer 率\n")
    L.append("| 匹配分区间 | 记录数 | offer 数 | offer 率 |")
    L.append("| --- | --- | --- | --- |")
    for b in report.buckets:
        if b.n == 0:
            L.append(f"| {b.lo}-{b.hi} | 0 | 0 | — |")
        else:
            L.append(f"| {b.lo}-{b.hi} | {b.n} | {b.positives} | {b.positives / b.n * 100:.1f}% |")
    L.append("")

    L.append("## 3. 逐条明细（按预测分排序）\n")
    L.append("| ID | 公司 | 岗位 | 预测分 | 能力项 | custom | 结果 |")
    L.append("| --- | --- | --- | --- | --- | --- | --- |")
    for s in sorted(usable, key=lambda x: -x["score"]):
        L.append(f"| {s['id']} | {s['company']} | {s['role']} | {s['score']:.1f} | "
                 f"{s['n_reqs']} | {s['n_custom']} | {s['outcome']} |")
    L.append("")

    L.append("## 4. 按岗位族的 offer 分布\n")
    L.append("| 预测族 | 记录数 | offer | offer 率 |")
    L.append("| --- | --- | --- | --- |")
    for dom, items in sorted(by_domain.items(), key=lambda kv: -len(kv[1])):
        off = sum(1 for i in items if i["cls"] == "offer")
        L.append(f"| {dom} | {len(items)} | {off} | {off / len(items) * 100:.1f}% |")
    L.append("")

    # 引擎行为观察
    n_custom_total = sum(s["n_custom"] for s in usable)
    n_reqs_total = sum(s["n_reqs"] for s in usable)
    no_req = sum(1 for s in scored if s["score"] is None)
    L.append("## 5. 引擎在这批中文 JD 上的行为\n")
    L.append(f"- 平均抽出能力项：**{n_reqs_total / max(1, len(usable)):.1f}** 个/JD")
    L.append(f"- custom（词表未覆盖）项占比：**{n_custom_total / max(1, n_reqs_total) * 100:.1f}%**")
    L.append(f"- 抽不出任何能力项的 JD：**{no_req}** 条")
    L.append("")

    out = Path(args.out)
    out.write_text("\n".join(L), encoding="utf-8")

    # ---- 控制台摘要 ----
    print("=" * 56)
    print("终局录取级校准（真实简历 × 真实中文 JD）")
    print("=" * 56)
    print(f"总记录 {total} 条 | 有效打分 {report.n} 条")
    print(f"结果分布：offer {by_cls.get('offer', 0)} / 面试淘汰 {by_cls.get('interview', 0)} "
          f"/ 简历拒绝 {by_cls.get('rejected', 0)} / 沉默 {by_cls.get('silent', 0)}")
    print(f"offer 率 {by_cls.get('offer', 0) / total * 100:.1f}%")
    print()
    print(f"预测分 ↔ 真实 offer：Pearson r = {report.correlation}   (n={report.n})")
    print("分桶 offer 率：")
    for b in report.buckets:
        if b.n:
            print(f"   {b.lo:>3}-{b.hi:<3} n={b.n:<3} offer={b.positives:<3} {b.positives / b.n * 100:5.1f}%")
    print()
    print(f"引擎行为：平均 {n_reqs_total / max(1, len(usable)):.1f} 能力项/JD，"
          f"custom 占 {n_custom_total / max(1, n_reqs_total) * 100:.1f}%，抽不出能力项 {no_req} 条")
    print()
    print(f"报告已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
