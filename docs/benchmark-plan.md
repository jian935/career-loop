# Benchmark plan: from 30-role spot check to a public benchmark

This page answers one question: **what does it actually take to prove coverage
and calibration with public, real data?**

## 0. Two benchmarks, two bars

| Benchmark | Question | Needs real outcomes? | Difficulty |
| --- | --- | --- | --- |
| **A. Coverage / extraction** | Can the engine parse requirements across all job families? | No | Medium (labeling labor) |
| **B. Calibration** | Does the score predict real replies? | Yes | High (privacy + sample size) |

"Full coverage" only needs **A**. "Is it accurate" needs **B**. Do not block A on B.

## 1. Data requirements

### A. Coverage benchmark

| Item | Minimum (v0) | Target (v1) |
| --- | ---: | ---: |
| Job descriptions | 100 | 300-500 |
| Job families covered | 20 | 30+ |
| Profiles (for matching) | 100 synthetic | 300 synthetic + 50 consented real |
| Annotators | 1 (author) + spot review | 2 independent + adjudication |

**Where to get JDs (compliant):**

- Public ATS job boards with open JSON: Greenhouse, Lever, Ashby, Workable.
  Company career pages, respecting `robots.txt`.
- Public datasets with a permissive license (check each one).
- Your own collected JDs, redacted.

**Do not** scrape LinkedIn / Boss / 猎聘: it violates their terms and is brittle.

### B. Calibration benchmark

| Item | Minimum | Useful |
| --- | ---: | ---: |
| Real applications with outcomes | 30 | 100-200 |
| Outcome labels | replied / interview / offer / rejected | + timestamps, role family |

Only the applicant can produce this. It must be consented and de-identified.

## 2. Annotation

**Unit of work:**

1. For each JD line: does it state a requirement? Which capability key (or
   `custom`)? What weight (1/2/3)?
2. For each (requirement, profile) pair: `full` / `partial` / `missing`, plus the
   verbatim evidence span.

**Decision rules** (same as `docs/methodology.md`): `full` needs concrete evidence
of doing it; `partial` means mentioned with weak/hedged evidence; `missing` means
no evidence or an explicit negative.

**Quality control:**

- Two annotators on at least 20% of the set.
- Report **Cohen's kappa** per capability; target **>= 0.70**.
- Adjudicate disagreements; keep the adjudicated label and the raw pair.
- Publish disagreement examples in the data card.

## 3. Size and statistics

- **Correlation:** to detect `r = 0.4` with 80% power at alpha = 0.05 you need
  about **47** paired outcomes; use **>= 100** for stability.
- **Per-capability accuracy:** a +/-10% confidence interval needs roughly **100**
  cases per capability. With 14 core capabilities that is **300-500 pairs**.
- Always report **bootstrap 95% CI**, not a single point estimate.
- Stratify by job family: an aggregate `r` can hide a family where the score fails.

## 4. Legal and privacy

| Concern | Rule |
| --- | --- |
| JD copyright | Store `source_url` + `sha256` + at most a 200-char excerpt; do not redistribute full text. |
| Personal data | Profiles are synthetic, or real with written consent and PII removed (name, phone, email, employer names). |
| Scraping | Only public ATS endpoints / pages that allow it; respect `robots.txt`. |
| License | Code MIT; **annotations CC BY 4.0**; JD excerpts under their source terms. |
| Removal | Provide a takedown path; honor requests within 7 days. |

## 5. Format (JSONL, one case per line)

```json
{
  "id": "ai-pm-0001",
  "language": "zh",
  "job_family": "ai",
  "source_url": "https://boards.greenhouse.io/...",
  "source_sha256": "…",
  "jd_excerpt": "≤200 chars",
  "profile_id": "synth-0042",
  "profile": "…",
  "requirements": [
    {"line": "熟悉大模型原理与边界", "key": "llm_basics", "weight": 2,
     "label": {"status": "full", "evidence": "…", "annotator": "a1"}}
  ],
  "adjudicated": true
}
```

## 6. Metrics to publish

- Extraction recall (requirement lines captured / requirement-like lines).
- Per-capability accuracy and macro-F1.
- Job-family detection accuracy.
- Annotation agreement (Cohen's kappa).
- Calibration `r` with bootstrap CI and `n`, plus per-family breakdown.

## 7. Milestones

| Version | Scope | Effort |
| --- | --- | --- |
| v0 | 100 JDs, 100 synthetic pairs, 1 annotator, no outcomes | ~1 week |
| v1 | 300 pairs, 2 annotators, kappa, data card, public repo | ~3-4 weeks |
| v2 | 100+ real outcomes, calibration with CI, per-family | ~3 months of applying |

## 8. Division of labor

**Can be done without your private data (v0 kit is in `benchmark/`):**

- JSONL schema and annotation guide. ✅ `benchmark/schema.md`, `annotation_guide.md`
- Offline annotation tool. ✅ `benchmark/annotate.html`
- Cohen's kappa + engine-vs-human script. ✅ `benchmark/agreement.py`
- Seed cases. ✅ `benchmark/cases_v0.jsonl` (10 pairs, labels empty)
- A local annotation tool (single HTML, keyboard-first, exports JSONL).
- Cohen's kappa + confusion-matrix script.
- Public-ATS fetcher for greenhouse/lever/ashby (respecting their public JSON).
- Metrics report + data card template + CI job.

**Only you (or a volunteer cohort) can provide:**

- 30-50 real applications with outcomes (for benchmark B).
- One co-annotator for the 20% double-labeled subset.
- Consent + review of any de-identified data before publishing.
- Final call on what personal data is acceptable to release.

## 9. Cost

- Public data + own labor: **0 currency**.
- Outsourced annotation: roughly ¥3-5 per case; 300 cases ≈ ¥1000-1500, plus
  adjudication time.

## 10. Risks

- **Single-applicant bias:** one person's outcomes do not generalize; label the
  cohort explicitly.
- **Small n:** r is unstable below ~50; never publish it without CI.
- **Label drift:** annotators change standards over time; re-calibrate with a
  shared gold subset every 50 cases.
- **Copyright/ToS:** the reason we store excerpts + hashes instead of full JDs.
