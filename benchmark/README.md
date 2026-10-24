# Benchmark (v0, draft)

A small, public, **human-labeled** benchmark for requirement extraction and
matching. The goal is to replace "it looks right" with numbers that other people
can reproduce.

> **Status: v0 draft.** The 10 cases ship with pre-extracted requirements but
> **no human labels yet** (`labels: {}`). Do not quote accuracy numbers from this
> directory until labels exist and kappa is reported.

## Files

| File | Purpose |
| --- | --- |
| `cases_v0.jsonl` | 10 (JD × profile) cases, requirements pre-filled |
| `build_v0.py` | Regenerates `cases_v0.jsonl` from source text |
| `schema.md` | Field-level data spec |
| `annotation_guide.md` | How to decide full / partial / missing |
| `annotate.html` | Offline labeling tool (keyboard-first, exports JSONL) |
| `agreement.py` | Cohen's kappa + optional engine-vs-human accuracy |

## Quick start

1. Open `benchmark/annotate.html` in a browser (double-click; no server).
2. Load `benchmark/cases_v0.jsonl` with the file picker.
3. Label each requirement: `1` full, `2` partial, `3` missing; `↑/↓` to move,
   `n/p` to change case.
4. Export `annotations_<name>.jsonl`.
5. Ask a second person to do the same, then:

```bash
python benchmark/agreement.py \
  --cases benchmark/cases_v0.jsonl \
  --a annotations_a1.jsonl --b annotations_a2.jsonl --engine
```

Target: **Cohen's kappa >= 0.70** per capability. Below that, fix the annotation
guide before adding cases.

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

## What is still missing

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
