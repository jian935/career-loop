# -*- coding: utf-8 -*-
"""弱族召回挖掘 v2：极大子串过滤 + 按 miss 转化潜力排序 + 带上下文。

在 v1 基础上：
  1. 极大子串过滤——若长候选 g' 包含短候选 g 且 df 接近（≥80%），
     丢弃碎片 g（'资方案' 被 '融资方案' 吃掉）；
  2. 排序键改为 **miss 转化数**：该词能救回多少条 miss JD，
     直接对应族识别准确率的增益估计；
  3. 每条候选附 2 条真实上下文，供人工判断是不是这一族的东西。
"""

from __future__ import annotations

import argparse
import collections
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from career_loop.matching.schema import DOMAIN_PACKS, detect_domains
from scripts.cn_eval_family import DATA, label_of, zh_ratio

CJK = re.compile(r"[\u4e00-\u9fff]+")
STOP_CHARS = set("的了是在与及或和于对着为就不都没很更还又吗呢吧啊哦嗯你他她它们这那有被把从到上下里外")

WEAK_FAMS = [
    "banking", "finance", "securities", "service", "media", "project_mgmt",
    "consulting", "ai_data", "data_analysis", "film", "product", "game",
    "healthcare", "operations", "ecommerce", "marketing", "ai_solution",
    "it_systems", "legal", "agriculture", "energy", "public_admin", "quality",
    "supply", "logistics",
]


def ngrams(text: str) -> set[str]:
    out: set[str] = set()
    for run in CJK.findall(text.lower()):
        if len(run) < 2:
            continue
        for n in range(2, 7):
            for i in range(len(run) - n + 1):
                g = run[i : i + n]
                if any(c in STOP_CHARS for c in g):
                    continue
                out.add(g)
    return out


def load(seed: int = 42):
    import pyarrow.parquet as pq

    rows = pq.read_table(DATA).to_pylist()
    recs: list[dict] = []
    for r in rows:
        text = r.get("job_description") or ""
        if zh_ratio(text) < 0.15:
            continue
        title = r.get("job_title") or ""
        expected = label_of(title)
        if not expected:
            continue
        recs.append({
            "text": text,
            "low": text.lower(),
            "grams": ngrams(text),
            "expected": expected,
            "title": title,
        })
    rng = random.Random(seed)
    rng.shuffle(recs)
    cut = int(len(recs) * 0.7)
    return recs[:cut], recs[cut:]


def mine(recs, target_fams, min_df=3, min_prec=0.6):
    df_all = collections.Counter()
    df_fam = {f: collections.Counter() for f in target_fams}
    for rec in recs:
        for g in rec["grams"]:
            df_all[g] += 1
            for f in target_fams:
                if f in rec["expected"]:
                    df_fam[f][g] += 1

    out = {}
    for f in target_fams:
        own_kw = {kw.lower() for spec in DOMAIN_PACKS.get(f, {}).values() for kw in spec["kw"]}
        cands = []
        for g, d in df_fam[f].items():
            if d < min_df or g in own_kw:
                continue
            prec = d / df_all[g]
            if prec < min_prec:
                continue
            cands.append({"g": g, "df": d, "tot": df_all[g], "prec": prec})
        # 极大子串过滤：被更长且 df≥80% 的候选吃掉就丢
        by_g = {c["g"]: c for c in cands}
        kept = []
        for c in cands:
            g = c["g"]
            eaten = False
            for other in cands:
                og = other["g"]
                if og != g and g in og and other["df"] >= c["df"] * 0.8 and len(og) > len(g):
                    eaten = True
                    break
            if not eaten:
                kept.append(c)
        # miss 转化潜力
        misses = [r for r in recs if f in r["expected"] and not (set(detect_domains(r["low"])) & r["expected"])]
        for c in kept:
            conv = sum(1 for r in misses if c["g"] in r["low"])
            c["conv"] = conv
        kept = [c for c in kept if c["conv"] >= 2]
        kept.sort(key=lambda c: (-c["conv"], -c["df"]))
        out[f] = (kept, len(misses))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fams", nargs="*", default=None)
    ap.add_argument("--min-df", type=int, default=3)
    ap.add_argument("--min-prec", type=float, default=0.6)
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--ctx", type=int, default=2)
    args = ap.parse_args()

    dev, hold = load()
    print(f"dev={len(dev)}  hold-out={len(hold)}")
    fams = args.fams or WEAK_FAMS
    res = mine(dev, fams, args.min_df, args.min_prec)
    for f in fams:
        kept, n_miss = res[f]
        print(f"\n===== {f}  (dev miss={n_miss}, 候选 {len(kept)}) =====")
        for c in kept[: args.top]:
            print(f"  {c['g']!r:18s} conv={c['conv']:2d} df={c['df']:3d} prec={c['prec']*100:3.0f}%")
            if args.ctx:
                shown = 0
                for r in dev:
                    if f in r["expected"] and c["g"] in r["low"] and shown < args.ctx:
                        idx = r["low"].find(c["g"])
                        s = max(0, idx - 18)
                        print(f"      [{r['title'][:14]}] …{r['low'][s:idx+len(c['g'])+14]}…")
                        shown += 1


if __name__ == "__main__":
    main()
