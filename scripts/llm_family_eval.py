# -*- coding: utf-8 -*-
"""LLM 族识别后端实测（公开中文 JD 集，与 cn_eval_family 同一标签口径）。

## 为什么需要它
规则基线在短 JD 上召回不足（中文公开集 86.0%，service 族约 52%），
W9 确认纯词表路线补不动。本脚本把「规则 / LLM / auto 混合 / 并集」
四种模式放在**同一批数据、同一套标签、同一输入字段**上对比，用真实调用说话。

## 口径（与 cn_eval_family.py 逐字对齐，防止自欺）
- 标签：`job_title` 经 TITLE_TO_FAMILY 判定，判不出的不计入（直接复用其函数）；
- 输入：`job_description` 一个字段，**岗位名绝不喂给模型**——标签来自岗位名，
  喂了就是泄露；
- 预处理：与规则同样剥平台样板（boilerplate），LLM 看到的文本和规则一致；
- 指标：any-in（预测族集合与期望族集合有交集即对），与对外口径一致。

## 输出
- 四种模式的总体准确率、分族表（n≥5）、service/project_mgmt 专项；
- 规则与 LLM 的分歧统计（规则漏 LLM 中 / LLM 漏规则中 / 都漏）+ 样例；
- LLM 调用统计：实调次数、缓存命中、失败数、墙钟时间；
- 原始预测落盘 data/llm_eval/preds.jsonl（gitignore），可复算、可复查。

复现：先 `python scripts/fetch_cn_eval_data.py` 下载数据集，
配置 OPENAI_API_KEY（.env 或环境变量），再跑本脚本。
LLM 结果有缓存（~/.career_loop/llm_cache），重跑不花钱、结果不变。
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # 让 cn_eval_family 可被 import

from career_loop.cli import _load_dotenv
from career_loop.matching.family_llm import detect_family_llm
from career_loop.matching.llm import LLM, LLMError
from career_loop.matching.schema import detect_domains

from cn_eval_family import DATA, label_of, zh_ratio  # noqa: E402 同一标签口径

_load_dotenv()  # 与 CLI 一致：从 .env / 环境变量读 Key

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "llm_eval")


def load_records() -> list[dict]:
    import pyarrow.parquet as pq

    rows = pq.read_table(DATA).to_pylist()
    recs = []
    for r in rows:
        text = r.get("job_description") or ""
        if zh_ratio(text) < 0.15:
            continue
        title = r.get("job_title") or ""
        expected = label_of(title)
        if not expected:
            continue
        recs.append({"title": title, "text": text, "expected": sorted(expected)})
    return recs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8, help="LLM 并发数")
    ap.add_argument("--limit", type=int, default=None, help="只取前 N 条（调试用）")
    ap.add_argument("--modes", default="rules,llm,auto,blend",
                    help="要评估的模式（rules 不调 LLM，可单独跑做基线核对；"
                         "union 为 blend 的对照口径，默认不跑）")
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "preds.jsonl"),
                    help="原始预测落盘路径")
    ap.add_argument("--resume", action="store_true",
                    help="跳过已写过预测的记录（按 title+正文 MD5）")
    args = ap.parse_args()

    if not os.path.exists(DATA):
        print("\n[missing] 未找到中文 JD 数据集。请先运行：\n"
              "  python scripts/fetch_cn_eval_data.py\n", file=sys.stderr)
        raise SystemExit(1)

    recs = load_records()
    if args.limit:
        recs = recs[: args.limit]
    print(f"可检验样本：{len(recs)} 条（与 cn_eval_family 同口径）")

    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    need_llm = any(m in ("llm", "auto", "union") for m in modes)

    llm_preds: list[list[str]] | None = None
    if need_llm:
        llm = LLM()
        if not llm.available:
            print("[missing] LLM 未配置：设置 OPENAI_API_KEY（.env 或环境变量）",
                  file=sys.stderr)
            raise SystemExit(1)

        done: dict[str, list[str]] = {}
        if args.resume and os.path.exists(args.out):
            for line in open(args.out, encoding="utf-8"):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # 只认 list（rules-only 跑出来的行 llm 是 null，不能当预测用）
                if not isinstance(row.get("llm"), list) or "key" not in row:
                    continue
                done[row["key"]] = row["llm"]
            print(f"断点续跑：已载入 {len(done)} 条历史 LLM 预测")

        def key_of(rec):
            return hashlib.md5((rec["title"] + "\0" + rec["text"]).encode()).hexdigest()

        def work(rec):
            k = key_of(rec)
            if k in done:
                return done[k]
            try:
                return detect_family_llm(rec["text"], llm)
            except (LLMError, KeyError, ValueError):
                return []

        t0 = time.time()
        results: list[list[str] | None] = [None] * len(recs)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {i: pool.submit(work, rec) for i, rec in enumerate(recs)}
            for n, (i, fut) in enumerate(futures.items(), 1):
                results[i] = fut.result()
                if n % 200 == 0:
                    s = llm.stats
                    print(f"  进度 {n}/{len(recs)}（HTTP 实调 {s['http_calls']}，"
                          f"缓存命中 {s['cache_hits']}，失败 {s['failures']}，"
                          f"{time.time() - t0:.0f}s）", file=sys.stderr)
        llm_preds = results
        s = llm.stats
        print(f"LLM 完成：HTTP 实调 {s['http_calls']} 次，缓存命中 {s['cache_hits']} 条，"
              f"失败 {s['failures']} 条，墙钟 {time.time() - t0:.0f}s，模型 {llm.model}")

    # ---- 汇总 ----
    n = len(recs)
    ok: dict[str, int] = collections.Counter()
    top1: dict[str, int] = collections.Counter()
    fam_sum: dict[str, int] = collections.Counter()
    by_fam: dict[str, collections.Counter] = {m: collections.Counter() for m in modes}
    by_fam_tot: collections.Counter = collections.Counter()
    rules_miss_llm_hit = llm_miss_rules_hit = both_miss = 0
    disagree_examples: list[str] = []

    rows_out = []
    for i, rec in enumerate(recs):
        expected = set(rec["expected"])
        rules = detect_domains(rec["text"])
        lp = llm_preds[i] if llm_preds is not None else None
        ll = lp or []

        def build(mode: str) -> list[str]:
            if mode == "rules":
                return rules
            if mode == "llm":
                return ll
            if mode == "auto":
                return rules or ll
            if mode == "blend":       # LLM 首选优先 + 规则补充
                return ll + [f for f in rules if f not in ll]
            if mode == "union":       # 规则优先 + LLM 补充（blend 的对照，被 blend 占优）
                return rules + [f for f in ll if f not in rules]
            raise ValueError(f"未知模式 {mode}")

        preds_by_mode = {m: build(m) for m in modes}
        for m in modes:
            preds = preds_by_mode[m]
            if any(p in expected for p in preds):
                ok[m] += 1
                for fam in expected:
                    by_fam[m][fam] += 1
            if preds and preds[0] in expected:
                top1[m] += 1
            fam_sum[m] += len(preds)
        for fam in expected:
            by_fam_tot[fam] += 1
        if lp is not None:
            r_ok = any(p in expected for p in rules)
            l_ok = any(p in expected for p in lp)
            if not r_ok and l_ok:
                rules_miss_llm_hit += 1
                if len(disagree_examples) < 6:
                    disagree_examples.append(
                        f"  [规则漏/LLM 中] {rec['title']} → LLM={lp} 规则={rules}")
            elif r_ok and not l_ok:
                llm_miss_rules_hit += 1
                if len(disagree_examples) < 6:
                    disagree_examples.append(
                        f"  [LLM 漏/规则中] {rec['title']} → 规则={rules} LLM={lp}")
            elif not r_ok and not l_ok:
                both_miss += 1
        rows_out.append({"key": hashlib.md5((rec["title"] + "\0" + rec["text"]).encode()).hexdigest(),
                         "title": rec["title"], "expected": rec["expected"],
                         "rules": rules, "llm": lp, "text": rec["text"][:200]})

    print(f"\n==== 总体族识别准确率（any-in，n={n}）====")
    base = None
    for m in modes:
        acc = ok[m] / n
        if base is None:
            base = acc
        print(f"  {m:6s} {ok[m]:5d}/{n} = {acc:.3f}   （较首个模式 {acc - base:+.3f}）")

    print("\n==== 代价侧：top-1 准确率与平均输出族数 ====")
    print("  （union 的 any-in 增益是有成本的：并集策略靠多输出换召回）")
    for m in modes:
        print(f"  {m:6s} top-1 {top1[m] / n:.3f}   平均输出 {fam_sum[m] / n:.2f} 个族/JD")

    print("\n==== 分族准确率（期望族样本 ≥5）====")
    header = "  " + "family".ljust(16) + "n".rjust(5) + "".join(m.rjust(10) for m in modes)
    print(header)
    for fam, c in sorted(by_fam_tot.items(), key=lambda kv: -kv[1]):
        if c < 5:
            continue
        line = f"  {fam:16s}{c:5d}"
        for m in modes:
            line += f"{by_fam[m][fam] / c:10.3f}"
        print(line)

    if llm_preds is not None:
        print("\n==== 规则 vs LLM 分歧 ====")
        print(f"  规则漏、LLM 中：{rules_miss_llm_hit}")
        print(f"  LLM 漏、规则中：{llm_miss_rules_hit}")
        print(f"  都漏：{both_miss}")
        for e in disagree_examples:
            print(e)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for row in rows_out:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\n原始预测已写入 {args.out}")


if __name__ == "__main__":
    main()
