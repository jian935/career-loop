# Benchmark & reproducible numbers

Everything here can be reproduced from a clean checkout with no API key.

## 1. Rule baseline on the labeled set

```bash
python -m career_loop eval --data data/eval_sample.jsonl --badcases badcases.jsonl
```

Expected:

```
评测集 42 条　规则基线一致率 1.0
逐能力：
  agent              1.0  (3/3)
  coding_tools       1.0  (3/3)
  ...
  14 个能力均为 1.0
无 badcase。
```

| Property | Value |
| --- | --- |
| Cases | 42 (14 capabilities × full / partial / missing) |
| Baseline accuracy | 1.0 |
| Badcases | 0 |

**What this number means.** The set is hand-built to cover boundary behavior
(negation, "did a demo only", headings that look like requirements). Passing it
means the rules still behave as specified. It is a **regression lock**, not a
claim that the engine is 100% accurate on real JDs.

**What would make it drop.** Adding a case that the current rules get wrong is a
normal and welcome change — fix the rule or mark the case, then document the new
number.

## 2. Calibration demo (synthetic)

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

Runs 28 end-to-end cases (happy path + invalid ids, empty JD, too few samples,
empty DB/dir, duplicate collection, invalid status) and exits non-zero on failure.
CI runs it on Linux and Windows.

## 4. Job coverage spot-check (30 roles)

```bash
python scripts/coverage.py
```

Runs 30 representative JDs and reports, per role: detected job family, number of
requirements extracted, how many came from the vocabulary vs. the custom
fallback, and whether the expected key terms were captured.

| Group | Roles | Extraction recall | Family detected |
| --- | ---: | ---: | ---: |
| AI (15) | PM, Agent, RAG, Prompt, NLP, CV, recsys, MLOps, solution, ops, speech, multimodal, robotics, data, testing | 100% | 100% |
| Business admin (15) | marketing, sales, accounting, FP&A, audit, HR, admin, supply chain, ecommerce, tourism/hotel, IT systems, project mgmt, trade, property, construction | 100% | 100% |

Recall = expected key terms whose requirement line was captured, either as a
canonical capability or as a custom requirement. This is a **spot check**: it
shows the architecture generalizes, not that every role on the market is
perfectly covered. Long-tail roles rely on the custom fallback or the LLM mode.

## 5. What we deliberately do not report

- No "accuracy on real job postings" claim: we have no public, labeled, real-world
  corpus.
- No ranking against career-ops or Resume-Matcher: they solve a different problem
  (full application pipeline / resume tailoring). Comparing scores across engines
  would require a shared labeled outcome dataset, which does not exist yet.

If you have a labeled dataset of (JD, profile, outcome), open an issue — a shared
benchmark is the most useful contribution this project could receive.

What building that benchmark actually requires (data volume, annotation rules,
statistical power, legal constraints) is documented in
[benchmark-plan.md](benchmark-plan.md).
