# Scaling to "all jobs": routes, effort, and what "done" means

## 0. Bottom line

| Goal | Route | Time (1 person, full-time) |
| --- | --- | --- |
| **能分析**几乎所有岗位 | LLM-first extraction + rule fallback | **1–2 months** |
| **能证明**覆盖所有岗位 | Hybrid + stratified benchmark + double labeling | **3–4 months** |
| 坚持手工扩词表 | Hand-curated packs | **1–2 years, still incomplete** |

The first two are engineering + evaluation problems. The third is a treadmill.

## 1. How big is "all jobs"?

| Source | Size |
| --- | --- |
| 中国《职业分类大典（2022 年版）》 | 8 大类 / 79 中类 / 449 小类 / **约 1,600 个职业** |
| O*NET-SOC (US) | **约 1,000 个职业** |
| 招聘平台上的职位名称 | **百万级**，长尾极长（同岗不同名、公司自创 title） |

So "all jobs" is not a finite list of 1,600 strings. A job family can be enumerated;
**job titles cannot**. Any approach that requires naming every title will lose.

## 2. Why the current approach has a ceiling

Today: 33 hand-written job-family packs + keyword matching + a custom fallback.

- Works well for the families we wrote (AI, business admin, common functions).
- Long-tail roles fall into `custom:` and are matched by character bigrams — broad,
  but coarse.
- Adding a pack is ~0.5–1 day; 1,600 occupations × several skills each is years of
  curation, and each new pack risks keyword collisions with existing ones.

The ceiling is **curation labor**, not code.

## 3. Four routes

### A. Hand-curated packs (current path)

| Item | Estimate |
| --- | --- |
| 100 packs (~70–80% of common postings) | 50–80 person-days (~2.5–4 months) |
| 300 packs | 150–300 person-days (~6–12 months) |
| 1,600 occupations | **not feasible by hand** |

Quality is high where covered, but coverage grows linearly and collisions grow
super-linearly.

### B. Import an occupational taxonomy + auto-expand keywords

| Step | Estimate |
| --- | --- |
| Import O*NET / 职业分类大典 skeleton (8/79/449) | 5–10 days |
| Auto-expand keywords from a JD corpus (TF-IDF / KeyBERT per family) | 15–20 days |
| Human review of top families | 10–15 days |
| **Total** | **2–3 months** |

Covers the **structure** of all occupations, but keyword quality is uneven and
still needs a corpus. Good as a skeleton, not as the matching engine.

### C. LLM-first extraction

| Step | Estimate |
| --- | --- |
| Wire LLM extraction as default + cache + fallback (mode exists) | 8–12 days |
| Batch mode + cost/latency controls | 5–8 days |
| Evaluation on 300–500 JDs | 20–30 days |
| **Total** | **~1.5–2 months** |

No vocabulary needed: the model reads any JD and returns requirements. Coverage is
effectively unlimited. Costs and hallucination are the trade-offs.

### D. Hybrid (recommended)

Rule packs as the fast path and label source; LLM for unknown families; embeddings
or bigrams for custom matching; a stratified benchmark to keep it honest.

| Step | Estimate |
| --- | --- |
| LLM path + caching + fallback (P0) | 10–15 days |
| Taxonomy skeleton + family mapping (P1) | 15–20 days |
| 500–1,000 JD stratified benchmark, 2 annotators, kappa (P2) | 30–40 days |
| Coverage report + long-tail tuning + docs (P3) | 15–20 days |
| **Total** | **3–4 months** |

## 4. Cost model

- LLM extraction: roughly **¥0.001–0.01 per JD** with a small model; 10k JDs ≈
  ¥10–100. A frontier model is 5–20× that.
- Annotation: **¥3–5 per case** outsourced; 1,000 cases ≈ ¥3,000–5,000, plus
  adjudication. Own labor is cheaper but slower.
- Engineering: 1 person, 3–4 months.

## 5. What "done" should mean

Do not claim "covers all jobs" without numbers. Define done as:

1. **Structural coverage**: every 中类 (79) has at least one evaluated JD.
2. **Long-tail behavior**: on 200 random JDs outside the curated packs, the engine
   still extracts ≥ 90% of requirement lines (via LLM or custom fallback).
3. **Quality**: per-family accuracy ≥ 80% on the stratified benchmark; Cohen's
   kappa ≥ 0.70 between annotators.
4. **Cost/latency**: < ¥0.02 and < 3 s per JD.
5. **Honesty**: report coverage and accuracy **per family**, not one aggregate
   number.

## 6. Recommended sequence

| Phase | Duration | Output |
| --- | --- | --- |
| P0 LLM path | 2–3 weeks | any JD can be parsed; cache + fallback |
| P1 taxonomy skeleton | 3–4 weeks | 8/79/449 mapping; family labels |
| P2 benchmark | 6–8 weeks | 500–1,000 JDs, 2 annotators, kappa |
| P3 coverage report | 3–4 weeks | per-family accuracy + long-tail report |

Total: **~3–4 months** for a defensible "all jobs" claim.
If you only need "it works on my target roles", the current 33 packs are enough.

## 7. Risks

- **Long-tail titles**: no taxonomy enumerates them; LLM is the only practical path.
- **Keyword collisions**: every new pack can suppress an existing one (we already
  hit `提示词工程` → `工程落地`, `转化率` → `电商运营`).
- **LLM cost drift** and provider changes.
- **Benchmark bias**: 500 JDs is a sample; stratify by 中类, not by convenience.
- **Overclaiming**: one aggregate accuracy number hides failing families.
