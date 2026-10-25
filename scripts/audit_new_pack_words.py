# -*- coding: utf-8 -*-
"""新词审计：一个词够不够格进词表，用真实中文 JD 说了算。

用法：
    python scripts/audit_new_pack_words.py                 # 审全部族
    python scripts/audit_new_pack_words.py --fam maritime  # 只审一个族

## 为什么要有这个脚本
给词表加词最容易犯的两个错，本仓库都犯过：

**1. 用「正文含该词」圈定目标集，再回过头统计该词的判别力。**
那是自证：目标集既然由这个词定义，它在目标集里的占比必然是 100%。
v0.8.26 第一版就掉进这个坑——挖出来的候选词精确率清一色 1.00，
数字漂亮但毫无意义。**目标集必须由与正文无关的东西定义**，本脚本用岗位名。

**2. 收裸名词。**
「船舶」「矿山」「环保」这种词匹配的是"这段文字里出现了这个字"，
不是"这个人具备这项能力"。实测代价：真实 JD 里
「任职要求：船舶制造类相关专业」被判成具备船舶操作能力。
所以本脚本对每个词除了报命中数，还报**岗位名确实属于该职业的比例**，
低于 `--min-title-hit`（默认 50%）的词建议删除；唯一例外是极低频的
领域术语（命中 <5 条时样本太小不判）。

数据：HuggingFace `ngtranai09/china_job`（8,674 条真实中文 JD），
按正文去重后再统计（同一 JD 被多次抓取会伪造比例）。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from career_loop.matching.boilerplate import strip_boilerplate          # noqa: E402
from career_loop.matching.schema import DOMAIN_PACKS                    # noqa: E402
from scripts.cn_eval_family import DATA, zh_ratio                       # noqa: E402

# 岗位名命中模式：只认标题，与正文无关 —— 这是打破自证循环的关键
TITLE_PATTERNS: dict[str, str] = {
    "maritime": r"船舶|轮机|船务|航运|海运|海事|船体|造船",
    "mining": r"采矿|矿山|地质|选矿|钻探|勘探|矿产",
    "environment": r"环保|环安|ehs|安环|水处理|环境|双碳|碳管理|安全工程师",
    "logistics": r"物流|仓储|关务|货代|配送",
    "energy": r"化工|石油|燃气|电力|储能|光伏",
}


def load_corpus() -> list[dict]:
    import pyarrow.parquet as pq

    rows = pq.read_table(DATA).to_pylist()
    out: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        text = r.get("job_description") or ""
        if zh_ratio(text) < 0.15:
            continue
        low = strip_boilerplate(text).lower()
        h = hashlib.md5(low.encode("utf-8")).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        out.append({"low": low, "title": (r.get("job_title") or "").strip()})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fam", default=None, help="只审这一个族")
    ap.add_argument("--min-title-hit", type=float, default=0.5)
    args = ap.parse_args()

    corpus = load_corpus()
    print(f"去重后真实中文 JD：{len(corpus)} 条")
    print(f"入选线：命中数 ≥5 时，岗位名属于该职业的比例需 ≥{args.min_title_hit:.0%}\n")

    fams = [args.fam] if args.fam else sorted(DOMAIN_PACKS)
    weak: list[tuple[str, str, int, float]] = []
    for fam in fams:
        if fam not in DOMAIN_PACKS:
            print(f"[warn] 没有这个族：{fam}")
            continue
        pat = TITLE_PATTERNS.get(fam)
        rx = re.compile(pat, re.I) if pat else None
        print(f"===== {fam}{'（无岗位名模式，只报命中数）' if rx is None else ''}")
        for key, spec in DOMAIN_PACKS[fam].items():
            for kw in spec["kw"]:
                lw = kw.strip().lower()
                hits = [i for i, r in enumerate(corpus)
                        if lw in r["low"] or lw in r["title"].lower()]
                if not hits:
                    print(f"  ·  {kw:<14} 全库 0 条（这个数据集里没有）")
                    continue
                if rx is None or len(hits) < 5:
                    print(f"  ·  {kw:<14} 全库 {len(hits)} 条（样本太小 / 无标题模式，不判）")
                    continue
                in_t = sum(1 for i in hits if rx.search(corpus[i]["title"]))
                frac = in_t / len(hits)
                mark = "✓" if frac >= args.min_title_hit else "✗"
                print(f"  {mark} {kw:<14} 全库 {len(hits):<4} 岗位名同职业 {in_t:<4} ({frac:.0%})")
                if frac < args.min_title_hit:
                    weak.append((fam, kw, len(hits), frac))
        print()

    if weak:
        print("建议删除（低于入选线）：")
        for fam, kw, n, frac in weak:
            print(f"  - {fam}: 「{kw}」 命中 {n} 条，岗位名同职业仅 {frac:.0%}")
    else:
        print("所有被判定的词都在入选线之上 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
