# -*- coding: utf-8 -*-
"""下载中文 JD 检验数据集（HuggingFace ngtranai09/china_job）。

数据来源：HuggingFace `ngtranai09/china_job`，8,674 条真实中文招聘 JD（猎聘），
约 9.8MB parquet。默认走 hf-mirror.com 镜像（国内可直连）。

不入库：data/cn_eval/ 已在 .gitignore 中。
"""

from __future__ import annotations

import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "cn_eval")
OUT_FILE = os.path.join(OUT_DIR, "china_job.parquet")

MIRRORS = [
    "https://hf-mirror.com/datasets/ngtranai09/china_job/resolve/main/data/train-00000-of-00001.parquet",
    "https://huggingface.co/datasets/ngtranai09/china_job/resolve/main/data/train-00000-of-00001.parquet",
]


def main() -> int:
    if os.path.exists(OUT_FILE):
        size = os.path.getsize(OUT_FILE)
        print(f"已存在：{OUT_FILE}（{size / 1024 / 1024:.1f} MB）")
        return 0

    os.makedirs(OUT_DIR, exist_ok=True)
    last_err: Exception | None = None
    for url in MIRRORS:
        print(f"尝试下载：{url}")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "career-loop/0.8"})
            with urllib.request.urlopen(req, timeout=120) as resp, \
                    open(OUT_FILE, "wb") as fh:
                total = 0
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    fh.write(chunk)
                    total += len(chunk)
            print(f"下载完成：{total / 1024 / 1024:.1f} MB → {OUT_FILE}")
            return 0
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"  失败：{e}", file=sys.stderr)
            if os.path.exists(OUT_FILE):
                os.remove(OUT_FILE)
    print(f"所有镜像均失败：{last_err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
