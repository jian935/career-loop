# -*- coding: utf-8 -*-
"""个人真实投递校准链路（私有，不入库）。

读取 data/calibration/applications.json（真实投递记录）与 profile.txt（候选人经历），
走完整 career-loop 流水线：add-profile -> add-jd -> apply（自动算预测匹配分）-> log（回填真实状态）
-> calibrate（算匹配分能否预测真实互动）。

重要诚实边界：
- applications.json 与 profile.txt 含个人真实求职信息，已在 .gitignore 排除，绝不提交。
- 预测匹配分需要"每条 JD 文本 × 简历"才能算。本脚本用「岗位族代表性 JD 模板」作为代理输入
  （domain -> 一段典型 JD），不是你投出去的那份真实 JD 原文，也不是你的真实简历全文。
  因此 fit_score 是「代理值」，calibrate 的 r 仅用于验证流水线机制，不能当作真实校准结论。
- 真正有价值、且完全真实的部分是「互动漏斗」：40 条真实投递里，招聘方真有人理你几条、
  集中在哪些岗位族/渠道——这部分不依赖任何预测分，是硬数据。
- 升级为完全真实校准：把 profile.txt 换成你的真实简历全文，并把每条投递配上真实 JD 原文
  （脚本后续可支持 applications.json 里加 jd_text 字段），重跑即得真实 r。

用法：
    python scripts/run_calibration.py
    python scripts/run_calibration.py --db data/calibration/loop.db
"""

from __future__ import annotations

import argparse
import json
import os
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

# 岗位族代表性 JD 模板（代理输入，非真实 JD 原文）。
# 关键词刻意覆盖 career-loop 词表，让预测匹配分在岗位族之间有真实差异：
#   aigc / generative / general_ai 偏产品 sense（简历强项）-> 高分；
#   llm_app 偏 大模型/RAG/工程落地（简历弱项）-> 低分。
DOMAIN_JD = {
    "aigc": (
        "负责AIGC产品规划与需求分析，撰写PRD与产品需求文档。"
        "进行用户研究与竞品分析，用墨刀绘制高保真原型。"
        "理解生成式AI与内容理解逻辑，用数据分析驱动产品迭代。"
        "协调设计与开发团队跨团队协作推动落地。"
    ),
    "generative": (
        "负责生成式AI产品规划，进行用户研究与竞品分析，输出PRD与原型。"
        "理解大模型与多模态生成逻辑，用数据分析优化用户体验，跨团队推动落地。"
    ),
    "general_ai": (
        "负责AI产品经理日常工作：产品规划、需求分析、撰写PRD、项目管理、竞品分析、用户研究。"
        "用数据分析支撑决策，跨团队沟通协调，制作原型验证想法。"
    ),
    "llm_app": (
        "负责大模型应用产品的需求拆解与技术方案评估，设计RAG与向量检索相关功能，"
        "理解Prompt工程与智能体Agent工作流。需具备一定的工程落地能力，与技术团队紧密协作，"
        "用数据分析衡量效果，了解算法的基本原理。"
    ),
}


def map_status(status_text: str) -> str:
    """把平台侧早期状态映射为 career-loop 的正式状态。

    只有招聘方真正有动作（沟通/感兴趣/初筛通过/面试邀约）才算正反馈（replied/interview）。
    仅查看/已读/入库/系统回执/待处理 都只是 'applied'，不算正反馈。
    """
    t = status_text
    if "面试" in t:
        return "interview"
    if any(k in t for k in ("沟通", "感兴趣", "有意向", "初筛通过")):
        return "replied"
    return "applied"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--profile", default=str(PROFILE))
    args = ap.parse_args()

    apps = json.loads(APPS.read_text(encoding="utf-8"))
    profile_text = Path(args.profile).read_text(encoding="utf-8")

    store.init(args.db)
    pid = store.add_profile("我（2028届AI PM）", profile_text, args.db)
    print(f"[init] profile #{pid} 已写入 {args.db}")

    scores, positives, domains, channels = [], [], [], []
    funnel_pos, funnel_by_domain = Counter(), Counter()
    n_pos_total = 0

    for a in apps:
        jd_text = DOMAIN_JD[a["domain"]]
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

    # ---- 校准（代理预测分）----
    print("\n===== 校准：代理预测匹配分 ↔ 真实互动 =====")
    if len(scores) < 5:
        print("样本太少。"); return 1
    rep = calib_mod.calibrate(scores, positives)
    print(f"样本量 {rep.n}　整体正反馈率 {rep.positive_rate}")
    print(f"匹配分 ↔ 真实结果 相关系数 r = {rep.correlation}  （代理值，见脚本顶部说明）")
    print("分桶正反馈率：")
    for b in rep.buckets:
        bar = "#" * int(b.positive_rate * 30)
        print(f"  {b.lo:>3}-{b.hi:<3}  n={b.n:<3}  率={b.positive_rate:<5} {bar}")
    print(f"\n结论：{rep.verdict}")

    out = DATA_DIR / "calibration_report.md"
    out.write_text(
        "# 个人投递校准报告（代理版）\n\n"
        f"- 数据日期：2026-10-25，样本 {len(apps)} 条真实投递\n"
        f"- 正反馈率（真实）：{n_pos_total}/{len(apps)} = {n_pos_total/len(apps):.1%}\n"
        f"- 代理校准 r = {rep.correlation}（预测分用岗位族代表性 JD，非真实 JD 原文）\n\n"
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
