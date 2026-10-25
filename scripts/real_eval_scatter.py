"""真实校准散点图生成（基于公开数据集 job-resume-matching）。

用真实 (简历, JD) 配对 + 数据集自带的 `final_score`，把引擎算出的匹配分
与真实标注做散点对照，并画出最小二乘趋势线，标注 Pearson r。

产物：docs/evidence-scatter.png（深色主题，可直接嵌进网页证据墙）。
数据来自 HuggingFace nonameee12233/job-resume-matching（CC BY，无 PII），
可第三方复现；配对数据落 data/real_eval/calibrate_pairs.json（已 gitignore）。

用法：
  python scripts/real_eval_scatter.py --n 2000 --seed 7
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
PAIRS_OUT = os.path.join(DATA, "calibrate_pairs.json")
IMG_OUT = os.path.join(os.path.dirname(HERE), "docs", "evidence-scatter.png")

PIL_PATH = r"C:/Users/llj12/.workbuddy/binaries/python/envs/default/Lib/site-packages"


def load():
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


def _linreg(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx if sxx else 0.0
    a = my - b * mx
    return a, b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    for p in (JOB_CSV, CV_CSV, MATCH_CSV):
        if not os.path.exists(p):
            sys.stderr.write(f"[missing] 真实评测数据集未找到：{p}\n请先运行 python scripts/fetch_real_eval_data.py\n")
            raise SystemExit(1)

    jobs, cvs, pairs = load()
    random.seed(args.seed)
    sample = random.sample(pairs, min(args.n, len(pairs)))

    my, true = [], []
    for c, j, fs in sample:
        reqs = extract_requirements(jobs[j])[0]
        if not reqs:
            continue
        my.append(score(reqs, match_by_rules(reqs, cvs[c])))
        true.append(fs)

    r = pearson(my, true)
    print(f"样本对: {len(my)}  |  Pearson r (引擎分 ↔ 真实final_score) = {r}")
    print(f"引擎分 均值={sum(my)/len(my):.1f}  真实final_score 均值={sum(true)/len(true):.3f}")

    # 落盘逐对数据（gitignore），便于他人复核
    import json
    with open(PAIRS_OUT, "w", encoding="utf-8") as fh:
        json.dump({"r": r, "n": len(my), "seed": args.seed,
                   "pairs": [{"x": round(x, 1), "y": round(y, 4)} for x, y in zip(my, true)]},
                  fh, ensure_ascii=False)

    # ---- 画图 ----
    sys.path.insert(0, PIL_PATH)
    from PIL import Image, ImageDraw
    W, H = 1200, 630
    pad_l, pad_r, pad_t, pad_b = 90, 40, 70, 70
    img = Image.new("RGB", (W, H), (7, 7, 10))
    d = ImageDraw.Draw(img)
    reg = r"C:/Windows/Fonts/msyh.ttc"
    bold = r"C:/Windows/Fonts/msyhbd.ttc"
    from PIL import ImageFont
    def F(p, s): return ImageFont.truetype(p, s)

    # 标题
    d.text((pad_l, 24), "引擎匹配分 vs 真实匹配度标注（公开数据集 2,000 对）",
           font=F(bold, 28), fill=(244, 246, 251))
    d.text((pad_l, 60), "HuggingFace job-resume-matching · CC BY · 无 PII · 可第三方复现",
           font=F(reg, 17), fill=(160, 167, 184))

    # 坐标系
    x0, y0 = pad_l, H - pad_b
    x1, y1 = W - pad_r, pad_t + 10
    d.rectangle([x0, y1, x1, y0], outline=(255, 255, 255, 70), width=1)
    # 轴标签
    d.text((x0 - 10, y1 + 4), "真实 final_score ↑", font=F(reg, 16), fill=(160, 167, 184))
    d.text((x1 - 120, y0 + 18), "引擎匹配分 →", font=F(reg, 16), fill=(160, 167, 184))
    for gx in range(0, 101, 20):
        px = x0 + (x1 - x0) * gx / 100
        d.line([(px, y0), (px, y0 + 6)], fill=(255, 255, 255, 90), width=1)
        d.text((px - 10, y0 + 8), str(gx), font=F(reg, 13), fill=(130, 138, 156))
    ymin, ymax = 0.40, 0.72
    for gy in (0.4, 0.5, 0.6, 0.7):
        py = y0 + (y1 - y0) * (gy - ymin) / (ymax - ymin)
        d.line([(x0, py), (x0 - 6, py)], fill=(255, 255, 255, 90), width=1)
        d.text((x0 - 64, py - 9), f"{gy:.1f}", font=F(reg, 13), fill=(130, 138, 156))

    # 散点
    def px(x): return x0 + (x1 - x0) * x / 100
    def py(y): return y0 + (y1 - y0) * (y - ymin) / (ymax - ymin)
    for x, y in zip(my, true):
        d.ellipse([px(x) - 2, py(y) - 2, px(x) + 2, py(y) + 2],
                  fill=(34, 211, 238, 120))

    # 趋势线
    a, b = _linreg(my, true)
    xlo, xhi = 0, 100
    d.line([(px(xlo), py(a + b * xlo)), (px(xhi), py(a + b * xhi))],
           fill=(124, 92, 255), width=3)

    # r 标注（截断到 3 位小数，盒子贴右但不溢出）
    bx0, bx1 = x1 - 320, x1 - 24
    d.rounded_rectangle((bx0, y1 + 12, bx1, y1 + 104), radius=12,
                        outline=(124, 92, 255, 170), width=2, fill=(124, 92, 255, 22))
    d.text((bx0 + 18, y1 + 22), f"n = {len(my)}", font=F(bold, 22), fill=(34, 211, 238))
    d.text((bx0 + 18, y1 + 60), f"Pearson r = {r:.3f}", font=F(bold, 24), fill=(244, 246, 251))

    img.save(IMG_OUT)
    print(f"已写出 {IMG_OUT}")


if __name__ == "__main__":
    main()
