# Architecture

Career-Loop is a small, dependency-free core with optional layers around it. The
goal is that every number in a report can be traced back to a rule and a quote.

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│ JD text     │────▶│ extract      │────▶│ Requirement │
└─────────────┘     │ (rules / LLM)│     │ key, weight │
                    └──────────────┘     └──────┬──────┘
┌─────────────┐     ┌──────────────┐            │
│ Profile     │────▶│ match        │◀───────────┘
└─────────────┘     │ rules / LLM  │
                    └──────┬───────┘
                           ▼
                 ┌──────────────────┐
                 │ score / gaps /   │
                 │ counterfactual   │
                 └────────┬─────────┘
                          ▼
        ┌──────────────────────────────────┐
        │ report.md / json / CLI / web demo│
        └──────────────────────────────────┘
                          │
                          ▼
        ┌──────────────────────────────────┐
        │ store (SQLite) → outcomes        │
        │        → calibrate (Pearson r)    │
        └──────────────────────────────────┘
```

## Modules

| Path | Responsibility |
| --- | --- |
| `career_loop/matching/schema.py` | Data classes and the layered vocabulary (`TAXONOMY`, `GENERAL_DIMS`, `DOMAIN_PACKS`, `ALL_DIMS`) |
| `career_loop/matching/extract.py` | JD -> `Requirement[]`; section detection, weights, custom fallback |
| `career_loop/matching/match.py` | Profile x requirement -> `full/partial/missing` + evidence; score, gaps, counterfactual |
| `career_loop/matching/llm.py` | Optional OpenAI-compatible client; failure falls back to rules |
| `career_loop/matching/render.py` | Markdown report |
| `career_loop/store.py` | SQLite: profiles, jds, applications |
| `career_loop/calibrate.py` | Pearson correlation, 20-point buckets, verdict |
| `career_loop/eval.py` | Labeled eval set loader + per-capability scoring |
| `career_loop/collect.py` | Batch JD import, noise stripping, dedupe, demand heat map |
| `career_loop/recommend.py` | Profile -> JD ranking; gap leverage |
| `career_loop/cli.py` | Command-line surface |
| `career_loop/dashboard.py` | Optional Streamlit view |
| `docs/index.html` | Zero-install browser demo (same rules, in JS) |

## Data model

```
profiles(id, name, text, created_at)
jds(id, title, text, requirements JSON, created_at)
applications(id, jd_id, profile_id, fit_score, status, note, applied_at)
```

`status ∈ {applied, replied, interview, offer, rejected}`.
Calibration treats `replied | interview | offer` as positive.

## Two execution modes

1. **Rules (default).** Deterministic, offline, inspectable. This is the baseline
   and the thing the eval set locks.
2. **LLM (optional).** Used only if an OpenAI-compatible key is configured. If it
   errors, returns invalid JSON, or is unavailable, the engine silently falls back
   to rules and records `mode: rule`.

## Extension points

- **New capability**: add to `schema.py`, add a test, update
  `docs/methodology.md`.
- **New job family**: add a pack under `DOMAIN_PACKS`, prefix keys.
- **New evidence source**: implement a matcher returning `MatchResult`; keep
  evidence verbatim.
- **New evaluation**: append JSONL rows to `data/eval_sample.jsonl`; `run_eval`
  will include them automatically.

## Design constraints

- Core has no third-party imports (CI enforces a clean environment).
- Evidence is a substring of user input; the matcher may not invent it.
- The browser demo must stay behavior-compatible with Python on the shipped
  samples (checked manually and in review).
- Reports are plain Markdown so they can be diffed and audited.

## What this is not

Not an auto-apply bot, not a resume generator, not a scraper. Those are separate
concerns (and separate projects). This repo is the **evaluation layer**: score,
explain, and verify.
