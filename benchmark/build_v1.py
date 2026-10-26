# -*- coding: utf-8 -*-
"""benchmark v1 scaffolding generator.

v1 target (see docs/benchmark-plan.md): 300 (JD x profile) cases across 30+
job families, two independent annotators on >= 20%, Cohen's kappa >= 0.70,
a public data card. The *content* (real, compliant JDs + profiles) must be
sourced by a human / volunteer cohort — this script only builds and checks the
**framework**, it never fabricates JD text.

Subcommands:
    plan                       print the balanced 300-case / 30-family target
    scaffold --out PATH        write 300 empty id/family slots (TODO markers)
    validate cases.jsonl [...] check coverage + double-label readiness

Usage:
    python benchmark/build_v1.py plan
    python benchmark/build_v1.py scaffold --out benchmark/cases_v1_scaffold.jsonl
    python benchmark/build_v1.py validate benchmark/cases_v1.jsonl \\
        --a annotations_a1.jsonl --b annotations_a2.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TARGET_TOTAL = 300
TARGET_FAMILIES = 30
DOUBLE_LABEL_FRACTION = 0.20

TODO_MARKERS = ("TODO", "TODO_SOURCE_JD", "TODO_SOURCE_PROFILE", "NEEDS_JD", "NEEDS_PROFILE")


def _families() -> list[str]:
    from career_loop.matching.schema import DOMAIN_PACKS
    return sorted(DOMAIN_PACKS.keys())


def _distribute(total: int, n: int) -> list[int]:
    base, rem = divmod(total, n)
    return [base + (1 if i < rem else 0) for i in range(n)]


def cmd_plan(args: argparse.Namespace) -> int:
    fams = _families()[: args.families]
    counts = _distribute(args.total, len(fams))
    print(f"v1 目标：{args.total} 个案例，覆盖 {len(fams)} 个岗位族（每个约 {args.total // len(fams)} 个）")
    print(f"双标注子集（>= {int(args.total * DOUBLE_LABEL_FRACTION)} 个 = {DOUBLE_LABEL_FRACTION:.0%}）由标注流程保证。\n")
    print(f"{'岗位族':<18}{'案例数':>8}")
    print("-" * 26)
    for f, c in zip(fams, counts):
        print(f"{f:<18}{c:>8}")
    print("\n数据来源（合规）：公共 ATS JSON（Greenhouse/Lever/Ashby）或自有合规 JD；")
    print("不要抓 LinkedIn / Boss / 猎聘。详见 benchmark/README.md 数据政策。")
    return 0


def cmd_scaffold(args: argparse.Namespace) -> int:
    fams = _families()[: args.families]
    counts = _distribute(args.total, len(fams))
    rows = []
    for f, c in zip(fams, counts):
        for i in range(1, c + 1):
            rows.append({
                "id": f"v1-{f}-{i:02d}",
                "language": "zh",
                "job_family": f,
                "jd": "TODO_SOURCE_JD",
                "profile": "TODO_SOURCE_PROFILE",
                "requirements": [],
                "labels": {},
            })
    Path(args.out).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                              encoding="utf-8")
    print(f"已写 {len(rows)} 个空槽位到 {args.out}")
    print("每个槽位是 TODO 占位（jd/profile 为 TODO 标记，requirements 为空），")
    print("**不是真实数据**：请填入合规 JD + 简历，并用 build_v0.py 的同款方式预抽 requirements。")
    return 0


def _load_jsonl(path: str) -> list[dict]:
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def cmd_validate(args: argparse.Namespace) -> int:
    cases = _load_jsonl(args.cases)
    fam_counts = Counter(c.get("job_family", "?") for c in cases)
    n_fam = len(fam_counts)

    print(f"案例总数：{len(cases)}（目标 {TARGET_TOTAL}，缺口 {max(0, TARGET_TOTAL - len(cases))}）")
    print(f"覆盖岗位族：{n_fam}（目标 >= {TARGET_FAMILIES}，缺口 {max(0, TARGET_FAMILIES - n_fam)}）")
    print()
    print(f"{'岗位族':<18}{'案例':>6}{'占比':>8}")
    print("-" * 34)
    for f, c in fam_counts.most_common():
        print(f"{f:<18}{c:>6}{c / max(1, len(cases)):>7.0%}")

    # content readiness: flag TODO / empty
    not_ready = [c["id"] for c in cases
                 if (c.get("jd") in TODO_MARKERS) or (c.get("profile") in TODO_MARKERS)
                 or not c.get("requirements")]
    print()
    if not_ready:
        print(f"未就绪（含 TODO 标记或 requirements 为空）：{len(not_ready)} / {len(cases)}")
    else:
        print("全部案例均有 JD / 简历 / 预抽 requirements。")

    # double-label readiness (optional)
    if args.a and args.b:
        a = {r["id"]: r for r in _load_jsonl(args.a)}
        b = {r["id"]: r for r in _load_jsonl(args.b)}
        double = [cid for cid in (set(a) & set(b))]
        print()
        print(f"双标注就绪：{len(double)} / {len(cases)} "
              f"（目标 >= {int(TARGET_TOTAL * DOUBLE_LABEL_FRACTION)}）")
        dbl_fam = Counter(a[cid].get("job_family", cases_by_id(cases, cid)) for cid in double)
        missing_fam = [f for f in fam_counts if dbl_fam.get(f, 0) == 0]
        if missing_fam:
            print(f"以下族尚无双标注样本：{', '.join(missing_fam)}")
        else:
            print("每个已覆盖族都至少有一个双标注样本。")
    elif args.a or args.b:
        print("\n（给出 --a 和 --b 两个标注文件可同时检查双标注覆盖率）")
    return 0


def cases_by_id(cases: list[dict], cid: str) -> str:
    for c in cases:
        if c.get("id") == cid:
            return c.get("job_family", "?")
    return "?"


def main() -> int:
    ap = argparse.ArgumentParser(description="benchmark v1 scaffolding generator")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan", help="print the balanced target manifest")
    p.add_argument("--total", type=int, default=TARGET_TOTAL)
    p.add_argument("--families", type=int, default=TARGET_FAMILIES)
    p.set_defaults(func=cmd_plan)

    s = sub.add_parser("scaffold", help="write empty id/family slots (TODO markers)")
    s.add_argument("--out", default="benchmark/cases_v1_scaffold.jsonl")
    s.add_argument("--total", type=int, default=TARGET_TOTAL)
    s.add_argument("--families", type=int, default=TARGET_FAMILIES)
    s.set_defaults(func=cmd_scaffold)

    v = sub.add_parser("validate", help="check coverage + double-label readiness")
    v.add_argument("cases")
    v.add_argument("--a", default="")
    v.add_argument("--b", default="")
    v.set_defaults(func=cmd_validate)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
