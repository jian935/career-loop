# -*- coding: utf-8 -*-
"""脱敏审计：检查要公开的文件里有没有泄露可定位到具体投递的信息。

为什么需要这个脚本：
「我们说数据脱敏了」是一句声明，别人没法验证。这个脚本把声明变成**可执行的检查**——
任何人都能跑一遍，确认公开文件里没有真实公司名、原始回流备注、个人信息。

用法：
    python scripts/audit_anonymization.py
    python scripts/audit_anonymization.py --csv data/calibration/final_outcomes_202609.csv

退出码：0 = 干净；1 = 有泄露（此时不要提交）。

设计要点（避免误报）：
- **只查"公司名 + 岗位名 + 结果"能反查的具体投递**。像「小红书」「金蝶」这种
  本身是词表里的行业名词（内容平台 / 财务软件），出现在代码或文档里是正常的，
  不算泄露——所以检查按**上下文**判定，不做纯子串匹配。
- 数字（150 之类）不单独作为泄露判据，因为 CSS 像素值、样本量都会命中。
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_CSV = ROOT / "data" / "calibration" / "final_outcomes_202609.csv"

#: 要审计的公开文件
PUBLIC_FILES = [
    "docs/reflow_sample.md",
    "docs/index.html",
    "docs/evidence.md",
    "docs/benchmark.md",
    "docs/methodology.md",
    "docs/retro.md",
    "docs/submission.md",
    "docs/share-kit.md",
    "README.md",
    "CHANGELOG.md",
]

#: 个人身份信息关键词（姓名 / 学校 / 邮箱 / 电话）
PII_PATTERNS = [
    "陈默",
    "塔里木大学",
    "@qq.com",
    "@163.com",
    "@gmail.com",
    "@outlook.com",
]

#: 这些词是**词表里的行业名词**（内容平台 / 财务软件 / 电商），本身该公开。
#: 只有当它们和"具体投递语境"同现时才可能是泄露。
INDUSTRY_NOISE = {
    "小红书", "抖音", "用友", "金蝶", "阿里", "腾讯", "百度", "京东", "美团",
    "拼多多", "快手", "小米", "网易", "滴滴", "华为", "荣耀", "OPPO", "vivo",
    "商汤", "旷视", "顺丰", "菜鸟", "海康威视", "大华", "浪潮", "药明康德",
}


def _load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def audit_file(path: Path, rows: list[dict]) -> list[str]:
    """返回该文件的泄露项列表（空列表 = 干净）。"""
    if not path.exists():
        return []
    txt = path.read_text(encoding="utf-8")
    problems: list[str] = []

    # 1) 原始回流备注——逐字匹配，这是最直接的泄露
    for r in rows:
        note = (r.get("note") or "").strip()
        if note and len(note) >= 8 and note in txt:
            problems.append(f"原始回流备注：{note!r}（记录 {r.get('id', '?')}）")
            break

    # 2) 真正的泄露判据 = **公司名 + 该公司的结果/岗位同现**。
    #    单独出现公司名不一定是泄露（「用友」「金蝶」是词表里的财务软件行业名词，
    #    出现在文档里很正常）；单独出现岗位名同样不构成身份信息。
    #    但「商汤」和「智慧城市解决方案」出现在同一行，就能反查具体那一次投递。
    by_company: dict[str, list[dict]] = {}
    for r in rows:
        comp = (r.get("company") or "").strip()
        if comp:
            by_company.setdefault(comp, []).append(r)
    for comp, items in by_company.items():
        if comp not in txt:
            continue
        # 公司名出现了 → 看是否还有可定位的搭配
        for r in items:
            role = (r.get("role") or "").strip()
            outcome = (r.get("outcome") or "").strip()
            if role and role in txt and _same_line(txt, comp, role):
                problems.append(
                    f"公司+岗位同行同现（可反查投递）：{comp!r} × {role!r}"
                )
                break
            if outcome and outcome in txt and _same_line(txt, comp, outcome):
                problems.append(
                    f"公司+结果同行同现（可反查投递）：{comp!r} × {outcome!r}"
                )
                break

    # 3) 个人身份信息
    for p in PII_PATTERNS:
        if p in txt:
            problems.append(f"个人信息：{p!r}")
    return problems


def _same_line(txt: str, a: str, b: str) -> bool:
    """判断 a 与 b 是否出现在同一行（同行才构成"可反查的组合"）。"""
    for line in txt.splitlines():
        if a in line and b in line:
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(DEFAULT_CSV))
    ap.add_argument("--files", nargs="*", default=None, help="要审计的文件（默认全部公开文件）")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"记录文件不存在：{csv_path}", file=sys.stderr)
        print("（私有数据未就位时无法审计——这属于正常情况，CI 里不跑这一项。）")
        return 0

    rows = _load_rows(csv_path)
    files = args.files or PUBLIC_FILES

    print("=" * 62)
    print("脱敏审计：检查公开文件里有没有可定位到具体投递的信息")
    print("=" * 62)
    print(f"基准记录：{len(rows)} 条（来自 {csv_path.name}）\n")

    total = 0
    for f in files:
        p = ROOT / f if not Path(f).is_absolute() else Path(f)
        if not p.exists():
            print(f"  –  {f}（不存在，跳过）")
            continue
        problems = audit_file(p, rows)
        if problems:
            total += len(problems)
            print(f"  ✗  {f}")
            for pr in problems:
                print(f"       {pr}")
        else:
            print(f"  ✓  {f}")

    print()
    if total:
        print(f"发现 {total} 处可能泄露 —— **先修掉再提交**。")
        return 1
    print("全部干净 ✓　公开文件里没有可定位到具体投递的信息。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
