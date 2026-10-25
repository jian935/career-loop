# -*- coding: utf-8 -*-
"""dev / hold-out 拆分测量：证明词表补充的增益不是过拟合。

用法（改动机前后各跑一次，对比 dev 与 hold-out 两列）：
    python scripts/measure_split.py
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from career_loop.matching.schema import detect_domains
from scripts.cn_eval_family import DATA, label_of, zh_ratio


def load(seed: int = 42):
    import pyarrow.parquet as pq

    rows = pq.read_table(DATA).to_pylist()
    recs: list[tuple[str, set[str]]] = []
    for r in rows:
        text = r.get("job_description") or ""
        if zh_ratio(text) < 0.15:
            continue
        exp = label_of(r.get("job_title") or "")
        if not exp:
            continue
        recs.append((text, exp))
    rng = random.Random(seed)
    rng.shuffle(recs)
    cut = int(len(recs) * 0.7)
    return recs[:cut], recs[cut:]


def acc(recs) -> tuple[int, int]:
    hit = sum(1 for text, exp in recs if set(detect_domains(text)) & exp)
    return hit, len(recs)


def main() -> None:
    dev, hold = load()
    dh, dt = acc(dev)
    hh, ht = acc(hold)
    print(f"dev     : {dh}/{dt} = {dh/dt:.4f}")
    print(f"hold-out: {hh}/{ht} = {hh/ht:.4f}")
    print(f"合并    : {dh+hh}/{dt+ht} = {(dh+hh)/(dt+ht):.4f}")


if __name__ == "__main__":
    main()
