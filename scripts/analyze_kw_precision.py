# -*- coding: utf-8 -*-
"""全词表「词 → 族」精确率分析：找出在多个族的 JD 里都高频出现的过泛词。

硬标准（来自 v0.8.7 教训）：一个词过泛，不是"听起来通用"，而是
**它在真实数据的多个 category 里都高频出现**。这里用期望族做 category。

对 DOMAIN_PACKS 里每个词计算：
  - occ：在可检验 JD 里出现的次数
  - own：出现且期望族含本族的次数
  - prec = own / occ
prec 低的词 = 在误吸别族 JD，是错预测的主要来源。
"""

from __future__ import annotations

import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from career_loop.matching.boilerplate import strip_boilerplate
from career_loop.matching.schema import DOMAIN_PACKS
from scripts.cn_eval_family import DATA, label_of, zh_ratio


def main() -> None:
    import pyarrow.parquet as pq

    rows = pq.read_table(DATA).to_pylist()

    # 预筛可检验记录（先剥样板——引擎看到的也是剥过的文本，
    # 不剥会把「职位来源于智联招聘」造成的假命中算成词表问题）
    recs: list[tuple[str, set[str]]] = []
    for r in rows:
        text = r.get("job_description") or ""
        if zh_ratio(text) < 0.15:
            continue
        title = r.get("job_title") or ""
        expected = label_of(title)
        if not expected:
            continue
        recs.append((strip_boilerplate(text).lower(), expected))

    print(f"可检验记录 {len(recs)} 条")

    # 每族统计
    stats: dict[tuple[str, str], list[int]] = collections.defaultdict(lambda: [0, 0])
    fam_occ = collections.Counter()
    for fam, pack in DOMAIN_PACKS.items():
        for spec_key, spec in pack.items():
            for kw in spec["kw"]:
                kwl = kw.lower()
                for text, expected in recs:
                    if kwl in text:
                        stats[(fam, kw)][0] += 1
                        if fam in expected:
                            stats[(fam, kw)][1] += 1

    # 汇总每族
    print("\n各族的词表总误吸情况（occ=出现次数, own=期望族命中, 按漏吸排序）:")
    fam_agg = collections.defaultdict(lambda: [0, 0])
    for (fam, kw), (occ, own) in stats.items():
        fam_agg[fam][0] += occ
        fam_agg[fam][1] += own
    for fam, (occ, own) in sorted(fam_agg.items(), key=lambda kv: kv[1][0] - kv[1][1], reverse=True)[:15]:
        print(f"  {fam:16s} occ={occ:5d} own={own:5d} leak={occ-own:5d} prec={own/max(occ,1)*100:5.1f}%")

    # 逐词：找出 occ>=15 且 prec<40% 的词
    print("\n过泛词候选（occ≥15 且 prec<40%），按漏吸排序 Top 30:")
    bad = [(kw, fam, occ, own) for (fam, kw), (occ, own) in stats.items() if occ >= 15 and own / occ < 0.4]
    bad.sort(key=lambda x: -(x[2] - x[3]))
    for kw, fam, occ, own in bad[:30]:
        print(f"  [{fam:14s}] {kw!r:24s} occ={occ:4d} own={own:4d} prec={own/occ*100:4.1f}%")


if __name__ == "__main__":
    main()
