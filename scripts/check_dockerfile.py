#!/usr/bin/env python
"""Dockerfile 离线校验——本机没有 docker 时，也能挡住最常见的两类腐坏。

为什么需要它
------------
README 里写了「Docker 见 `Dockerfile`」，但本机没有 docker 命令、CI 里也没有
build 步骤，所以这个文件**从来没被执行过**。一个没执行过的 Dockerfile 只会
朝坏的方向变：哪天有人在代码里加了一个默认读取的 `data/xxx.jsonl`，容器里
就少这个文件，而本地开发完全发现不了（本地有完整仓库）。

它能挡住什么
------------
1. COPY 的源不存在（路径改名/移动后最常见的腐坏）
2. 运行时真正会读的仓库内文件，其所在目录没被 COPY
   ——这类最阴：镜像 build 得出来，跑起来在某一个命令上炸
3. ENTRYPOINT 用的命令名和 pyproject 里声明的 console script 对不上
4. pip 安装需要的文件（pyproject.toml / README.md）没被先 COPY

它挡不住什么（所以 CI 里仍然要真跑 docker build）
------------------------------------------------
基础镜像能不能拉下来、系统级依赖缺不缺、容器里的权限问题。
脚本的定位是**离线把静态部分查完**，让 CI 那次 build 只承担环境问题。

用法
----
    python scripts/check_dockerfile.py            # 校验
    python scripts/check_dockerfile.py --self-test  # 校验器自身的A/B自测
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = ROOT / "Dockerfile"


# --------------------------------------------------------------------------
# 解析
# --------------------------------------------------------------------------

def parse_copy_sources(docker_text: str) -> list[str]:
    """取出所有 `COPY <src>... <dst>` 的**源**路径。

    注意 `COPY a b ./` 这种多源写法：最后一个 token 是目标目录，
    前面的全都是源。第一版只取了 parts[0]，于是 `COPY pyproject.toml
    README.md ./` 里的 README.md 被当成目标漏掉了 —— 校验器自己出了假阳性。
    """
    out: list[str] = []
    for line in docker_text.splitlines():
        line = line.strip()
        if not line.upper().startswith("COPY "):
            continue
        parts = [p for p in line.split()[1:] if not p.startswith("--")]
        if len(parts) >= 2:
            out.extend(parts[:-1])          # 最后一个是目标 dst
    return out


def pytest_assets(include_top: bool = False) -> list[str]:
    """找出代码里**会在运行时读取**的仓库内文件。

    判据：career_loop/ 的源码（排除 tests）里出现 `"xxx/yyy"` 形式的字符串
    字面量，且这个路径相对仓库根确实存在。
    ——存在性过滤是关键：CLI 里还有一堆"用户稍后传进来的"示例路径，
    那些不是运行时依赖，靠这一层滤掉。

    这样以后新加一个默认读取的资源文件，不用记得手动同步任何清单，
    检查会自己发现 Dockerfile 没覆盖到它。
    """
    assets: set[str] = set()
    for py in sorted((ROOT / "career_loop").rglob("*.py")):
        rel = py.relative_to(ROOT).as_posix()
        if rel.startswith("career_loop/tests/") or rel.startswith("career_loop\\tests\\"):
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for m in re.finditer(r'"([A-Za-z_][\w.-]*/[\w./-]+)"', text):
            cand = m.group(1)
            if cand.startswith(("http://", "https://")):
                continue
            p = ROOT / cand
            if p.is_file() and cand != rel:
                assets.add(cand)
    if include_top:
        assets |= {"pyproject.toml", "README.md"}
    return sorted(assets)


def entrypoint_command(docker_text: str) -> str | None:
    m = re.search(r'ENTRYPOINT\s+\[\s*"([^"]+)"', docker_text)
    return m.group(1) if m else None


def declared_scripts(pyproject_text: str) -> set[str]:
    block = re.search(r"^\[project\.scripts\]\s*$(.*?)(?=^\[|\Z)",
                      pyproject_text, re.M | re.S)
    if not block:
        return set()
    return set(re.findall(r"^([\w.-]+)\s*=", block.group(1), re.M))


# --------------------------------------------------------------------------
# 检查
# --------------------------------------------------------------------------

def check(docker_text: str | None = None) -> list[str]:
    """返回问题清单；空列表 = 通过。"""
    docker_text = docker_text if docker_text is not None else DOCKERFILE.read_text(
        encoding="utf-8")
    problems: list[str] = []

    if "FROM " not in docker_text:
        return ["Dockerfile 里连 FROM 都没有"]

    # 1) COPY 的源必须存在
    for src in parse_copy_sources(docker_text):
        # 只查仓库内的相对源；`COPY --from=builder /x /y` 这种先跳过
        if src.startswith("/") or src.startswith("--"):
            continue
        if not (ROOT / src).exists():
            problems.append(f"COPY 的源不存在：{src}")

    copied = {s.strip("/") for s in parse_copy_sources(docker_text)}

    # 2) pip 安装必需文件必须先 COPY（`pip install .` 要读 pyproject + README）
    for need in ("pyproject.toml", "README.md"):
        if need not in copied:
            problems.append(
                f"`pip install .` 需要 {need}，但它没被 COPY 进镜像")

    # 3) 运行时读取的仓库内文件，其顶层目录必须被 COPY
    for asset in pytest_assets():
        top = asset.split("/")[0]
        if top not in copied:
            problems.append(
                f"代码会读 `{asset}`，但 Dockerfile 没有 COPY `{top}/` "
                f"——镜像里会缺这个文件，容器跑对应命令才炸")

    # 4) ENTRYPOINT 必须是 pyproject 里声明过的 console script
    cmd = entrypoint_command(docker_text)
    if cmd is None:
        problems.append("Dockerfile 没有 ENTRYPOINT")
    else:
        scripts = declared_scripts((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        if scripts and cmd not in scripts:
            problems.append(
                f"ENTRYPOINT 是 `{cmd}`，但 pyproject 声明的入口是 {sorted(scripts)}"
                f"——镜像起来会 command not found")

    return problems


# --------------------------------------------------------------------------
# 自测
# --------------------------------------------------------------------------

SELF_TESTS: list[tuple[str, str, bool]] = [
    # (说明, 被改坏的 Dockerfile, 是否应该有报错)
    ("COPY 一个不存在的源", "COPY nonexistent.png ./x.png", True),
    ("忘了 COPY data/（eval 默认读它）", "COPY examples ./examples", False),
    ("ENTRYPOINT 命令名拼错", 'ENTRYPOINT ["careerloop"]', True),
    ("删掉 pyproject 的 COPY", "", False),
]


def self_test() -> int:
    """喂坏 Dockerfile 必须报错，好的必须过——一个只会点头的校验器没有用。"""
    good = DOCKERFILE.read_text(encoding="utf-8")
    ok = True

    def run(text: str) -> list[str]:
        return check(text)

    cases = [
        ("原样 Dockerfile 必须通过", good, False),
        ("COPY 不存在的源要报错",
         good + "\nCOPY docs/nope.md /tmp/nope.md\n", True),
        ("去掉 data/ 的 COPY 要报错",
         good.replace("COPY data ./data\n", ""), True),
        ("去掉 examples/ 的 COPY 要报错",
         good.replace("COPY examples ./examples\n", ""), True),
        ("ENTRYPOINT 拼错要报错",
         good.replace('ENTRYPOINT ["career-loop"]', 'ENTRYPOINT ["careerloop"]'), True),
        ("去掉 README.md 的 COPY 要报错",
         good.replace("COPY pyproject.toml README.md ./", "COPY pyproject.toml ./"), True),
    ]
    for name, text, expect_problem in cases:
        got = bool(run(text))
        passed = got == expect_problem
        ok = ok and passed
        print(f"  {name:34s} {'✓' if passed else '✗'}"
              f"（{'报错' if got else '通过'}）")

    # 追加一个"更多坏情况"的兜底：整份 Dockerfile 空掉必须报错
    empty = bool(run(""))
    print(f"  {'Dockerfile 为空要报错':34s} {'✓' if empty else '✗'}")
    ok = ok and empty
    print(f"\n自测 {'通过' if ok else '失败'}（{len(cases) + 1} 例）")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true", help="跑校验器自身的 A/B 自测")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    problems = check()
    if problems:
        print("Dockerfile 静态校验未通过：")
        for p in problems:
            print(f"  ✗ {p}")
        print("\n提示：这只覆盖静态部分（路径/入口），容器内能不能跑要靠 CI 的 docker build。")
        return 1
    print("Dockerfile 静态校验通过 ✓（COPY 路径齐全、入口与 pyproject 一致）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
