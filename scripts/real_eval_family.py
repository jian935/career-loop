"""真实 JD 族识别准确率检验（基于公开数据集 job-resume-matching）。

数据来源：HuggingFace `nonameee12233/job-resume-matching`（CC BY 4.0 类许可），
1,167 条真实岗位 JD，每条带公开 `category` 标注
（FINANCE / HR / SALES / BUSINESS-DEVELOPMENT / INFORMATION-TECHNOLOGY）。

做法：把每条真实 JD 文本喂给 detect_domains()，看其预测族是否落在
「该 category 对应的 career-loop 岗位族集合」内。这是对"覆盖面/族识别"
的客观、可复现检验——不是手写样例，也不是合成数据。

诚实边界：本检验只覆盖英文 JD + 5 大公开类别（数据集本身只有这些类）；
中文 JD、其余岗位族的检验待用户真实回流数据补充。
"""

from __future__ import annotations
import csv, sys, collections, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from career_loop.matching.schema import detect_domains

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "real_eval", "job_resume_job.csv")

# 公开 category → career-loop 岗位族集合（启发式映射，用于检验预测是否"落在正确族簇"）
EXPECTED = {
    "FINANCE": {"finance"},
    "HR": {"hr"},
    "SALES": {"sales"},
    "BUSINESS-DEVELOPMENT": {"sales", "marketing", "consulting"},
    "INFORMATION-TECHNOLOGY": {
        "it_systems", "devops", "backend", "frontend", "qa", "security", "embedded",
        "ai_nlp", "ai_cv", "ai_recsys", "ai_mlops", "ai_data", "ai_speech",
        "ai_multimodal", "ai_robotics", "ai_testing", "ai_compliance",
        "ai_solution", "ai_ops",
    },
}

csv.field_size_limit(10 ** 7)


def _ensure_data() -> None:
    if os.path.exists(DATA):
        return
    sys.stderr.write(
        f"\n[missing] {DATA}\n"
        "真实评测数据集未找到。请先运行下载脚本：\n"
        "  python scripts/fetch_real_eval_data.py\n"
        "（数据来自 HuggingFace nonameee12233/job-resume-matching，约 250MB，不入库）\n"
    )
    raise SystemExit(1)


def main() -> None:
    _ensure_data()
    total = hit = 0
    per = collections.Counter()
    per_hit = collections.Counter()
    pred_counter = collections.Counter()
    misses = collections.defaultdict(collections.Counter)
    with open(DATA, encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            cat = row["category"]
            text = row.get("job_text") or row.get("job_description") or ""
            preds = detect_domains(text)
            per[cat] += 1
            if preds:
                pred_counter[preds[0]] += 1
            if any(p in EXPECTED[cat] for p in preds):
                hit += 1
                per_hit[cat] += 1
            else:
                misses[cat][tuple(preds[:3]) or ("<none>",)] += 1
    total = sum(per.values())
    print(f"真实 JD 总数: {total}")
    print(f"总体族识别准确率: {hit / total:.3f}  ({hit}/{total})")
    print("\n分类别准确率:")
    for cat in EXPECTED:
        c = per[cat]
        print(f"  {cat:24s} {per_hit[cat]:4d}/{c:4d} = {per_hit[cat] / c:.3f}")
    print("\nTop 预测族（族名: 次数）:")
    for name, c in pred_counter.most_common(15):
        print(f"  {name:20s} {c}")
    print("\n各分类别的主要误判（预测 top3 -> 次数）:")
    for cat in EXPECTED:
        print(f"  [{cat}]")
        for pred, c in misses[cat].most_common(4):
            print(f"    {pred} -> {c}")


if __name__ == "__main__":
    main()
