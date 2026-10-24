"""真实匹配度校准检验（基于公开数据集 job-resume-matching）。

做法：
  用真实 (简历, JD) 配对 + 数据集自带的 `final_score`（真实匹配标注），
  检验 career-loop 引擎算出的匹配分能否预测真实匹配度（Pearson r）。

为什么做这个：
  原来 calibrate 模块用的是 29 条手写 demo（r=0.694），那是自证数据——
  数据本身按「分高就成功」编的，不能证明引擎真的准。这里改用公开真实
  数据集的真实标注来算 r，结果是可被第三方复现的。

诚实边界：
  - `final_score` 是另一个算法（语义 + 技能 + 类别 + 经历 + 教育多维）算出的
    匹配度，不是「真人是否拿到面试」；它比手写 demo 客观，但仍非真人结果。
  - 引擎当前是规则关键词基线，与多维语义标注只有弱相关属预期；
    真人投递回流数据才是校准的终极目标（见 README）。

用法：
  python scripts/real_eval_calibrate.py --n 2000 --seed 7
"""

from __future__ import annotations
import csv, sys, os, argparse, random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from career_loop.matching.extract import extract_requirements
from career_loop.matching.match import match_by_rules, score
from career_loop.calibrate import pearson

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data", "real_eval")
JOB_CSV = os.path.join(DATA, "job_resume_job.csv")
CV_CSV = os.path.join(DATA, "job_resume_cv.csv")
MATCH_CSV = os.path.join(DATA, "job_resume_matches.csv")


def _ensure_data() -> None:
    missing = [p for p in (JOB_CSV, CV_CSV, MATCH_CSV) if not os.path.exists(p)]
    if not missing:
        return
    sys.stderr.write(
        "\n[missing] 真实评测数据集未找到：\n"
        + "\n".join(f"  - {p}" for p in missing)
        + "\n请先运行下载脚本：\n"
        "  python scripts/fetch_real_eval_data.py\n"
        "（数据来自 HuggingFace nonameee12233/job-resume-matching，约 250MB，不入库）\n"
    )
    raise SystemExit(1)


def load() -> tuple[dict, dict, list]:
    jobs, cvs, pairs = {}, {}, []
    csv.field_size_limit(10 ** 7)
    with open(JOB_CSV, encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            jobs[row["job_id"]] = row.get("job_text") or row.get("job_description") or ""
    with open(CV_CSV, encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            cvs[row["candidate_id"]] = row.get("resume_text") or ""
    with open(MATCH_CSV, encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            c, j = row["candidate_id"], row["job_id"]
            if c in cvs and j in jobs:
                pairs.append((c, j, float(row["final_score"])))
    return jobs, cvs, pairs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    _ensure_data()
    jobs, cvs, pairs = load()
    random.seed(args.seed)
    sample = random.sample(pairs, min(args.n, len(pairs)))

    my, true = [], []
    empty = 0
    for c, j, fs in sample:
        reqs = extract_requirements(jobs[j])[0]
        if not reqs:
            empty += 1
            continue
        my.append(score(reqs, match_by_rules(reqs, cvs[c])))
        true.append(fs)

    r = pearson(my, true)
    print(f"样本对: {len(sample)} (抽出0能力跳过 {empty})")
    print(f"我的匹配分 均值={sum(my)/len(my):.1f}  真实final_score 均值={sum(true)/len(true):.3f}")
    print(f"Pearson r (引擎分 ↔ 真实final_score) = {r}")


if __name__ == "__main__":
    main()
