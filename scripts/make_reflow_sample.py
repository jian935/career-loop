# -*- coding: utf-8 -*-
"""生成脱敏版真实回流报告样例（可公开放进仓库）。

用 `data/calibration/` 里的真实回流记录跑一遍 `reflow`，然后把结果脱敏，
输出到 `docs/reflow_sample.md`——让评委看到「真实数据跑出来的报告长什么样」，
而不泄露任何可定位到具体投递的信息。

脱敏规则（逐条可审计）：
1. **公司名 → 稳定代号**（按首次出现顺序映射成「甲方 A / 甲方 B」…）
   理由：公司名 + 岗位名 + 结果三者组合起来可以反查具体投递。
2. **回流备注 → 归因标签**（如「不可控：HC 冻结」「可控：缺少项目经验」）
   理由：备注原文含"某公司因某具体原因拒了我"，是最容易反推身份的字段。
   但**归因类别必须保留**——它正是报告最有价值的部分。
3. **JD 原文不进入报告**（报告本身只输出能力项计数，不含原文，无需额外处理）。
4. 岗位名保留：方向归类需要，且单看岗位名不构成身份信息。

数据定位：本批是**样例/验证数据**（D001–D040 与 D041–D090 同源同格式），
报告中会如实标注这一点，不作为作者真实求职记录对外宣称。
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
DEFAULT_OUT = ROOT / "docs" / "reflow_sample.md"


def anonymize(records: list[dict]) -> list[dict]:
    """公司名换成稳定代号，备注换成归因标签。

    **归因必须在脱敏之前算完**——先在原始备注上判定"可控/不可控"，
    再把备注替换成标签。否则标签里的措辞和原词对不上，
    归因结果会变（比如「偏向学术」→「项目偏学术、缺落地」就判不出来了），
    **脱敏会悄悄改变分析结论**，这是原则性错误。
    """
    alias: dict[str, str] = {}
    out: list[dict] = []
    for r in records:
        company = r.get("company", "")
        if company and company not in alias:
            # 用「企业 01 / 02…」这种纯序号代号，比字母+数字后缀更好读
            alias[company] = f"企业 {len(alias) + 1:02d}"
        rec = dict(r)
        rec["company"] = alias.get(company, company)
        note = r.get("note", "")
        # 先判归因（用原始备注），再压标签
        rec["_attr"] = rf.attribute_rejection(note)
        rec["note"] = _note_to_label(note)
        out.append(rec)
    return out


def _note_to_label(note: str) -> str:
    """把具体备注压成归因标签，保留分析价值、去掉可定位细节。"""
    n = note or ""
    low = n.lower()
    if any(k in low for k in rf.EXTERNAL_FACTORS):
        # 细分到具体外部因素类型，但不写具体公司/岗位
        if any(k in n for k in ("hc", "名额", "招满", "已满", "暂停", "补招", "关闭", "取消")):
            return "不可控：HC/名额收紧"
        if "学历" in n or "院校" in n or "批次" in n or "硕士" in n or "本科" in n:
            return "不可控：学历/院校门槛"
        if any(k in n for k in ("地点", "城市", "出差")):
            return "不可控：地点/出差冲突"
        return "不可控：岗位竞争/资格线"
    if any(k in n for k in rf.CONTROLLABLE_FACTORS):
        if "笔试" in n or "得分" in n or "及格" in n:
            return "可控：笔试/得分未达标"
        if "学术" in n:
            return "可控：项目偏学术、缺落地"
        return "可控：缺少相关项目经验"
    if any(k in n for k in rf.INTERVIEW_GAPS):
        if any(k in n for k in ("保守", "创新", "同质化", "片面")):
            return "面试暴露：思路保守/缺差异化"
        if any(k in n for k in ("耗时", "出错", "错误", "偏差", "不及格")):
            return "面试暴露：硬技能/正确性不达标"
        return "面试暴露：原理/深度理解不足"
    if "offer" in low:
        return "拿到 offer"
    if "猎头" in n or "内推" in n or "公众号" in n or "官网" in n:
        return "无反馈：渠道未回状态"
    return "其他"


SAMPLE_NOTE = (
    "**样例/验证数据**（D041–D090，与 D001–D040 同源同格式、时间连续）。"
    "公司名已替换为代号、回流备注已压成归因标签——**不含任何可定位到具体投递的信息**。"
    "用途：展示「真实中文 JD + 真实回流」跑出来的报告长什么样。"
    "**不**作为作者真实求职记录对外宣称。"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(DEFAULT_CSV))
    ap.add_argument("--profile", default=str(DEFAULT_PROFILE))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    csv_path = Path(args.csv)
    profile_path = Path(args.profile)
    if not csv_path.exists():
        print(f"记录文件不存在：{csv_path}", file=sys.stderr)
        return 1
    if not profile_path.exists():
        print(f"经历文件不存在：{profile_path}", file=sys.stderr)
        return 1

    records = rf.load_records(csv_path)
    profile = profile_path.read_text(encoding="utf-8")
    res = rf.analyze_reflow(anonymize(records), profile, "terminal", None)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        rf.render_report(
            res,
            title="投递回流校准报告（真实中文 JD · 脱敏样例）",
            data_note=SAMPLE_NOTE,
        ),
        encoding="utf-8",
    )

    print("=" * 56)
    print("脱敏回流报告样例")
    print("=" * 56)
    print(rf.render_console_summary(res))
    print()
    print(f"已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
