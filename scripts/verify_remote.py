#!/usr/bin/env python3
"""核验 GitHub 上的仓库内容与本地是否一致（推送后自检）。

用法：
    python scripts/verify_remote.py                 # 用 origin 的 URL 推算仓库名
    python scripts/verify_remote.py --repo jian935/career-loop

读法：
- 只比对**已跟踪文件**（git ls-files），不碰本地未入库的数据。
- 通过 GitHub REST API 的 contents 接口逐文件比对 size（字节数）与
  blob sha（git hash-object 的值），不看内容正文，避免把大文件拉下来。
- 只读操作：不写仓库、不改任何东西。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"


def sh(*args: str) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout.strip()


def tracked() -> list[str]:
    out = sh("git", "ls-files")
    return [p for p in out.splitlines() if p]


def api_get(path: str, token: str | None) -> dict:
    req = urllib.request.Request(f"{API}{path}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def git_blob_sha(path: str) -> str:
    """git 的 blob sha = sha1("blob <len>\0" + content)。"""
    with open(path, "rb") as f:
        data = f.read()
    h = hashlib.sha1()
    h.update(f"blob {len(data)}\0".encode())
    h.update(data)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="", help="owner/name，默认从 origin URL 推算")
    ap.add_argument("--token", default="", help="可选：GitHub token（公开仓库不需要）")
    ap.add_argument("--branch", default="main")
    args = ap.parse_args()

    repo = args.repo
    if not repo:
        url = sh("git", "remote", "get-url", "origin")
        repo = url.rstrip("/").removesuffix(".git").split("/")[-2:]
        repo = "/".join(repo)
    token = args.token or ""

    print(f"核验仓库：{repo}（分支 {args.branch}）")

    files = tracked()
    print(f"本地已跟踪文件：{len(files)} 个")

    try:
        api_get(f"/repos/{repo}", token)
    except urllib.error.HTTPError as exc:
        print(f"✗ 无法访问仓库 {repo}：HTTP {exc.code}")
        if exc.code == 404:
            print("  可能仓库不存在、或未公开、或需要 token（--token）")
        return 2
    except urllib.error.URLError as exc:
        print(f"✗ 网络不通：{exc.reason}")
        print("  这个脚本需要能访问 api.github.com")
        return 2
    print("✓ 仓库可访问")

    ok = missing = differ = 0
    problems: list[tuple[str, str]] = []

    for path in files:
        try:
            data = api_get(f"/repos/{repo}/contents/{path}?ref={args.branch}", token)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                missing += 1
                problems.append((path, "远端缺失"))
            else:
                differ += 1
                problems.append((path, f"HTTP {exc.code}"))
            continue
        except urllib.error.URLError as exc:
            differ += 1
            problems.append((path, f"网络 {exc.reason}"))
            continue

        if data.get("type") != "file":
            problems.append((path, f"类型异常 {data.get('type')}"))
            differ += 1
            continue

        local_sha = git_blob_sha(path)
        remote_sha = (data.get("sha") or "").strip()
        if remote_sha == local_sha:
            ok += 1
        else:
            differ += 1
            problems.append((path, f"sha 不同（本地 {local_sha[:8]} / 远端 {remote_sha[:8]}）"))

    print(f"\n一致 {ok} / {len(files)}")
    if missing:
        print(f"远端缺失 {missing} 个")
    if differ:
        print(f"内容不一致 {differ} 个")
    if problems:
        print("\n问题清单：")
        for path, why in problems[:40]:
            print(f"  - {path}：{why}")
        if len(problems) > 40:
            print(f"  … 另有 {len(problems) - 40} 条")
        return 1

    print("✓ 远端内容与本地已跟踪文件逐字节一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
