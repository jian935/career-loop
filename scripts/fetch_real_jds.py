# -*- coding: utf-8 -*-
"""Fetch real public job posts from Remotive / Jobicy into a JSONL file.

These APIs are public job-distribution feeds. We store title/company/url and a
trimmed description for local evaluation only; do not redistribute the text.

Usage:
    python scripts/fetch_real_jds.py --target 100 --out benchmark/real_jds_v0.jsonl
"""

from __future__ import annotations

import argparse
import html
import json
import re
import urllib.request
from pathlib import Path

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; career-loop/0.6; +https://github.com/)",
    "Accept": "application/json",
}


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=40) as resp:
        return json.loads(resp.read().decode("utf-8"))


def clean(text: str, limit: int = 6000) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>|</li>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:limit]


def from_remotive(lang: str) -> list[dict]:
    data = _get("https://remotive.com/api/remote-jobs?limit=200")
    out = []
    for j in data.get("jobs", []):
        out.append({
            "id": f"remotive:{j.get('id')}",
            "source": "remotive",
            "category": j.get("category") or "unknown",
            "title": (j.get("title") or "").strip(),
            "company": (j.get("company_name") or "").strip(),
            "location": j.get("candidate_required_location") or "",
            "url": j.get("url") or "",
            "description": clean(j.get("description") or ""),
        })
    return out


def from_jobicy(lang: str) -> list[dict]:
    data = _get("https://jobicy.com/api/v2/remote-jobs?count=100")
    out = []
    for j in data.get("jobs", []):
        industry = j.get("jobIndustry")
        if isinstance(industry, str):
            industry = industry.strip("[]'\"")
        elif isinstance(industry, list):
            industry = ", ".join(str(x) for x in industry)
        out.append({
            "id": f"jobicy:{j.get('id')}",
            "source": "jobicy",
            "category": industry or "unknown",
            "title": (j.get("jobTitle") or "").strip(),
            "company": (j.get("companyName") or "").strip(),
            "location": j.get("jobGeo") or "",
            "url": j.get("url") or "",
            "description": clean(j.get("jobDescription") or ""),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=100)
    ap.add_argument("--out", default="benchmark/real_jds_v0.jsonl")
    args = ap.parse_args()

    rows: list[dict] = []
    for fn in (from_remotive, from_jobicy):
        try:
            got = fn("en")
            print(f"{fn.__name__}: {len(got)}")
            rows.extend(got)
        except Exception as exc:  # noqa: BLE001
            print(f"{fn.__name__} failed: {exc}")

    seen = set()
    unique = []
    for r in rows:
        if not r["title"] or len(r["description"]) < 120:
            continue
        key = (r["title"].lower(), r["company"].lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)

    unique = unique[: args.target]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in unique:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    cats: dict[str, int] = {}
    for r in unique:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    print(f"\nwrote {len(unique)} -> {out}")
    for cat, n in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"  {n:>3}  {cat}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
