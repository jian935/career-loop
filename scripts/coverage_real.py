# -*- coding: utf-8 -*-
"""Measure LLM requirement-extraction coverage on real job posts.

Usage:
    python scripts/coverage_real.py --data real_jds.jsonl --workers 6 \
        --report benchmark/real_jd_coverage.md
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from career_loop.cli import _load_dotenv
from career_loop.matching.extract import extract_by_llm
from career_loop.matching.schema import ALL_DIMS

_load_dotenv()


def one(job: dict, llm) -> dict:
    for attempt in range(2):
        try:
            reqs = extract_by_llm(job["description"], llm)
            keys = [r.key for r in reqs]
            canon = [k for k in keys if k in ALL_DIMS]
            new = [k for k in keys if k not in ALL_DIMS]
            return {
                "id": job["id"], "category": job["category"],
                "title": job["title"], "ok": True, "n": len(reqs),
                "canon": len(canon), "new": len(new),
                "new_labels": [r.label for r in reqs if r.key not in ALL_DIMS],
                "keys": keys,
            }
        except Exception as exc:  # noqa: BLE001
            if attempt == 1:
                return {"id": job["id"], "category": job["category"],
                        "title": job["title"], "ok": False, "error": str(exc)[:160]}
            time.sleep(1.5)
    return {"id": job["id"], "category": job["category"], "title": job["title"],
            "ok": False, "error": "unknown"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--report", default="benchmark/real_jd_coverage.md")
    args = ap.parse_args()

    from career_loop.matching.llm import LLM
    llm = LLM()
    if not llm.available:
        print("LLM 未配置：先设置 .env 或环境变量")
        return 1

    jobs = [json.loads(line) for line in Path(args.data).read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        jobs = jobs[: args.limit]
    print(f"jobs={len(jobs)} workers={args.workers} model={llm.model}")

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(one, j, llm): j for j in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            results.append(r)
            if i % 10 == 0:
                print(f"  {i}/{len(jobs)}")

    ok = [r for r in results if r["ok"]]
    bad = [r for r in results if not r["ok"]]
    total_req = sum(r["n"] for r in ok)
    total_canon = sum(r["canon"] for r in ok)
    total_new = sum(r["new"] for r in ok)
    with_canon = sum(1 for r in ok if r["canon"] > 0)

    by_cat = defaultdict(list)
    for r in results:
        by_cat[r["category"]].append(r)

    lines = ["# 真实 JD 覆盖报告（LLM 抽取）", "",
             f"- 样本：**{len(jobs)}** 条，{len(by_cat)} 个类别",
             f"- 抽取成功：**{len(ok)}** / {len(results)}（失败 {len(bad)}）",
             f"- 平均要求数：**{total_req / max(1, len(ok)):.1f}**",
             f"- 标准能力 key：**{total_canon}**（{total_canon / max(1, total_req):.0%}）",
             f"- LLM 自建 key：**{total_new}**（{total_new / max(1, total_req):.0%}）",
             f"- 至少命中 1 个标准能力的 JD：**{with_canon}/{len(ok)}**（{with_canon / max(1, len(ok)):.0%}）",
             "", "## 分类覆盖", "",
             "| 类别 | 条数 | 成功 | 平均要求 | 标准 key 占比 |",
             "| --- | ---: | ---: | ---: | ---: |"]
    for cat, rs in sorted(by_cat.items(), key=lambda x: -len(x[1])):
        oks = [r for r in rs if r["ok"]]
        n = sum(r["n"] for r in oks)
        c = sum(r["canon"] for r in oks)
        lines.append(f"| {cat} | {len(rs)} | {len(oks)} | {n / max(1, len(oks)):.1f} | {c / max(1, n):.0%} |")

    labels = defaultdict(int)
    for r in ok:
        for lab in r["new_labels"]:
            labels[lab] += 1
    lines += ["", "## LLM 自建能力项 Top 20", ""]
    for lab, n in sorted(labels.items(), key=lambda x: -x[1])[:20]:
        lines.append(f"- {lab} × {n}")

    if bad:
        lines += ["", "## 失败样例（前 5 条）", ""]
        for r in bad[:5]:
            lines.append(f"- {r['title']}: {r['error']}")

    lines += ["", "> 说明：标准 key 指项目 33 个岗位族；自建 key（`custom:`/`llm:`）表示该岗位超出了预置词表。"]
    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nok={len(ok)} failed={len(bad)} avg_req={total_req / max(1, len(ok)):.1f} "
          f"canon={total_canon / max(1, total_req):.0%} new={total_new / max(1, total_req):.0%}")
    print("report ->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
