## What changed

<!-- One or two sentences. Link the issue if there is one. -->

## Why

<!-- The user-facing or evaluation reason. -->

## Checklist

- [ ] `python -m unittest discover -s career_loop/tests -p "test_*.py"` passes
- [ ] `python scripts/audit.py` passes
- [ ] `python -m career_loop eval --data data/eval_sample.jsonl` still reports 1.0 (or I explained the drop)
- [ ] Core has no new third-party dependency
- [ ] Browser demo updated if rules changed (scores must match Python on shipped samples)
- [ ] Docs updated if behavior, numbers, or vocabulary changed
- [ ] No personal data, tokens, or local databases committed

## Notes for reviewers

<!-- Edge cases, trade-offs, things you are unsure about. -->
