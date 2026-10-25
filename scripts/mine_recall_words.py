# -*- coding: utf-8 -*-
"""弱族召回挖掘 v3：样板剥离 + 矛盾记录过滤 + 极大子串过滤 + 按 miss 转化潜力排序。

v3 在 v2 基础上（W8，攻 service / project_mgmt 时改）：
  1. 挖掘前先剥 JD 样板（v0.8.14 起 detect_domains 就剥了，
     但这里 n-gram 一直用的是原文——「职位来源于智联招聘」会被挖成候选，
     是个与引擎口径不一致的既有缺陷，一并修掉）；
  3. **按正文去重后再统计 df**（W8 新发现）：数据集对同一 JD 有多次抓取，
     不去重时 df 和精确率全被重复记录扭曲——service 的 dev miss 有 4 条是
     同一份「播音配音」JD，挖出的候选全是它的子串碎片、精确率 100% 纯属
     df_fam=df_all=4 的假象。去重后这些候选因 df<3 自动消失。
     注意：去重只影响挖掘视角，评测本身仍按记录算（重复记录是数据集事实）。
  4. 矛盾记录过滤：标题标签族在正文零命中、而另一族 ≥3 词的记录
     （标题写「客服」正文是销售话术那种），挖词时排除、单独计数。
     这些记录的词会把候选池搅浑（服务族 32 条 miss 里 14 条是这类）。
     注意：过滤只影响挖掘视角，不改评测口径（对外主数字仍用标题标签）；
"""

from __future__ import annotations

import argparse
import collections
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from career_loop.matching.boilerplate import strip_boilerplate
from career_loop.matching.schema import DOMAIN_PACKS, detect_domains
from scripts.cn_eval_family import DATA, label_of, zh_ratio

CJK = re.compile(r"[\u4e00-\u9fff]+")
STOP_CHARS = set("的了是在与及或和于对着为就不都没很更还又吗呢吧啊哦嗯你他她它们这那有被把从到上下里外")
CONTRA_MIN = 3  # 正文指向别族的词数阈值：≥3 词算「标题-正文矛盾」

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


def fam_scores(low: str) -> dict[str, int]:
    """各词表族在文本里的命中词数（与 detect_domains 同口径，未含 ai 父族）。"""
    s: dict[str, int] = {}
    for name, packs in DOMAIN_PACKS.items():
        c = 0
        for spec in packs.values():
            for kw in spec["kw"]:
                if kw in low:
                    c += 1
        if c:
            s[name] = c
    return s


def load(seed: int = 42):
    import hashlib

    import pyarrow.parquet as pq

    rows = pq.read_table(DATA).to_pylist()
    recs: list[dict] = []
    n_contra = 0
    seen: set[str] = set()
    n_dup = 0
    for r in rows:
        text = r.get("job_description") or ""
        if zh_ratio(text) < 0.15:
            continue
        title = r.get("job_title") or ""
        expected = label_of(title)
        if not expected:
            continue
        low = strip_boilerplate(text).lower()
        # 去重键 = 剥样板后正文的 hash（同一 JD 的多次抓取只留一条）
        h = hashlib.md5(low.encode("utf-8")).hexdigest()
        if h in seen:
            n_dup += 1
            continue
        seen.add(h)
        sc = fam_scores(low)
        # 矛盾判定：期望族零命中 且 另一族 ≥CONTRA_MIN 词
        contra = not any(f in sc for f in expected) and any(
            c >= CONTRA_MIN for f, c in sc.items() if f not in expected
        )
        if contra:
            n_contra += 1
        recs.append({
            "text": text,
            "low": low,
            "grams": ngrams(low),
            "expected": expected,
            "title": title,
            "contra": contra,
        })
    rng = random.Random(seed)
    rng.shuffle(recs)
    cut = int(len(recs) * 0.7)
    return recs[:cut], recs[cut:], n_contra, n_dup


def mine(recs, target_fams, min_df=3, min_prec=0.6):
    # 矛盾记录（标题-正文矛盾）不参与 df 统计：它们的正文不是目标族的典型表达
    clean = [r for r in recs if not r["contra"]]
    df_all = collections.Counter()
    df_fam = {f: collections.Counter() for f in target_fams}
    for rec in clean:
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
        # miss 转化潜力（同样只算非矛盾记录）
        misses = [r for r in clean if f in r["expected"] and not (set(detect_domains(r["low"])) & r["expected"])]
        n_contra_miss = sum(
            1 for r in recs
            if r["contra"] and f in r["expected"] and not (set(detect_domains(r["low"])) & r["expected"])
        )
        for c in kept:
            conv = sum(1 for r in misses if c["g"] in r["low"])
            c["conv"] = conv
        kept = [c for c in kept if c["conv"] >= 2]
        kept.sort(key=lambda c: (-c["conv"], -c["df"]))
        out[f] = (kept, len(misses), n_contra_miss)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fams", nargs="*", default=None)
    ap.add_argument("--min-df", type=int, default=3)
    ap.add_argument("--min-prec", type=float, default=0.6)
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--ctx", type=int, default=2)
    args = ap.parse_args()

    dev, hold, n_contra, n_dup = load()
    print(f"dev={len(dev)}  hold-out={len(hold)}  (按正文去重剔除重复抓取 {n_dup} 条；矛盾记录 {n_contra} 条不参与挖掘)")
    fams = args.fams or WEAK_FAMS
    res = mine(dev, fams, args.min_df, args.min_prec)
    for f in fams:
        kept, n_miss, n_contra_miss = res[f]
        contra_note = f"，另 {n_contra_miss} 条为标题-正文矛盾（不挖）" if n_contra_miss else ""
        print(f"\n===== {f}  (dev miss={n_miss}{contra_note}, 候选 {len(kept)}) =====")
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
