# -*- coding: utf-8 -*-
"""Inter-annotator agreement (Cohen's kappa) and optional engine-vs-human accuracy.

Usage:
    python benchmark/agreement.py \
        --cases benchmark/cases_v0.jsonl \
        --a annotations_a1.jsonl --b annotations_a2.jsonl [--engine] \
        [--bootstrap 2000 --seed 0] \
        [--datacard benchmark/datacard.md] \
        [--consensus benchmark/consensus.jsonl]

Design notes (why these exist):
- ``bootstrap_kappa`` reports a 95% CI with **no numpy dependency** — the project's
  "zero core dependency" rule applies to the benchmark tooling too. Pure-Python
  percentile over resampled kappas. The plan (docs/benchmark-plan.md §3) requires
  "always report bootstrap 95% CI, not a single point estimate".
- ``--datacard`` emits a reproducible markdown data card so the benchmark result
  is a file others can cite, not a paste from a terminal.
- ``--consensus`` emits adjudication-ready labels: where the two annotators agree
  the label stands; where they disagree (or only one labeled) it is flagged
  ``needs_review`` so a third pass resolves it without losing either raw label.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
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


def bootstrap_kappa(pairs: list[tuple[str, str]], n: int = 2000, seed: int = 0):
    """95% CI for Cohen's kappa via non-parametric bootstrap (pure Python).

    Returns ``(lo, hi)`` or ``(None, None)`` when there are too few pairs to
    resample. Deterministic for a given ``seed`` so the data card is reproducible.
    """
    m = len(pairs)
    if m < 2 or n <= 0:
        return (None, None)
    rng = random.Random(seed)
    samples: list[float] = []
    for _ in range(n):
        s = [pairs[rng.randrange(m)] for _ in range(m)]
        k = cohen_kappa(s)
        if k is not None:
            samples.append(k)
    if not samples:
        return (None, None)
    samples.sort()
    lo = samples[int(0.025 * len(samples))]
    hi = samples[min(len(samples) - 1, int(0.975 * len(samples)))]
    return (lo, hi)


def _fmt_kappa(x: float | None) -> str:
    return "  n/a" if x is None else f"{x:5.2f}"


def _fmt_ci(ci) -> str:
    if ci[0] is None:
        return "    n/a"
    return f"[{ci[0]:.2f}, {ci[1]:.2f}]"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--engine", action="store_true",
                    help="also score the rule engine against the human consensus")
    ap.add_argument("--bootstrap", type=int, default=2000,
                    help="bootstrap iterations for 95%% CI; 0 disables (default 2000)")
    ap.add_argument("--seed", type=int, default=0,
                    help="bootstrap RNG seed for reproducible CIs (default 0)")
    ap.add_argument("--datacard", default="",
                    help="write a reproducible markdown data card to this path")
    ap.add_argument("--consensus", default="",
                    help="write adjudication-ready consensus labels to this path")
    args = ap.parse_args()

    cases = {c["id"]: c for c in load_jsonl(args.cases)}
    a = {r["id"]: r.get("labels", {}) for r in load_jsonl(args.a)}
    b = {r["id"]: r.get("labels", {}) for r in load_jsonl(args.b)}

    pairs_by_cap: dict[str, list[tuple[str, str]]] = defaultdict(list)
    mismatches: list[tuple[str, str, str | None, str | None]] = []
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
                if sa != sb:
                    mismatches.append((cid, key, sa, sb))
            elif sa or sb:
                one_sided += 1

    all_pairs = [p for ps in pairs_by_cap.values() for p in ps]
    overall_kappa = cohen_kappa(all_pairs)
    overall_ci = bootstrap_kappa(all_pairs, args.bootstrap, args.seed) if args.bootstrap else (None, None)

    print(f"cases={len(cases)}  double-labeled={both}  one-sided={one_sided}")
    print(f"overall agreement={sum(1 for x, y in all_pairs if x == y) / max(1, len(all_pairs)):.1%}"
          f"  kappa={_fmt_kappa(overall_kappa)}"
          + (f"  95% CI {_fmt_ci(overall_ci)}" if args.bootstrap else ""))
    print()
    print(f"{'capability':<22}{'n':>5}{'agree':>9}{'kappa':>8}{'95% CI':>16}")
    print("-" * 62)
    for key in sorted(pairs_by_cap):
        ps = pairs_by_cap[key]
        agree = sum(1 for x, y in ps if x == y) / len(ps)
        k = cohen_kappa(ps)
        ci = bootstrap_kappa(ps, args.bootstrap, args.seed) if args.bootstrap else (None, None)
        print(f"{key:<22}{len(ps):>5}{agree:>8.0%}{_fmt_kappa(k):>8}{_fmt_ci(ci):>16}")

    engine_stats = None
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
            matches, _ = matching.match(reqs, case["profile"])
            for req in case["requirements"]:
                key = req["key"]
                sa = (la.get(key) or {}).get("status")
                sb = (lb.get(key) or {}).get("status")
                if not sa or sa != sb:
                    continue
                got = matches.get(key)
                eng_by_cap[key].append(bool(got and got.status == sa))
        total = sum(len(v) for v in eng_by_cap.values())
        correct = sum(sum(v) for v in eng_by_cap.values())
        for key in sorted(eng_by_cap):
            v = eng_by_cap[key]
            print(f"{key:<22}{len(v):>5}{sum(v) / len(v):>8.0%}")
        if total:
            print("-" * 40)
            print(f"{'overall':<22}{total:>5}{correct / total:>8.0%}")
        engine_stats = (total, correct, eng_by_cap)

    if args.consensus:
        _write_consensus(args.consensus, cases, a, b)
        print(f"\nwrote consensus labels -> {args.consensus}")

    if args.datacard:
        _write_datacard(args, cases, pairs_by_cap, both, one_sided, all_pairs,
                        overall_kappa, overall_ci, mismatches, engine_stats)
        print(f"wrote data card -> {args.datacard}")

    return 0


def _write_consensus(path: str, cases, a, b) -> None:
    out = []
    for cid, case in cases.items():
        la, lb = a.get(cid, {}), b.get(cid, {})
        labels: dict[str, dict] = {}
        keys = set(la) | set(lb)
        for key in keys:
            va = (la.get(key) or {}).get("status")
            vb = (lb.get(key) or {}).get("status")
            if va and vb and va == vb:
                labels[key] = {"status": va,
                               "evidence": (la.get(key) or {}).get("evidence", ""),
                               "needs_review": False}
            else:
                chosen = va or vb
                labels[key] = {
                    "status": chosen or "missing",
                    "evidence": ((la.get(key) or lb.get(key) or {}).get("evidence", "")),
                    "needs_review": True,
                    "raw_a": va, "raw_b": vb,
                }
        reviewed = bool(labels) and all(
            (labels.get(r["key"]) or {}).get("status") for r in case["requirements"]
        )
        out.append(json.dumps({"id": cid, "annotator": "consensus",
                               "labels": labels, "reviewed": reviewed},
                              ensure_ascii=False))
    Path(path).write_text("\n".join(out) + "\n", encoding="utf-8")


def _write_datacard(args, cases, pairs_by_cap, both, one_sided, all_pairs,
                    overall_kappa, overall_ci, mismatches, engine_stats) -> None:
    L: list[str] = []
    L.append("# career-loop benchmark data card")
    L.append("")
    L.append("> 由 `benchmark/agreement.py` 自动生成。数值部分可复现；叙事/法律部分见"
             " `benchmark/datacard_template.md` 的留白说明。")
    L.append("")
    L.append("## 0. 元数据")
    L.append("")
    L.append(f"- 生成时间（UTC）：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
    L.append(f"- cases 文件：`{args.cases}`")
    L.append(f"- 标注人 A：`{args.a}`　B：`{args.b}`")
    L.append(f"- bootstrap：{args.bootstrap} 次，seed={args.seed}"
             + ("（已关闭）" if not args.bootstrap else ""))
    L.append("")
    L.append("## 1. 数据集摘要")
    L.append("")
    L.append(f"- 案例总数：{len(cases)}")
    L.append(f"- 双标注（两人均标）：{both}")
    L.append(f"- 单标注（仅一人标）：{one_sided}")
    L.append(f"- 双标注占比：{both / max(1, both + one_sided):.1%}"
             f"（目标 ≥ 20%，见 benchmark-plan.md）")
    L.append("")
    L.append("## 2. 标注一致性（Cohen's kappa）")
    L.append("")
    agree = sum(1 for x, y in all_pairs if x == y) / max(1, len(all_pairs))
    L.append(f"- 总体一致率：{agree:.1%}")
    L.append(f"- 总体 kappa：{overall_kappa:.2f}" if overall_kappa is not None
             else "- 总体 kappa：n/a")
    L.append(f"- 总体 95% CI：{_fmt_ci(overall_ci)}" if args.bootstrap else
             "- 总体 95% CI：未计算（加 `--bootstrap`）")
    L.append("")
    L.append("## 3. 分能力一致性")
    L.append("")
    L.append(f"{'能力':<20}{'n':>6}{'一致率':>9}{'kappa':>9}{'95% CI':>18}")
    L.append("-" * 64)
    for key in sorted(pairs_by_cap):
        ps = pairs_by_cap[key]
        ag = sum(1 for x, y in ps if x == y) / len(ps)
        k = cohen_kappa(ps)
        ci = bootstrap_kappa(ps, args.bootstrap, args.seed) if args.bootstrap else (None, None)
        L.append(f"{key:<20}{len(ps):>6}{ag:>8.0%}{_fmt_kappa(k):>9}{_fmt_ci(ci):>18}")
    L.append("")
    if engine_stats is not None:
        total, correct, eng_by_cap = engine_stats
        L.append("## 4. 引擎 vs 人工（仅在 --engine）")
        L.append("")
        L.append(f"- 总体准确率：{correct / total:.1%}（n={total}）")
        L.append("")
        L.append(f"{'能力':<20}{'n':>6}{'准确率':>9}")
        L.append("-" * 36)
        for key in sorted(eng_by_cap):
            v = eng_by_cap[key]
            L.append(f"{key:<20}{len(v):>6}{sum(v) / len(v):>8.0%}")
        L.append("")
    L.append("## 5. 双标注分歧样例（前 10 条）")
    L.append("")
    if mismatches:
        for cid, key, sa, sb in mismatches[:10]:
            L.append(f"- `{cid}` / `{key}`：A={sa}　B={sb}")
    else:
        L.append("- 无分歧。")
    L.append("")
    L.append("## 6. 复现命令")
    L.append("")
    cmd = (f"python benchmark/agreement.py --cases {args.cases} --a {args.a} --b {args.b}"
           + (" --engine" if engine_stats is not None else "")
           + (f" --bootstrap {args.bootstrap} --seed {args.seed}" if args.bootstrap else "")
           + f" --datacard {args.datacard}")
    L.append("```bash")
    L.append(cmd)
    L.append("```")
    L.append("")
    L.append("## 7. 待人工填写（模板留白）")
    L.append("")
    L.append("- [ ] 分歧的定性说明（哪类能力容易判错，为什么）")
    L.append("- [ ] 数据来源与授权（source_url / sha256 / 摘录长度，见数据政策）")
    L.append("- [ ] 真实/合成档案的知情同意与脱敏声明")
    L.append("- [ ] 分岗位族覆盖表（build_v1.py validate 可生成骨架）")
    L.append("")
    L.append("详见 `benchmark/datacard_template.md`。")
    Path(args.datacard).write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
