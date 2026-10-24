# -*- coding: utf-8 -*-
"""Download the public job-resume-matching dataset for real-data validation.

Source: HuggingFace `nonameee12233/job-resume-matching`
  https://huggingface.co/datasets/nonameee12233/job-resume-matching
The repo ships three CSVs at its root:
  - job.csv      (1,167 real job postings, with `category`)
  - cv.csv       (9,544 real résumés)
  - matches.csv  (122,560 candidate-job compatibility records, with `final_score`)

We save them under `data/real_eval/` with the names the eval scripts expect
(`job_resume_job.csv`, `job_resume_cv.csv`, `job_resume_matches.csv`).

License: the dataset ships under a CC BY-style license; cite the source when
redistributing. We store only the public files locally and add nothing private.

Usage:
    python scripts/fetch_real_eval_data.py
    python scripts/fetch_real_eval_data.py --out data/real_eval

Note: this needs outbound HTTPS to huggingface.co. If your network blocks it,
download the three CSVs manually from the dataset page and place them with the
expected names under `data/real_eval/`.
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.normpath(os.path.join(HERE, "..", "data", "real_eval"))

BASE = "https://huggingface.co/datasets/nonameee12233/job-resume-matching/resolve/main"
# remote filename -> local filename
FILES = {
    "job.csv": "job_resume_job.csv",
    "cv.csv": "job_resume_cv.csv",
    "matches.csv": "job_resume_matches.csv",
}

HEADERS = {
    "User-Agent": "career-loop/0.8 (+https://github.com/jian35/career-loop)",
    "Accept": "*/*",
}


def _fmt_mb(n: float) -> str:
    return f"{n / 1_000_000:.1f} MB"


def download(remote: str, dest: str) -> None:
    url = f"{BASE}/{remote}"
    req = urllib.request.Request(url, headers=HEADERS)
    print(f"\n↓ {remote}  ->  {os.path.basename(dest)}")
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length", "0") or "0")
        chunk = 1 << 20  # 1 MiB
        written = 0
        with open(dest, "wb") as fh:
            while True:
                buf = resp.read(chunk)
                if not buf:
                    break
                fh.write(buf)
                written += len(buf)
                if total:
                    pct = written / total * 100
                    print(f"   {pct:6.1f}%  {_fmt_mb(written)}/{_fmt_mb(total)}", end="\r")
                else:
                    print(f"   {_fmt_mb(written)}", end="\r")
    print(f"   done  {_fmt_mb(written)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--skip-existing", action="store_true",
                    help="skip files that already exist locally")
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    for remote, local in FILES.items():
        dest = os.path.join(out, local)
        if args.skip_existing and os.path.exists(dest):
            print(f"skip (exists): {local}")
            continue
        try:
            download(remote, dest)
        except Exception as exc:  # noqa: BLE001
            print(f"\nFAILED to download {remote}: {exc}")
            print("You can download it manually from the dataset page and save it as "
                  f"{local} under data/real_eval/.")
            return 1

    print("\nAll files downloaded. Verify with:")
    print("  python scripts/real_eval_family.py")
    print("  python scripts/real_eval_calibrate.py --n 2000 --seed 7")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
