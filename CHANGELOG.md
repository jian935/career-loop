# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

## [0.5.1] - 2026-10-24

### Added
- The CLI now actually uses the LLM mode (`match` / `whatif` / `apply` /
  `recommend` / `add-jd`); it was implemented but never wired.
- LLM response cache at `~/.career_loop/llm_cache` (hash of model + prompt),
  disable with `CAREER_LOOP_NO_CACHE=1`.
- `doctor` command: Python / DB / LLM / cache / eval-set status.

### Fixed
- Configuring an API key had no effect; every command silently used rules.

### Changed
- 30 unit tests, 31 end-to-end CLI checks.

## [0.5.0] - 2026-10-24

### Added
- `intern` command: 10 built-in internship directions, ranked by
  (goal match, weighted score), plus a cohort timeline
  (daily internship -> summer -> autumn recruiting -> spring).
- Browser demo: an internship direction panel that updates with the profile.
- `--presets` to use your own internship JSONL.

### Fixed
- A JD's first line (job title without `#`) was parsed as a requirement,
  producing noise like "补：产品经理实习生".

### Changed
- 28 unit tests, 30 end-to-end CLI checks.

## [0.4.0] - 2026-10-24

### Added
- **Works for any role**, not just AI/tech: a layered vocabulary (AI/tech +
  9 universal capabilities + 12 job families) and a **custom fallback** that keeps
  requirements no vocabulary matched instead of silently dropping them.
- `whatif` command: counterfactual uplift — how much the score rises if one
  requirement is brought to "full".
- Browser demo (`docs/index.html`): zero-install, local-only, same rule engine as
  Python; deep link `?s=2` opens the finance sample.
- Docs: `docs/architecture.md`, `docs/methodology.md`, `docs/benchmark.md`.
- Governance: `CONTRIBUTING`, `SECURITY`, `CODE_OF_CONDUCT`, `LEGAL_DISCLAIMER`.
- CI workflow (Linux + Windows, Python 3.10-3.13) and `scripts/audit.py`.
- Dockerfile for a one-command run.

### Fixed
- `apply` / `log` did not forward `--db`, so they could read/write the default
  database instead of the one you passed.
- `collect` returned success on a non-existent directory.
- `_claim_lines` used a top-1 rule that let a long job-family keyword suppress a
  shorter core keyword (e.g. `资产负债表` hid `会计` / `金蝶`).
- Packaging missed `career_loop.matching` (editable installs worked, wheels would
  not).

### Changed
- Claim rule now keeps the top 4 lexical hits per line.
- `score`/`gaps` unchanged; eval baseline remains 1.0.

## [0.3.0] - 2026-10-24

### Added
- `collect`: batch-import raw JDs from a folder, strip job-board noise, dedupe.
- `demand`: capability demand heat map across a JD pool, with per-capability
  coverage and a build-priority score.

## [0.2.0] - 2026-10-24

### Added
- `recommend`: rank a JD pool for a given profile, and estimate which capability
  unlocks the most roles.

## [0.1.0] - 2026-10-24

### Added
- Initial closed loop: matching engine, weighted score, gap ranking with verbatim
  evidence, labeled eval set (42 cases), Pearson calibration with buckets, SQLite
  storage, CLI, optional Streamlit dashboard.
