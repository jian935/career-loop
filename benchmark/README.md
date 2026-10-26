# Benchmark (v0, draft)

A small, public, **human-labeled** benchmark for requirement extraction and
matching. The goal is to replace "it looks right" with numbers that other people
can reproduce.

> **Status: v1 scaffolding ready — human labels still pending.** The 10 seed cases
> ship with pre-extracted requirements but **no human labels yet** (`labels: {}`).
> The v1 *framework* (300-case target, double-label compare mode, bootstrap-kappa
> CIs, auto-generated data card) is in place; do **not** quote accuracy numbers
> until real labels exist and kappa is reported.

## Files

| File | Purpose |
| --- | --- |
| `cases_v0.jsonl` | 10 (JD × profile) cases, requirements pre-filled |
| `build_v0.py` | Regenerates `cases_v0.jsonl` from source text |
| `build_v1.py` | v1 scaffold: `plan` / `scaffold` / `validate` (300 pairs, 30+ families) |
| `schema.md` | Field-level data spec |
| `annotation_guide.md` | How to decide full / partial / missing |
| `annotate.html` | Offline labeling tool (keyboard-first, exports JSONL, double-label compare) |
| `agreement.py` | Cohen's kappa + bootstrap 95% CI + data card + consensus export |
| `datacard_template.md` | Data-card template (numbers auto-filled; narrative/legal by hand) |

## v1 scaffolding: what is ready vs what needs a human

**Ready now (zero runtime dependency, offline):**

- `python benchmark/build_v1.py plan` — the balanced 300-case / 30-family target.
- `python benchmark/build_v1.py scaffold --out benchmark/cases_v1_scaffold.jsonl`
  — 300 empty id/family slots with explicit `TODO` markers (not real data).
- `annotate.html` — label one annotator; load a second annotator's JSONL with the
  "第二标注人" button and every disagreement is highlighted (red border + `B: …`
  tag), with a live `分歧 N / 双标注 M` counter.
- `agreement.py --bootstrap 2000 --seed 0 --datacard X.md --consensus Y.jsonl` —
  reproducible kappa with 95% CI, an auto-filled data card, and adjudication-ready
  consensus labels (disagreements flagged `needs_review`).
- `python benchmark/build_v1.py validate cases.jsonl --a A --b B` — coverage gaps
  and double-label readiness.

**Needs a human / volunteer cohort (cannot be generated):**

- The 300 real (JD × profile) pairs — sourced from public ATS JSON or your own
  compliant JDs; **do not scrape** LinkedIn / Boss / 猎聘.
- Two independent annotators on >= 20% of cases.
- Consent + de-identification review before publishing any real data.

## Quick start

1. Open `benchmark/annotate.html` in a browser (double-click; no server).
2. Load `benchmark/cases_v0.jsonl` with the file picker.
3. Label each requirement: `1` full, `2` partial, `3` missing; `↑/↓` to move,
   `n/p` to change case.
4. Export `annotations_<name>.jsonl`.
5. Ask a second person to do the same (load their JSONL in `annotate.html` via the
   "第二标注人" button to see disagreements live), then:

```bash
python benchmark/agreement.py \
  --cases benchmark/cases_v0.jsonl \
  --a annotations_a1.jsonl --b annotations_a2.jsonl --engine \
  --bootstrap 2000 --seed 0 \
  --datacard benchmark/datacard.md --consensus benchmark/consensus.jsonl
```

Target: **Cohen's kappa >= 0.70** per capability, reported **with its 95% CI**.
Below 0.70, fix the annotation guide before adding cases. Fill the narrative/legal
sections of `datacard.md` using `datacard_template.md`.

## Annotation protocol

- Double-label at least 20% of cases (minimum 20 cases when the set grows).
- Label independently; do not discuss individual cases before submitting.
- Adjudicate disagreements; keep both raw files and the final label.
- Re-check a shared 20-case gold subset every 50 cases to catch drift.

## Data policy

- Profiles in v0 are **synthetic**.
- If you add real data: written consent, remove names / phone / email / employer,
  and say so in the data card.
- JD text: keep `source_url` and `sha256`; store at most a short excerpt when the
  source terms do not allow redistribution.
- Do not scrape LinkedIn / Boss / 猎聘. Public ATS JSON (Greenhouse, Lever, Ashby)
  or your own collected JDs only.

## What is still missing (data, not tooling)

The tooling is now in place; what remains is human labeling at scale:

| Gap | Why it matters |
| --- | --- |
| Human labels | No accuracy claim is possible without them |
| 300-500 cases across 30+ families | Tiny samples hide family-specific failures |
| Real outcomes | Needed for calibration (`r`), not for coverage |
| Second annotator | Kappa is the only guard against idiosyncratic labels |

See [`../docs/benchmark-plan.md`](../docs/benchmark-plan.md) for data volume,
statistical power, legal constraints, and milestones.

## License

- Code (`.py`, `.html`): MIT, same as the project.
- Annotations: **CC BY 4.0**.
- JD excerpts remain under their source terms; we do not relicense them.
