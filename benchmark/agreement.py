# -*- coding: utf-8 -*-
"""Inter-annotator agreement (Cohen's kappa) and optional engine-vs-human accuracy.

Usage:
    python benchmark/agreement.py \
        --cases benchmark/cases_v0.jsonl \
        --a annotations_a1.jsonl --b annotations_a2.jsonl [--engine]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CATS = ("full", "partial", "missing")


def load_jsonl(path: str) -> list[dict]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    n = len(pairs)
    if n == 0:
        return None
    po = sum(1 for a, b in pairs if a == b) / n
    pa = {c: sum(1 for a, _ in pairs if a == c) / n for c in CATS}
    pb = {c: sum(1 for _, b in pairs if b == c) / n for c in CATS}
    pe = sum(pa[c] * pb[c] for c in CATS)
    if pe >= 1:
        return 1.0
    return (po - pe) / (1 - pe)


def fmt(x: float | None) -> str:
    return "  n/a" if x is None else f"{x:5.2f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--engine", action="store_true",
                    help="also score the rule engine against the human consensus")
    args = ap.parse_args()

    cases = {c["id"]: c for c in load_jsonl(args.cases)}
    a = {r["id"]: r.get("labels", {}) for r in load_jsonl(args.a)}
    b = {r["id"]: r.get("labels", {}) for r in load_jsonl(args.b)}

    pairs_by_cap: dict[str, list[tuple[str, str]]] = defaultdict(list)
    both = one_sided = 0

    for cid, case in cases.items():
        la, lb = a.get(cid, {}), b.get(cid, {})
        for req in case["requirements"]:
            key = req["key"]
            sa = (la.get(key) or {}).get("status")
            sb = (lb.get(key) or {}).get("status")
            if sa and sb:
                pairs_by_cap[key].append((sa, sb))
                both += 1
            elif sa or sb:
                one_sided += 1

    all_pairs = [p for ps in pairs_by_cap.values() for p in ps]
    print(f"cases={len(cases)}  double-labeled={both}  one-sided={one_sided}")
    print(f"overall agreement={sum(1 for x, y in all_pairs if x == y) / max(1, len(all_pairs)):.1%}"
          f"  kappa={fmt(cohen_kappa(all_pairs))}")
    print()
    print(f"{'capability':<22}{'n':>5}{'agree':>9}{'kappa':>8}")
    print("-" * 46)
    for key in sorted(pairs_by_cap):
        ps = pairs_by_cap[key]
        agree = sum(1 for x, y in ps if x == y) / len(ps)
        print(f"{key:<22}{len(ps):>5}{agree:>8.0%}{fmt(cohen_kappa(ps)):>8}")

    if args.engine:
        from career_loop import matching

        print()
        print("engine vs human consensus (only where both annotators agree)")
        print(f"{'capability':<22}{'n':>5}{'correct':>9}")
        print("-" * 40)
        eng_by_cap: dict[str, list[bool]] = defaultdict(list)
        for cid, case in cases.items():
            la, lb = a.get(cid, {}), b.get(cid, {})
            reqs, _ = matching.extract_requirements(case["jd"])
            pred = matching.match(reqs, case["profile"])
            for req in case["requirements"]:
                key = req["key"]
                sa = (la.get(key) or {}).get("status")
                sb = (lb.get(key) or {}).get("status")
                if not sa or sa != sb:
                    continue
                got = pred.get(key)
                eng_by_cap[key].append(bool(got and got.status == sa))
        total = sum(len(v) for v in eng_by_cap.values())
        correct = sum(sum(v) for v in eng_by_cap.values())
        for key in sorted(eng_by_cap):
            v = eng_by_cap[key]
            print(f"{key:<22}{len(v):>5}{sum(v) / len(v):>8.0%}")
        if total:
            print("-" * 40)
            print(f"{'overall':<22}{total:>5}{correct / total:>8.0%}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
