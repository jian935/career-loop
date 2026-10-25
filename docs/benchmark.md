# Benchmark & reproducible numbers

Everything here can be reproduced from a clean checkout with no API key.

## 1. Rule baseline on the labeled set

```bash
python -m career_loop eval --data data/eval_sample.jsonl --badcases badcases.jsonl
```

Expected:

```
评测集 60 条　规则基线一致率 1.0
逐能力：
  agent              1.0  (4/4)
  coding_tools       1.0  (3/3)
  ...
  16 个能力均为 1.0
无 badcase。
```

| Property | Value |
| --- | --- |
| Cases | 50 (16 capabilities × full / partial / missing, + 8 coverage / boundary cases) |
| Baseline accuracy | 1.0 |
| Badcases | 0 |

**What this number means.** The set is hand-built to cover boundary behavior
(negation, "did a demo only", headings that look like requirements). It now spans
the 14 `TAXONOMY` AI/tech capabilities **plus 2 `GENERAL_DIMS` general capabilities**
(writing, exec_project) and 8 extra coverage/boundary cases, so the regression lock
also guards the general-capability path and a few "missing-vs-partial" edges. Passing it
means the rules still behave as specified. It is a **regression lock**, not a
claim that the engine is 100% accurate on real JDs.

**What would make it drop.** Adding a case that the current rules get wrong is a
normal and welcome change — fix the rule or mark the case, then document the new
number.

### 2.1 Calibration demo (synthetic)

```bash
python -m career_loop calibrate --data data/demo_applications.jsonl
```

| Bucket | n | Positive rate |
| --- | ---: | ---: |
| 0-20 | 0 | 0.0 |
| 20-40 | 4 | 0.0 |
| 40-60 | 7 | 0.143 |
| 60-80 | 10 | 0.5 |
| 80-100 | 8 | 0.875 |

- n = 29, overall positive rate 0.448
- Pearson `r = 0.694`

These are **synthetic demo data** used to show how to read the report. They are
not the author's job-search statistics. With real data, run `calibrate` without
`--data`.

### 2.2 Real-world end-to-end validation (public dataset)

This is the **second pillar** of evaluation: instead of hand-built boundary cases,
we score real (JD, résumé) pairs from a public, labeled corpus and check whether
the engine agrees with the corpus's own human/algorithmic `final_score`.

```bash
python scripts/real_eval_family.py                       # family-identification accuracy on 1,167 real JDs
python scripts/real_eval_calibrate.py --n 2000 --seed 7  # engine score vs real final_score, Pearson r
```

On the public `job-resume-matching` dataset (1,167 real JDs +
9,544 real résumés + 122,560 real match labels, CC BY, no PII):

- **Family-identification accuracy: 93.6%** (1092/1167) — FINANCE 96.6 / HR 99.5 /
  BD 100 / IT 93.3 / SALES 78.4 (known weak spot).
- **Engine score vs. the dataset's `final_score`: Pearson r = 0.193** (2,000 real
  pairs, weak positive, reproducible with `--seed 7`). The engine is a rule baseline;
  a weak-but-positive r is expected next to a multi-dimensional semantic label.

This is the honest counterpart to §1: §1 locks *specified rule behavior* on synthetic
cases; §2.2 checks *agreement with real labels* on real data. See
`docs/real_eval_report.md` and `docs/evidence.md`.

### 2.3 Real Chinese JD extraction (v0.8.13)

The synthetic control set uses toy sentences (JD median **15 characters**).
Real Chinese JDs are messier — template boilerplate, benefit clauses, degree
requirements, multi-item lines packed into one line. So the engine needs to be
tested on **real Chinese text**.

**Annotated set** — `data/eval_real_jd.jsonl`, **45 rows** (39 positive + 6 negative),
all taken verbatim from the public `ngtranai09/china_job` dataset, covering
**20 capabilities**. Accuracy **45/45 = 100%**.

**Hold-out check (the part that carries the argument)** — 10,613 real JD lines that
were **never annotated**, judged by a reproducible rule ("a line that hits exactly
one capability should hit exactly that one"):

| Configuration | Consistency |
|---|---:|
| With context guard | **100.0%** |
| Without context guard | 86.2% |

**The context guard's real contribution: +13.8 percentage points.**
(The hold-out grew from 10,497 to 10,613 lines in v0.8.14 because the extended
vocabulary turned 116 previously zero-hit lines into single-hit lines. The
with/without comparison is always made on the same fixed set, so the conclusion
is unaffected.)
Both numbers come from the hold-out set, not the annotated set — so this is not
overfitting to the samples.

```bash
python scripts/fetch_cn_eval_data.py     # 9.3MB, needs pip install pyarrow
python scripts/eval_real_jd.py
```

What this found and fixed — see `docs/evidence.md` §7.1:
generic words caused **44.1%** precision on `engineering` ("服务质量" ≠ engineering)
and **8.0%** on `adm_archive` ("办理证照" ≠ archive management). After the fix:
**92.7%** and **92.1%**, with recall essentially unchanged.

### 2.4 Job-family identification on real Chinese JDs (v0.8.14–v0.8.17)

Extraction (§2.3) asks "which capability did this line ask for". Family
identification asks a coarser question: "which of the 66 job families is this
JD about". Same public dataset (`ngtranai09/china_job`, 8,674 JDs), labels taken
from `job_title` only (the dataset's own `searched_job_title` is a *search term*
and is far too noisy to use as ground truth — see `docs/evidence.md` §1.2).

**Rule mode** (v0.8.14, after stripping platform boilerplate):

| Family-identification accuracy (any-in) | Rows |
| --- | ---: |
| **86.0%** | 1581 / 1838 |

**Optional LLM backend** (v0.8.17) — same rows, same labels, same input field
(the job title is *not* fed to the model, to avoid leaking the label):

| Mode | any-in | top-1 | avg families / JD |
| --- | ---: | ---: | ---: |
| `rules` — vocabulary only | 86.0% | 56.6% | 4.88 |
| `llm` — model only | 86.5% | 73.5% | 2.20 |
| `auto` — ask the model only when rules return nothing | 87.0% | 57.6% | 4.90 |
| **`blend` — model's first pick first, vocabulary fills in** (default) | **93.4%** | **73.5%** | 5.49 |

The two engines fail on *different* jobs: the vocabulary misses short / heavily
paraphrased JDs, the model misses "consulting / implementation / pre-sales"
families. Their blind spots barely overlap, which is why the union works.
`blend` and `union` produce the same family set, but `blend` ranks the model's
first pick first and therefore scores **16 points higher on top-1**.

**Honest limits.** Across runs the LLM numbers move by ~0.1pt: temperature is
0.2 and the dataset contains 383 duplicate rows, so concurrent sampling can
answer the same text differently (first run 1592, cache-normalised 1590). The
cache keys on model+system+prompt, so a single run is exactly reproducible.
1,838 calls took 517s and cost roughly ¥9; one HTTP failure (0.05%).

```bash
python scripts/fetch_cn_eval_data.py     # 9.3MB, needs pip install pyarrow
python scripts/llm_family_eval.py --modes rules,llm,auto,blend,union
```

The **main pipeline never calls the LLM** for family identification — `match`,
`whatif`, `reflow` and `calibrate` stay rule-only, because the calibration
`r` must be reproducible offline. The LLM backend is opt-in via
`career-loop domains --file jd.md --backend blend`.

## 3. Cross-engine parity (Python vs browser)

The browser demo reimplements the rules in JavaScript. To keep them honest, the
shipped samples must produce identical scores:

| Sample | Python | Browser |
| --- | ---: | ---: |
| AI PM | 58.3% | 58.3% |
| Agent dev | 53.6% | 53.6% |
| Finance | 81.8% | 81.8% |

If you change a rule, change both and update this table.

## 4. CLI audit

```bash
python scripts/audit.py
```

Runs 32 end-to-end cases (happy path + invalid ids, empty JD, too few samples,
empty DB/dir, duplicate collection, invalid status) and exits non-zero on failure.
CI runs it on Linux and Windows.

## 5. Job coverage spot-check (75 roles)

```bash
python scripts/coverage.py                      # rule mode, offline
python scripts/coverage.py --mode llm           # LLM mode (needs API key)
python scripts/coverage.py --only 长尾 --mode both
```

Runs 75 representative JDs in 8 groups, plus a deliberate **long-tail group**
(tea artisan, wedding planner, pet groomer, drone pilot, flight attendant,
courier, nail artist, bartender, LARP host) that has **no built-in family**, so
the fallback rate is measured instead of hidden.

### Rule mode (offline)

| Group | Roles | Recall | Family detected | Fallback share |
| --- | ---: | ---: | ---: | ---: |
| AI | 15 | 100% | 100% | 2% |
| 工商管理 | 15 | 100% | 100% | 4% |
| 研发工程 | 9 | 100% | 100% | 0% |
| 金融专业 | 4 | 100% | 100% | 0% |
| 传媒文娱 | 5 | 100% | 100% | 14% |
| 服务零售 | 4 | 100% | 100% | 0% |
| 制造能源农林 | 8 | 100% | 100% | 14% |
| 科研公共 | 5 | 100% | 100% | 0% |
| **长尾（未建词表）** | 9 | 100% | n/a | **46%** |

- **66 roles with a built-in family**: recall 100%, family detection 100%,
  fallback share 3% — i.e. the vocabulary actually carries the load.
- **9 long-tail roles**: recall 100% but fallback share 46%. Recall stays high
  because the fallback keeps the original line verbatim; that is *not* the same
  as understanding it. Long-tail roles are where the LLM mode matters.

Vocabulary size: **66 job families / 171 family-level capabilities**, plus 14 AI
dimensions and 9 general dimensions (194 total).

### LLM mode vs rule mode (same probe set)

| Group | Rule fallback | LLM fallback | Note |
| --- | ---: | ---: | --- |
| AI | 2% | 21% | LLM prefers its own naming even when a canonical key exists |
| 研发工程 | 0% | 7% | |
| 长尾 | 46% | 91% | LLM invents *semantic* items, not verbatim copies |

LLM recall on the long-tail group is 97%. The items it creates are named
capabilities, e.g. 茶艺师 → `tea_brewing`(茶艺冲泡) / `tea_table_design`(茶席设计)
/ `tea_culture`(茶文化传播); 无人机飞手 → `drone_license`(无人机执照) /
`drone_fc_gimbal`(飞控与云台操作).

**Trade-off, stated plainly:** LLM mode covers more, but it names capabilities
ad hoc, so the same skill can appear under different keys across JDs — which
makes the aggregate `demand` statistics noisier. Rule mode is worse at long-tail
coverage and better at comparability. That is why both modes ship.

Recall = expected key terms whose requirement line was captured, either as a
canonical capability or as a self-created requirement. This is a **spot check**:
it shows the architecture generalizes, not that every role on the market is
perfectly covered.

## 6. Occupation-classification alignment

```bash
python -c "from career_loop.matching.taxonomy_cn import render_coverage; print(render_coverage())"
```

Maps job families onto the 8 top-level classes of China's Occupation
Classification Dictionary so coverage can be audited against an external
skeleton:

| Class | Mid-classes collected | Mapped | Status |
| --- | ---: | ---: | --- |
| 1 单位负责人 | 3 | 3 | complete |
| 2 专业技术人员 | 10 | 10 | complete |
| 3 办事人员 | 4 | 4 | complete |
| 4 社会生产服务和生活服务人员 | 9 | 9 | complete |
| 5 农林牧渔生产及辅助人员 | 4 | 4 | complete |
| 6 生产制造及有关人员 | 9 | 9 | complete |
| 7 军人 | 0 | 0 | out of scope |
| 8 不便分类的其他从业人员 | 0 | 0 | out of scope |

**Honest limit:** 39 mid-classes are collected here; the Dictionary has 79. So
this shows 100% of *what we listed*, i.e. ~49% of the Dictionary's mid-classes.
The mapping is heuristic keyword matching, not official data.

## 7. What we deliberately do not report

- No "end-to-end accuracy on *private* job-search outcomes" claim: we do **not**
  publish the author's own application results (PII, gitignored). What we validate
  on real data is *agreement with a public labeled corpus* (§2.2) — a different,
  honest claim from "this score predicts your offer."
- No ranking against career-ops or Resume-Matcher: they solve a different problem
  (full application pipeline / resume tailoring). Comparing scores across engines
  would require a shared labeled outcome dataset, which does not exist yet.

If you have a labeled dataset of (JD, profile, outcome), open an issue — a shared
benchmark is the most useful contribution this project could receive.

What building that benchmark actually requires (data volume, annotation rules,
statistical power, legal constraints) is documented in
[benchmark-plan.md](benchmark-plan.md).
