# -*- coding: utf-8 -*-
"""诊断中文族识别的失败模式：空预测 vs 错预测，按期望族归类。"""

from __future__ import annotations

import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from career_loop.matching.schema import detect_domains
from scripts.cn_eval_family import DATA, TITLE_TO_FAMILY, label_of, zh_ratio


def main() -> None:
    import pyarrow.parquet as pq

    rows = pq.read_table(DATA).to_pylist()

    total = 0
    hit = 0
    empty = 0  # 完全没输出
    wrong = 0  # 输出了但没一个族对
    per_empty = collections.Counter()
    per_wrong = collections.Counter()
    per_tot = collections.Counter()
    pred_when_empty = collections.Counter()
    wrong_pred_counter = collections.Counter()

    for r in rows:
        text = r.get("job_description") or ""
        if zh_ratio(text) < 0.15:
            continue
        title = r.get("job_title") or ""
        expected = label_of(title)
        if not expected:
            continue
        total += 1
        # 用期望族里第一个做主统计键（多族标签取全集判断命中）
        for fam in expected:
            per_tot[fam] += 1
        preds = set(detect_domains(text))
        if preds & expected:
            hit += 1
            continue
        if not preds:
            empty += 1
            for fam in expected:
                per_empty[fam] += 1
        else:
            wrong += 1
            for fam in expected:
                per_wrong[fam] += 1
            for p in preds:
                wrong_pred_counter[p] += 1

    miss = total - hit
    print(f"总计 {total} 命中 {hit} 未命中 {miss}")
    print(f"  空预测（词表零命中）: {empty}  ({empty/miss*100:.1f}% of misses)")
    print(f"  错预测（输出但不含期望族）: {wrong}  ({wrong/miss*100:.1f}% of misses)")
    print()
    print("按期望族的空预测/错预测分布（miss 数排序，只列 miss≥5 的族）:")
    fam_miss = {f: per_empty[f] + per_wrong[f] for f in per_tot}
    for fam, m in sorted(fam_miss.items(), key=lambda kv: -kv[1])[:25]:
        if m < 5:
            continue
        print(f"  {fam:16s} miss={m:3d} (empty={per_empty[fam]:3d} wrong={per_wrong[fam]:3d} tot={per_tot[fam]:3d})")
    print()
    print("错预测时最常误输出成什么族（Top 15）:")
    for p, c in wrong_pred_counter.most_common(15):
        print(f"  -> {p:16s} {c}")


if __name__ == "__main__":
    main()
