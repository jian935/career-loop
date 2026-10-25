# -*- coding: utf-8 -*-
"""career-loop 免安装一键演示（不接大模型、不落库，纯跑匹配引擎）。

用法：
    python scripts/demo_cli.py

会从 examples/ 读取一份示例经历和若干示例 JD，演示：
  1) 单个 JD 的匹配分 + 逐项能力达成情况（full / partial / missing）
  2) 一份经历 × 多个 JD 的排序（先投哪个）
  3) 补上哪几项能力，能解锁最多 JD（性价比最高的缺口）

全程离线、无需 API Key、不产生任何数据文件。评委/用户一键即可看到核心能力。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from career_loop import matching  # noqa: E402
from career_loop import recommend as rec_mod  # noqa: E402

PROFILE = ROOT / "examples" / "profile_me.md"
JD_DIR = ROOT / "examples" / "jds"

STATUS_CN = {"full": "✓ 满足", "partial": "◐ 部分", "missing": "✗ 缺失"}


def _status(matches: dict, key: str) -> str:
    m = matches.get(key)
    return m.status if m else "missing"


def main() -> int:
    if not PROFILE.exists():
        print("找不到示例经历：", PROFILE)
        return 1
    profile = PROFILE.read_text(encoding="utf-8")
    jds = []
    for f in sorted(JD_DIR.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        jds.append((matching.extract_title(text), text))
    if not jds:
        print("examples/jds 下没有示例 JD")
        return 1

    focus_title, focus_text = jds[0]

    print("=" * 64)
    print("DEMO 1 · 单个 JD 匹配（规则基线，无大模型）")
    print("=" * 64)
    reqs, _ = matching.extract_requirements(focus_text, None)
    matches, mode = matching.match(reqs, profile, None)
    score = matching.score(reqs, matches)
    print(f"岗位：{focus_title}　匹配分 {score:.1f}%　模式 {mode}　能力项 {len(reqs)}")
    for r in reqs:
        st = _status(matches, r.key)
        print(f"  {STATUS_CN.get(st, st):<8} [{r.weight}] {r.label}")
    missing = [r.label for r in reqs if _status(matches, r.key) in ("missing",)]
    print(f"  缺口（缺失项）：{', '.join(missing) if missing else '无'}")

    print("\n" + "=" * 64)
    print("DEMO 2 · 一份经历 × 多个 JD（先投哪个）")
    print("=" * 64)
    ranked = rec_mod.recommend(profile, jds, None)
    for i, r in enumerate(ranked, 1):
        print(f"  {i}. {r.score:>5.1f}%  {r.title}")

    print("\n" + "=" * 64)
    print("DEMO 3 · 补哪项能力，解锁最多 JD（性价比缺口）")
    print("=" * 64)
    lev = rec_mod.gap_leverage(profile, jds, 0.7, None)
    shown = 0
    for item in lev:
        if item["gained"] == 0:
            continue
        shown += 1
        if shown > 5:
            break
        print(f"  + {item['label']}：可多解锁 {item['gained']} 个 JD")
        for t in item["jds"][:3]:
            print(f"      · {t}")
    if shown == 0:
        print("  （当前缺口已较均衡，没有「补一项就能跨线」的短板。）")
    print("\n完成。真实使用见 README『快速开始』（命令行）或打开 docs/index.html（网页）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
