# Contributing

Thanks for taking a look. This project is intentionally small, so the bar for
changes is less about volume and more about **not making the evaluation less
trustworthy**.

## Principles (please don't break these)

1. **Evidence is verbatim.** Any `evidence` shown in a report must be copied from
   the user's own text. Never generate or paraphrase it.
2. **No fabricated experience.** The engine may say "missing"; it must never imply
   the candidate has something they didn't write.
3. **Zero dependency core.** `career_loop` must run on a clean Python 3.10+ with
   no third-party packages. `streamlit` is UI-only and optional.
4. **Honest numbers.** We do not claim real-world accuracy. The eval set is a
   regression lock, and `r` is only reported with its sample size.
5. **Rules must stay explainable.** If a matching decision can't be explained in
   one sentence with a quote, don't ship it.

## Local development

```bash
python -m unittest discover -s career_loop/tests -p "test_*.py" -v
python -m career_loop eval --data data/eval_sample.jsonl --badcases /tmp/bc.jsonl
python scripts/audit.py          # end-to-end CLI audit, exits non-zero on failure
```

No virtualenv is required for the core. Create one only if you need `streamlit`.

## Adding a capability (dimension)

1. Add the entry to `career_loop/matching/schema.py`:
   - AI/tech dims -> `TAXONOMY`
   - universal soft skills -> `GENERAL_DIMS`
   - a job family -> `DOMAIN_PACKS`
   Keep keys unique; prefix job-family keys (`fin_`, `sales_`, `ds_`, ...).
2. Add 2-3 keyword variants people actually write, including common synonyms.
3. Add a unit test in `career_loop/tests/test_core.py` proving the new key is
   extracted and matched.
4. If the dimension is broadly useful, add it to `docs/methodology.md`.
5. Run `python -m career_loop eval ...` and make sure the baseline is still 1.0.

> Do **not** add a keyword that is a strict synonym of an existing core key
> (e.g. `user_research` next to `product_sense`). Longer keywords suppress
> shorter ones during line claiming and cause silent regressions.

## Commit messages

Follow conventional-ish prefixes: `feat:`, `fix:`, `docs:`, `test:`, `chore:`.
One logical change per commit. Explain *why* in the body if the diff is not
self-evident.

## Pull request checklist

- [ ] `python -m unittest discover -s career_loop/tests -p "test_*.py"` passes
- [ ] `python scripts/audit.py` passes
- [ ] `python -m career_loop eval ...` still reports 1.0 (or you explain the drop)
- [ ] No new third-party dependency in the core path
- [ ] Docs updated if behavior or numbers changed
- [ ] No personal data, tokens, or local DBs committed

## Good first issues

- Add a job-family pack (e.g. architecture, logistics, hospitality).
- Add a badcase to `data/eval_sample.jsonl` that currently fails.
- Improve Chinese/English keyword coverage for one dimension.
- Add a translation of the README.

## Reporting a bug

Open an issue with: the JD text (redact personal info), the profile text, the
command, the actual output, and the expected output. A reproducible snippet is
worth more than a long description.
