# Methodology

This page documents exactly how a score is produced, so you can argue with it.
Every step is deterministic in the default (rules) mode.

## 1. Vocabulary layers

| Layer | Where | Examples |
| --- | --- | --- |
| AI / tech | `TAXONOMY` | `python`, `rag`, `agent`, `function_calling`, `eval` |
| Universal | `GENERAL_DIMS` | `exec_project`, `problem_solving`, `learning`, `writing`, `office` |
| Job family | `DOMAIN_PACKS` | `fin_tax`, `sales_bd`, `ds_visual`, `ai_mlops`, `project_mgmt` (33 packs) |
| Custom | generated per JD line | key `custom:<hash>`, label = the requirement text |

`ALL_DIMS` is the union. Keys are stable identifiers; labels are display strings.

## 2. JD -> requirements

1. Split the JD into lines; drop markdown headings and lines shorter than 6 chars.
2. Detect section markers (`岗位职责/工作职责/工作内容/职位描述/你将/职责`,
   `任职要求/岗位要求/任职资格/基础要求/要求`, `优先条件/加分项/优先/bonus`).
   A line is a section header only if the marker occupies almost the whole line
   (leftover <= 4 chars), so "要求熟悉 Python" stays a requirement.
3. For each requirement line, find every vocabulary hit (substring match,
   case-insensitive). If there is at least one hit, emit a requirement per key,
   keeping the highest weight seen for that key.
4. If a line has **no** vocabulary hit but looks like a requirement (contains
   verbs such as 熟悉/掌握/具备/负责/熟练/优先 and no noise markers such as
   薪资/福利/公司简介/邮箱), emit a **custom** requirement. Its label is the line
   with leading verbs stripped. This is why non-AI roles are not silently
   under-counted.

**LLM mode is not bounded by the vocabulary.** `extract_by_llm` first tries the
`known_keys` it is given (all 33 packs), then accepts `custom:<slug>` and
normalizes invented keys to `llm:<slug>`. A role with no pack at all (e.g. 茶艺师)
still gets structured capability items instead of line fragments.

### Weights

| Section | Weight |
| --- | --- |
| `nice` (优先/加分) | 1 |
| `job` (岗位职责) | 2 |
| `must`, no strong word | 2 |
| `must`, with a strong word | 3 |

Strong words: `精通`, `深入`, `独立`, `主导`, `熟练掌握`, `扎实`, `闭环`,
`从0到1`, `从 0 到 1`.

## 3. Profile -> status per requirement

1. Profile lines: skip headings, strip bullets, keep lines >= 6 chars.
2. Each line is "claimed" by the vocabulary keys it hits, keeping the **top 4**
   by longest matching keyword (length >= 2). Keeping more than one avoids losing
   shorter core keywords to a longer job-family keyword; capping at 4 stops a
   single paragraph from claiming everything.
3. For a canonical requirement key:
   - no claimed line -> `missing`
   - any claimed line contains a strong negative (`没用过/没做过/从没/完全没有/
     毫无/从不/没碰过/没接触/不了解`) -> `missing`
   - else take the first claimed line containing an action verb
     (`做/实现/搭建/开发/写/上线/设计/优化/负责/...`); `full` unless it also
     contains a hedge (`没有/未/只做过/仅/缺少/没做/没统计/demo/简单/...`), which
     becomes `partial`
   - no action verb at all -> `partial` (mentioned, but no evidence of doing it)
4. For a `custom:` requirement: compare character bigrams of the requirement with
   each profile line, after removing a stop list (`负责/经验/相关/能力/...`).
   Containment ratio `c = |target ∩ line| / |target|`:
   - `c >= 0.5` -> `full` if the line has an action verb, else `partial`
   - `c >= 0.28` -> `partial` (note: needs human confirmation)
   - otherwise -> `missing`

Evidence returned is always a slice of the matched profile line, never generated.

## 4. Score

```
score = Σ(weight_i × status_i) / Σ(weight_i) × 100
status_i ∈ { full: 1.0, partial: 0.5, missing: 0.0 }
```

Rounded to one decimal. No requirements -> 0.0.

### Gap priority

For every requirement that is not `full`:

```
priority = weight × severity        severity = missing 1.0, partial 0.5
```

Sorted descending. This is deliberately not the weighted average: a weight-3
hard requirement must not be hidden by a high average.

### Counterfactual (`whatif`)

For each non-full requirement, substitute it with `full`, recompute the score, and
report the delta. Sorted by delta descending. This answers "which single fix buys
the most", not "what is wrong".

## 5. Calibration

Given paired observations `(score, positive)` where `positive` is true for
`replied | interview | offer`:

```
r = Σ(x - x̄)(y - ȳ) / sqrt(Σ(x - x̄)² · Σ(y - ȳ)²)
```

- Requires `n >= 2` and non-zero variance; otherwise `r = None`.
- The CLI refuses to conclude below **5** samples.
- Buckets: `[0,20), [20,40), [40,60), [60,80), [80,100]`; each reports
  `positives / n`. Empty buckets report 0.0 but are labelled with `n=0`.
- Verdict: `|r| < 0.15` no relation; `< 0.4` weak; `>= 0.4` medium-to-strong.

`r` measures association, not causation. It says "higher scores co-occur with more
replies", not "the score caused the reply".

## 6. Evaluation set

`data/eval_sample.jsonl` contains 50 rows: 16 capabilities (14 `TAXONOMY` AI/tech + 2 `GENERAL_DIMS` general: `writing`, `exec_project`) × full/partial/missing, plus 8 extra coverage/boundary cases.
Each row is `{id, capability, expected, jd, profile}`. `run_eval` checks the
predicted status **for that capability only** and reports per-capability accuracy
plus badcases.

The set is a **regression lock**: it prevents rule changes from silently breaking
known cases. It is synthetic and boundary-focused; it is **not** a claim of
real-world accuracy.

Separately, real-world end-to-end agreement is validated on the public
`job-resume-matching` dataset (family-identification accuracy **93.6%**; engine score
vs. the dataset's `final_score` gives Pearson **r = 0.193** over 2,000 real pairs).
That is a real-label check on real data — a different, honest claim from "this score
predicts your offer". See `docs/benchmark.md` §2.2.

## 7. Ambiguous keywords

A word can mean different things in different roles: `召回` is retrieval recall in
RAG, but user win-back in operations; `推理` is model inference in MLOps, but
logical reasoning elsewhere. Bare ambiguous words therefore cause cross-domain
false positives (an Agent JD picking up "用户运营").

Rule: use **compound** keywords for ambiguous concepts (`用户召回`, `流失召回`,
`模型推理`, `推理服务`), and keep the bare word only in the domain where it is the
primary meaning (`召回` in RAG, `推荐召回`/`召回策略` in recsys).

## 8. Known limitations

- Keyword matching misses paraphrase and implicit requirements; the custom bigram
  fallback is coarse and can produce false `partial`.
- Domain packs are shallow (a few keywords per family); long-tail roles rely on
  the custom fallback.
- `r` with small samples is unstable; treat it as a warning signal, not a grade.
- The browser demo is a simplified port; when rules change, it must be updated in
  the same commit to stay behavior-compatible.
