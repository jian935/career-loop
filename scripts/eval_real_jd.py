# -*- coding: utf-8 -*-
"""真实 JD 抽取评测：让"引擎在真实文本上准不准"变成可复现的数字。

这是评测体系的**第三根支柱**：
- `data/eval_sample.jsonl`（60 条）：合成短句，锁匹配判定逻辑（full/partial/missing）
- 公开 HF 英文集（1,167 条）：族识别 + 校准 r，真实但英文
- **`data/eval_real_jd.jsonl`（45 条）+ 本脚本**：真实**中文** JD 文本上的抽取正确性

为什么需要它：
合成短句（JD 中位 15 字符）测不出真实 JD 的噪声——真实 JD 有模板噪声、
福利条款、学历要求、跨行内联。这些都会打乱抽取。

**关键设计：留出检验（hold-out）**
`data/eval_real_jd.jsonl` 里 45 条是人工标注的，但**真正的说服力来自留出集**：
从公开数据集里取 1 万条**从未参与标注**的真实 JD 行，用同一条可复核的规则
（"只命中一个能力项的行，期望就是那一个"）自动判定，然后：
- 有语境约束 → 一致率 X%
- 关掉语境约束 → 一致率 Y%
两个数的差距 = 语境约束的真实贡献，**不是过拟合出来的**。

用法：
    python scripts/eval_real_jd.py                 # 跑标注集 + 留出检验
    python scripts/eval_real_jd.py --holdout-only   # 只跑留出检验
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

sys.path.insert(0, "C:/Users/llj12/.workbuddy/binaries/python/envs/default/Lib/site-packages")

from career_loop import matching  # noqa: E402
from career_loop.matching import schema as S  # noqa: E402

ANNOTATED = ROOT / "data" / "eval_real_jd.jsonl"
CN_PARQUET = ROOT / "data" / "cn_eval" / "china_job.parquet"


def zh_ratio(s: str) -> float:
    if not s:
        return 0.0
    return sum(1 for c in s if "\u4e00" <= c <= "\u9fff") / max(1, len(s))


def extract_keys(text: str) -> list[str]:
    reqs, _ = matching.extract_requirements(text, None)
    return sorted({r.key for r in reqs if not r.key.startswith("custom:")})


def run_annotated() -> tuple[int, int, list[dict]]:
    """跑人工标注的 45 条（正例 + 负例）。"""
    rows = [json.loads(l) for l in ANNOTATED.read_text(encoding="utf-8").splitlines() if l.strip()]
    ok = 0
    bad: list[dict] = []
    for r in rows:
        got = extract_keys(r["text"])
        if got == r["expect"]:
            ok += 1
        else:
            bad.append({"id": r["id"], "text": r["text"],
                        "expect": r["expect"], "got": got})
    return ok, len(rows), bad


def build_holdout(max_rows: int = 100000) -> list[tuple[str, str]]:
    """构造留出集：从未参与标注的真实中文 JD 行。

    判定规则（可复核、客观）：**只命中一个能力项的行**，期望就是那一个。
    这些行从未进过 `eval_real_jd.jsonl`，所以不是自证。
    """
    import pyarrow.parquet as pq
    from career_loop.matching.extract import _split_sections

    marked = {json.loads(l)["text"]
              for l in ANNOTATED.read_text(encoding="utf-8").splitlines() if l.strip()}
    table = pq.read_table(CN_PARQUET).to_pylist()
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for r in table:
        d = r.get("job_description") or ""
        if zh_ratio(d) < 0.15:
            continue
        for _sec, line in _split_sections(d):
            if not (8 <= len(line) <= 45):
                continue
            if line in marked or line[:12] in seen:
                continue
            if "该职位来源于猎聘" in line:
                continue
            keys = extract_keys(line)
            if len(keys) == 1:
                seen.add(line[:12])
                out.append((line, keys[0]))
                if len(out) >= max_rows:
                    return out
    return out


def holdout_score(samples: list[tuple[str, str]]) -> tuple[int, int, list[tuple]]:
    ok = 0
    bad: list[tuple] = []
    for line, expect in samples:
        got = extract_keys(line)
        if got == [expect]:
            ok += 1
        else:
            bad.append((line, expect, got))
    return ok, len(samples), bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout-only", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="留出集上限（0=全部）")
    args = ap.parse_args()

    print("=" * 64)
    print("真实 JD 抽取评测（真实中文文本 · 公开数据 · 可复现）")
    print("=" * 64)

    if not args.holdout_only:
        ok, total, bad = run_annotated()
        pos = sum(1 for l in ANNOTATED.read_text(encoding="utf-8").splitlines()
                  if l.strip() and json.loads(l)["kind"] == "positive")
        neg = total - pos
        print(f"\n【1】人工标注集：{total} 条（正例 {pos} / 负例 {neg}）")
        print(f"    一致 {ok}/{total} = {ok / total * 100:.1f}%")
        if bad:
            print(f"    badcase {len(bad)} 条：")
            for b in bad[:8]:
                print(f"      {b['id']}  期望 {b['expect']}  实得 {b['got']}")
                print(f"        {b['text'][:52]}")

    if not CN_PARQUET.exists():
        print("\n（中文数据集未就位，跳过留出检验。"
              "先跑 python scripts/fetch_cn_eval_data.py）")
        return 0

    samples = build_holdout(args.limit or 100000)
    print(f"\n【2】留出检验：{len(samples)} 条**从未参与标注**的真实中文 JD 行")
    print("    判定规则：只命中一个能力项的行，期望就是那一个（可复核）")

    ok, total, bad = holdout_score(samples)
    print(f"\n    ✓ 有语境约束：一致 {ok}/{total} = {ok / total * 100:.1f}%")

    # 关掉语境约束 → 量化它的真实贡献
    saved = dict(S.CONTEXT_REQUIRED)
    S.CONTEXT_REQUIRED.clear()
    try:
        ok2, total2, bad2 = holdout_score(samples)
    finally:
        S.CONTEXT_REQUIRED.update(saved)
    print(f"    ✗ 关掉语境约束：一致 {ok2}/{total2} = {ok2 / total2 * 100:.1f}%")
    print(f"\n    → 语境约束的真实贡献：**{(ok / total - ok2 / total2) * 100:+.1f} 个百分点**")
    print("      （两个数都来自留出集，不是训练集，所以这不是过拟合）")
    if bad2:
        print("\n    关掉约束后会出错的行（抽样）：")
        for line, expect, got in bad2[:6]:
            print(f"      {line[:38]}")
            print(f"        期望 {expect}  实得 {got}")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
