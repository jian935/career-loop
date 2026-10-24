# Benchmark data schema

Two files per round:

- `cases_v0.jsonl` — the cases to annotate (one JSON object per line).
- `annotations_<annotator>.jsonl` — one annotator's labels.

## Case object

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | string | ✅ | Stable, e.g. `match-ai-pm` |
| `language` | `"zh"` \| `"en"` | ✅ | |
| `job_family` | string | ✅ | `ai`, `finance`, `sales`, `design`, ... |
| `jd` | string | ✅ | Full JD text used for annotation (public excerpt or consented) |
| `profile` | string | ✅ | Synthetic, or consented + de-identified |
| `requirements` | array | ✅ | Pre-extracted, see below |
| `labels` | object | ✅ | Empty `{}` in the case file; filled in annotations |

### Requirement object

| Field | Type | Notes |
| --- | --- | --- |
| `key` | string | Capability key, or `custom:<hash>` |
| `label` | string | Display label |
| `weight` | 1 \| 2 \| 3 | 1 = nice-to-have, 2 = normal, 3 = hard requirement |
| `line` | string | Verbatim JD line |

## Annotation object

One line per case:

```json
{
  "id": "match-ai-pm",
  "annotator": "a1",
  "labels": {
    "llm_basics": {
      "status": "partial",
      "evidence": "用 DeepSeek API 做了提示词工程",
      "note": "提了 API，但没写模型边界"
    }
  },
  "reviewed": true
}
```

- `status` ∈ `full` | `partial` | `missing`.
- `evidence` must be copied from `profile`; empty for `missing`.
- Keys must exist in the case's `requirements`; extra keys are ignored by the
  scorer.
- `reviewed` means the annotator finished the whole case.

## Scoring

```bash
python benchmark/agreement.py \
  --cases benchmark/cases_v0.jsonl \
  --a annotations_a1.jsonl --b annotations_a2.jsonl
```

Reports per-capability agreement, Cohen's kappa, and (if `--engine` is passed)
engine-vs-human accuracy.
