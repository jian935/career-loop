# -*- coding: utf-8 -*-
"""Fetch a targeted product/AI job pool from Himalayas (public API).

Keeps only entry/mid-level roles whose title or category mentions product, AI,
ML, LLM, agent, or automation. Writes JSONL with a `level_hint` field.

Usage:
    python scripts/fetch_target_jds.py --pages 20 --out benchmark/target_jds.jsonl
"""

from __future__ import annotations

import argparse
import html
import json
import re
import time
import urllib.request
from pathlib import Path

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; career-loop/0.7; +https://github.com/)",
    "Accept": "application/json",
}
SENIORITY = {
    "entry-level": "junior", "entry": "junior",
    "mid-level": "mid", "mid": "mid",
    "senior": "senior", "manager": "senior",
    "director": "exec", "executive": "exec",
}
RELEVANT_PHRASES = ("product", "artificial intelligence", "machine learning",
                    "automation", "data science", "conversational")


def is_relevant(title: str, categories: str) -> bool:
    t = title.lower()
    if "product" in t:
        return True
    if "product" in categories.lower():
        return True
    # uppercase AI as a token: "AI Operations" yes, Italian "ai Test" no
    if re.search(r"\bAI\b", title) or re.search(r"\bAI\b", categories):
        return True
    return any(w in t for w in (
        "machine learning", "artificial intelligence", "llm", "agentic",
        "automation", "data analyst", "data science", "analytics engineer",
        "business analyst",
    ))


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


def level_of(seniority) -> str:
    s = str(seniority or "").lower()
    for k, v in SENIORITY.items():
        if k in s:
            return v
    return "mid"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=20)
    ap.add_argument("--out", default="benchmark/target_jds.jsonl")
    args = ap.parse_args()

    jobs: list[dict] = []
    cursor = None
    for i in range(args.pages):
        url = "https://himalayas.app/jobs/api?limit=20"
        if cursor:
            url += f"&cursor={cursor}"
        data = _get(url)
        jobs.extend(data.get("jobs", []))
        cursor = data.get("nextCursor")
        if not cursor:
            break
        time.sleep(0.15)

    out_rows = []
    for j in jobs:
        title = (j.get("title") or "").strip()
        cats = " ".join(j.get("parentCategories") or [])
        level = level_of(j.get("seniority"))
        if level not in ("junior", "mid"):
            continue
        if not is_relevant(title, cats):
            continue
        desc = clean(j.get("description") or "")
        if len(desc) < 200:
            continue
        out_rows.append({
            "id": f"himalayas:{j.get('guid') or title}",
            "source": "himalayas",
            "category": cats or "Product",
            "title": title,
            "company": (j.get("companyName") or "").strip(),
            "location": " / ".join(j.get("locationRestrictions") or []),
            "url": j.get("applicationLink") or "",
            "description": desc,
            "level_hint": level,
        })

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"scanned {len(jobs)} -> kept {len(out_rows)} -> {out}")
    for r in out_rows[:10]:
        print(f"  [{r['level_hint']:<6}] {r['title']} | {r['company']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
