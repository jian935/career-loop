# -*- coding: utf-8 -*-
"""D041–D090 批次的漏斗归因与方向性分析（终局结果）。

与 `calibrate_admission.py` 的分工：
- calibrate_admission.py 回答「匹配分能不能预测录取」（r 与分桶）；
- 本脚本回答「结果卡在哪、哪些是可控的、往哪个方向投」（漏斗归因 + 方向对比）。

数据定位：与 D001–D040 同源同格式（时间连续、字段同构），
按**样例/验证数据**处理——用来验证分析流程与观察引擎行为，
不作为作者真实求职记录对外宣称。
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_CSV = ROOT / "data" / "calibration" / "final_outcomes_202609.csv"
DEFAULT_OUT = ROOT / "data" / "calibration" / "funnel_attribution_report.md"

# 简历关：外部/资格线因素（候选人难控）
EXTERNAL = (
    "hc", "冻结", "缩减", "收缩", "招满", "关闭", "取消", "名额", "学历", "本科", "硕士",
    "院校", "批次", "地点", "城市", "出差", "薪资", "优先已有", "竞争", "优先有",
    "已满", "暂停", "补招", "不接受", "现场经验", "行情相关", "合规项目",
)
# 简历关：可通过改简历/补项目挽回
CONTROLLABLE = (
    "缺少", "没有", "经验较少", "项目经历较少", "偏向学术", "学生demo",
    "笔试", "得分偏低", "未达到及格线",
)
# 面试淘汰：都是当场表现暴露的短板
INTERVIEW_GAP = (
    "偏保守", "创新性不足", "耗时过长", "结果出错", "理解不够深入", "偏差较大",
    "熟练度不足", "不扎实", "理解片面", "存在漏洞", "不够清晰", "不完善",
    "有偏差", "错误较多", "效率不达标", "同质化", "经验不足", "掌握薄弱",
)

# 岗位方向 → 关键词（按先到先得匹配，一个岗位只归一个方向）
DIRECTIONS = [
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


def classify_direction(role: str) -> str:
    low = role.lower()
    for name, kws in DIRECTIONS:
        if any(k in low for k in kws):
            return name
    return "其他"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(DEFAULT_CSV))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    with Path(args.csv).open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))

    total = len(rows)
    by_outcome = Counter(r["outcome"] for r in rows)
    offer = by_outcome.get("发放offer", 0)
    interview = by_outcome.get("面试环节淘汰", 0)
    rejected = by_outcome.get("简历筛选拒绝", 0)
    silent = by_outcome.get("无反馈沉默", 0)

    # ---- 简历关归因 ----
    attr = Counter()
    attr_detail: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for r in rows:
        if r["outcome"] != "简历筛选拒绝":
            continue
        note = r["note"]
        if any(k in note.lower() for k in EXTERNAL):
            kind = "不可控（HC/学历/地点/资格线）"
        elif any(k in note for k in CONTROLLABLE):
            kind = "可控（改简历/补项目可挽回）"
        else:
            kind = "其他"
        attr[kind] += 1
        attr_detail[kind].append((r["id"], r["company"], r["role"], note))

    # ---- 方向对比 ----
    dir_stat: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])  # 投递, offer, 面试淘汰
    for r in rows:
        d = classify_direction(r["role"])
        dir_stat[d][0] += 1
        if r["outcome"] == "发放offer":
            dir_stat[d][1] += 1
        elif r["outcome"] == "面试环节淘汰":
            dir_stat[d][2] += 1

    # ---- 报告 ----
    L: list[str] = []
    L.append("# 终局漏斗归因与方向性分析（D041–D090）\n")
    L.append("> 数据定位：样例/验证数据（与 D001–D040 同源同格式、时间连续）。")
    L.append("> 用途：验证分析流程可跑通，并观察引擎在真实中文 JD 上的行为。")
    L.append("> **不**作为作者真实求职记录对外宣称。\n")

    L.append("## 1. 终局漏斗\n")
    L.append(f"- 总投递 **{total}** 条")
    L.append(f"  - **拿到 offer：{offer}**（{offer / total * 100:.1f}%）")
    L.append(f"  - 进面试但淘汰：{interview}（{interview / total * 100:.1f}%）")
    L.append(f"  - 简历关：{rejected}（{rejected / total * 100:.1f}%）")
    L.append(f"  - 沉默（结果未知）：{silent}（{silent / total * 100:.1f}%）")
    L.append(f"\n- 简历通过率（进面试+offer）：**{(offer + interview) / total * 100:.1f}%**")
    L.append(f"- 面试→offer 转化：**{offer / (offer + interview) * 100:.1f}%**")
    L.append(f"- 沉默率：{silent / total * 100:.1f}%（这 {silent} 条结果不明，不计入成败统计）\n")

    L.append("## 2. 简历关归因：多少是「你的问题」\n")
    L.append("| 归因 | 条数 | 占简历关 |")
    L.append("| --- | --- | --- |")
    for k, v in attr.most_common():
        L.append(f"| {k} | {v} | {v / rejected * 100:.0f}% |")
    L.append("")
    ext = attr.get("不可控（HC/学历/地点/资格线）", 0)
    ctl = attr.get("可控（改简历/补项目可挽回）", 0)
    L.append(f"**结论：简历关 {rejected} 条里，{ext} 条（{ext / rejected * 100:.0f}%）是外部/资格线因素**"
             f"（HC 冻结、岗位招满、学历门槛、地点冲突、名额已满），"
             f"跟简历写得好不好没关系；真正能靠改简历/补项目挽回的只有 {ctl} 条（{ctl / rejected * 100:.0f}%）。\n")

    for kind in ("不可控（HC/学历/地点/资格线）", "可控（改简历/补项目可挽回）", "其他"):
        items = attr_detail.get(kind)
        if not items:
            continue
        L.append(f"### {kind}（{len(items)} 条）\n")
        L.append("| ID | 公司 | 岗位 | 回流备注 |")
        L.append("| --- | --- | --- | --- |")
        for i, c, role, note in items:
            L.append(f"| {i} | {c} | {role} | {note} |")
        L.append("")

    L.append("## 3. 面试淘汰（16 条）：短板在当场暴露\n")
    L.append("这些不是简历问题，是面试当场暴露的短板。逐条看：\n")
    L.append("| ID | 公司 | 岗位 | 暴露的短板 |")
    L.append("| --- | --- | --- | --- |")
    for r in rows:
        if r["outcome"] != "面试环节淘汰":
            continue
        L.append(f"| {r['id']} | {r['company']} | {r['role']} | {r['note']} |")
    L.append("")

    L.append("## 4. 方向对比：投哪个方向回报高\n")
    L.append("| 方向 | 投递 | 进面试 | 拿到 offer | offer 率 | 样本可信度 |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    for d, (n, o, it) in sorted(dir_stat.items(), key=lambda kv: (-kv[1][0], kv[0])):
        # 样本量警告：每格样本 <5 的 offer 率不可当结论
        if n >= 5:
            trust = "可用"
        elif n >= 3:
            trust = "偏弱（n<5）"
        else:
            trust = "**仅供参考**（n<3）"
        L.append(f"| {d} | {n} | {it} | {o} | {o / n * 100:.1f}% | {trust} |")
    L.append("")
    L.append("> ⚠️ 只有「投递 ≥ 5 条」的方向才谈得上方向性参考。"
             "n<3 的行（offer 率 100% 之类）纯属巧合，别当结论。\n")

    L.append("## 5. 可执行结论\n")
    L.append("1. **别把拒绝全归因于自己。** 简历关里 "
             f"{ext / rejected * 100:.0f}% 是 HC/学历/地点等外部因素，"
             "这些投再多也救不回来，别用它们否定自己。")
    reliable = [(d, v) for d, v in dir_stat.items() if v[0] >= 5]
    if reliable:
        best = max(reliable, key=lambda kv: kv[1][1] / kv[1][0])
        worst = min(reliable, key=lambda kv: kv[1][1] / kv[1][0])
        L.append(f"2. **在样本够用的方向里（投递 ≥ 5 条）**，offer 率最高的是「{best[0]}」"
                 f"（{best[1][1]}/{best[1][0]} = {best[1][1] / best[1][0] * 100:.0f}%），"
                 f"最低的是「{worst[0]}」（{worst[1][1]}/{worst[1][0]}）。"
                 "样本仍然偏小，只作方向性参考，但值得优先投入。")
    L.append("3. **面试才是真正的分水岭**：简历通过后面试→offer 转化有 "
             f"{offer / (offer + interview) * 100:.1f}%，"
             "说明进了面试就有约三成机会；短板集中在"
             "「原理答不上」「案例拆解偏保守」「工程深度不够」三类，"
             "这些靠面试前针对性准备能改。")
    L.append(f"4. **沉默 {silent} 条要单独追**：内推/猎头/公众号投递拿不到状态，"
             "这类渠道应该主动要反馈，否则无法判断是沉没还是被拒——"
             "它们既不算成功也不算失败，但正在浪费投递额度。")
    L.append("")

    L.append("## 6. 边界（必须说清）\n")
    L.append("- 样本 50 条，方向维度的每格样本只有 1–8 条，**只能作方向性参考，不能当统计结论**。")
    L.append("- 归因靠回流备注的关键词分类，是**启发式**；备注本身是事后描述，可能有偏差。")
    L.append("- 匹配分与 offer 的相关系数 r ≈ 0，意思是**当前匹配分不能预测录取**——"
             "这批数据里 offer 率只有 14%，且不可控因素占比高，匹配分再准也改变不了 HC 和学历门槛。")
    L.append("- 这批是**样例/验证数据**；换成真实回流数据后，脚本可直接复用，结论需重算。\n")

    out = Path(args.out)
    out.write_text("\n".join(L), encoding="utf-8")

    print("=" * 56)
    print("终局漏斗归因（D041–D090）")
    print("=" * 56)
    print(f"总投递 {total} | offer {offer} | 面试淘汰 {interview} | 简历关 {rejected} | 沉默 {silent}")
    print(f"简历通过率 {(offer + interview) / total * 100:.1f}% | 面试→offer {offer / (offer + interview) * 100:.1f}%")
    print()
    print("简历关归因：")
    for k, v in attr.most_common():
        print(f"   {k:<28} {v:>2} 条 ({v / rejected * 100:.0f}%)")
    print()
    print("方向对比：")
    for d, (n, o, it) in sorted(dir_stat.items(), key=lambda kv: (-kv[1][0], kv[0])):
        print(f"   {d:<14} 投{n:>2} 面试{it:>2} offer{o:>2}  {o / n * 100:5.1f}%")
    print()
    print(f"报告已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
