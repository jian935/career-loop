# Benchmark data card — template

> **This is a template.** The numeric sections (§1–§5) are filled automatically by
> `benchmark/agreement.py --datacard <out.md>` from your annotation files. The
> bracketed `[...]` sections are for you to write by hand: the *story* and the
> *legal* parts that a script cannot know. Do not publish accuracy numbers until
> both annotators have labeled and kappa is reported.
>
> Status check before publishing:
> - [ ] Two independent annotators, labeled without discussing cases.
> - [ ] Cohen's kappa >= 0.70 per capability (or the rule for that capability was
>       rewritten and re-labeled).
> - [ ] Bootstrap 95% CI reported (not a single point estimate).
> - [ ] Data source + consent + de-identification documented (§7).

## How to fill the numbers

```bash
python benchmark/agreement.py \
  --cases benchmark/cases_v1.jsonl \
  --a annotations_a1.jsonl --b annotations_a2.jsonl \
  --engine --bootstrap 2000 --seed 0 \
  --datacard benchmark/datacard.md --consensus benchmark/consensus.jsonl
```

Then paste the generated `benchmark/datacard.md` §0–§5 here (or keep it as the
canonical file and only fill §6–§8 below). The `consensus.jsonl` is your
adjudication-ready label set: entries where the two annotators disagreed (or only
one labeled) are flagged `needs_review: true` with both raw labels preserved.

## §0. Metadata

- Benchmark version: `v1`
- Generated (UTC): `[auto]`
- cases file: `[path]`
- Annotators: A=`[name/handle]`　B=`[name/handle]`
- Engine version measured: `career-loop [version]` (pin it)

## §1. Dataset summary (target vs actual)

| Item | v1 target | Actual |
| --- | ---: | ---: |
| (JD × profile) cases | 300 | `[n]` |
| Job families covered | 30+ | `[n]` |
| Double-labeled (both annotators) | >= 20% (>= 60) | `[n]` |
| Profiles synthetic / consented-real | 300 syn + 50 real | `[n / n]` |

## §2. Annotation agreement (Cohen's kappa)

| Metric | Value | Target |
| --- | --- | --- |
| Overall agreement rate | `[auto]` | — |
| Overall Cohen's kappa | `[auto]` | >= 0.70 |
| Overall 95% CI | `[auto]` | narrow & above 0.70 |

**Interpretation:** `[one paragraph — which capabilities were easy/hard to agree
on, any systematic bias between annotators (e.g. A marks partial where B marks
missing).]`

## §3. Per-capability agreement

| Capability | n | Agreement | kappa | 95% CI |
| --- | --- | ---: | ---: | --- |
| `[auto from datacard.md §3]` | | | | |

Capabilities below kappa 0.70 and what was done about them:
- `[key]`: `[rewrote rule / added worked example to annotation_guide.md / dropped]` — `[result]`.

## §4. Engine vs human (optional, --engine)

| Metric | Value |
| --- | --- |
| Overall accuracy (on agreed pairs) | `[auto]` |
| Per-capability accuracy | `[auto]` |

Caveat: this only measures agreement with the *human consensus label*, not
real-world hiring outcomes. It is a labeling-quality check, not a calibration
claim. Calibration (`r`) needs real outcomes (benchmark B) and is out of scope
for v1.

## §5. Disagreement examples (qualitative)

The auto data card lists the raw A/B mismatches. Turn the top ones into prose so
a reader understands *why* labels diverge:

- `[case id] / [capability]`: A said `full` ("…"), B said `partial` ("…").
  Resolution: `[the adjudicated label + the rule that decided it]`.
- …

## §6. Per-family coverage

Run `python benchmark/build_v1.py validate benchmark/cases_v1.jsonl` and paste
the family-coverage table here. Confirm no family is so thin that its per-capability
accuracy CI is meaningless (< ~30 cases per capability is the floor for a +/-10%
interval).

## §7. Legal & privacy

- [ ] JD sourcing: public ATS JSON (Greenhouse/Lever/Ashby) or own collected JDs;
      **not** scraped from LinkedIn / Boss / 猎聘.
- [ ] For each JD: `source_url` + `sha256` recorded; stored text is at most a
      short excerpt when the source terms forbid redistribution.
- [ ] Profiles: synthetic, **or** real with written consent and PII removed
      (name / phone / email / employer).
- [ ] License: code MIT; annotations **CC BY 4.0**; JD excerpts under their source
      terms.
- [ ] Takedown path documented; honor requests within 7 days.

## §8. Reproducibility

```bash
# exact command used (copy from datacard.md §6)
[command]

# environment
python --version      # [e.g. 3.13.x]
pip show career-loop  # [version]
# no network / API key required for the labeling + agreement step
```

If the engine version changed between annotation and measurement, re-run §4; the
labeling step itself is engine-independent.
