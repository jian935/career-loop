# -*- coding: utf-8 -*-
"""把 Python 词表同步进 docs/index.html（浏览器端 demo）。

网页 demo 是单文件、零依赖的，因此需要一份 JS 版词表。手工复制会漂移，
所以改成从 career_loop/matching/schema.py 自动生成。

用法：
    python scripts/sync_web_vocab.py          # 同步
    python scripts/sync_web_vocab.py --check  # 只检查是否漂移（CI 用）
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from career_loop.cli import DOMAIN_CN                      # noqa: E402
from career_loop.matching.boilerplate import BOILERPLATE_PATTERNS  # noqa: E402
from career_loop.matching.family_llm import family_system_prompt     # noqa: E402
from career_loop.matching.schema import (                  # noqa: E402
    AI_CORE_KW, CONTEXT_REQUIRED, DOMAIN_PACKS, GENERAL_DIMS, TAXONOMY,
)

HTML = ROOT / "docs" / "index.html"
BEGIN = "/* VOCAB:BEGIN"
END = "/* VOCAB:END */"
CN_RE = re.compile(r"const DOMAIN_CN=\{[^\n]*\};")


def js_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def render_dims(table: dict, indent: str = "") -> str:
    lines = []
    for key, spec in table.items():
        kw = ",".join(js_str(k) for k in spec["kw"])
        lines.append(f'{indent}{key}:{{label:{js_str(spec["label"])}, kw:[{kw}]}},')
    return "\n".join(lines)


def render_packs() -> str:
    lines = []
    for name, pack in DOMAIN_PACKS.items():
        body = render_dims(pack, indent="    ")
        lines.append(f"  {name}:{{\n{body}\n  }},")
    return "\n".join(lines)


def render_context() -> str:
    """渲染过泛词的语境约束表（Python ↔ 网页必须一致，否则两边结果不同）。"""
    lines = []
    for key, words in CONTEXT_REQUIRED.items():
        ws = ",".join(js_str(w) for w in words)
        lines.append(f'  {js_str(key)}:[{ws}],')
    return "\n".join(lines)


def render_ai_core() -> str:
    """渲染 AI 父族硬核词表（v0.8.14 起 Python 侧 detect_domains 用它判 ai 族）。"""
    ws = ",".join(js_str(k) for k in AI_CORE_KW)
    return f"const AI_CORE_KW = [{ws}];"


def render_boilerplate() -> str:
    """渲染平台样板清除函数（v0.8.14 起两端都先剥样板再匹配）。

    模式从 career_loop/matching/boilerplate.py 自动生成，避免两端漂移。
    """
    pats = ", ".join(f"/{p.pattern}/g" for p in BOILERPLATE_PATTERNS)
    return (
        f"const BOILERPLATE_PATTERNS = [{pats}];\n"
        'function stripBoilerplate(t){ if(!t) return t; '
        'for(const re of BOILERPLATE_PATTERNS){ t = t.replace(re, ""); } return t; }'
    )


def render_family_prompt() -> str:
    """渲染 LLM 族识别的封闭集提示词（v0.8.20 起网页端也能用模型判族）。

    提示词必须与 Python 侧**逐字一致**——否则网页判的族和 CLI 判的族不是同一件事，
    两端口径漂移会让「93.4%」这个数字失去意义。
    """
    return f"const FAMILY_PROMPT = {js_str(family_system_prompt())};"


def render_family_keys() -> str:
    """合法族 key 集合（= DOMAIN_PACKS 的键 + ai 父族），与 Python 的 _normalize 同源。"""
    keys = list(DOMAIN_PACKS) + ["ai"]
    return f"const FAMILY_KEYS = [{','.join(js_str(k) for k in keys)}];"


def render_daily_rules() -> str:
    """截止日抽取规则（线索词 / 「招满为止」 / 两条日期正则）——给网页的 daily 用。

    **pattern 本身也导出**，而不是在网页里手写一份：手写必漂移，
    而漂移的表现是「网页说 11 月 30 截止、CLI 说没截止」，用户当场失去信任。
    注意两边都用同一个 pattern，所以 daily.py 里的正则必须避开 JS 不支持的
    语法（lookbehind 在 Safari 16.4 之前会整段崩）。
    """
    from career_loop.daily import (
        DEADLINE_CUES, OPEN_ENDED, _DATE_FULL, _DATE_SHORT,
    )

    cues = ",".join(js_str(c) for c in DEADLINE_CUES)
    open_ended = ",".join(js_str(c) for c in OPEN_ENDED)
    return (
        f"const DAILY_CUES = [{cues}];\n"
        f"const DAILY_OPEN_ENDED = [{open_ended}];\n"
        f"const RE_DATE_FULL = {js_str(_DATE_FULL.pattern)};\n"
        f"const RE_DATE_SHORT = {js_str(_DATE_SHORT.pattern)};"
    )


def render_occupations() -> str:
    """职业分类覆盖面的**计算结果**（不是原始数据）——给网页的对账表用。

    这里刻意导出**算好的** summary 而不是让网页自己数：算两次的必然结果是
    慢慢漂移，而 Python 是唯一的计算方（`taxonomy_cn.coverage_summary`）。
    网页侧只负责渲染。
    """
    from career_loop.matching.taxonomy_cn import (
        MIDS_IN_DICTIONARY_2022, coverage_matrix, coverage_summary,
    )
    rows = []
    for r in coverage_matrix():
        packs = ",".join(js_str(p) for p in r["packs"])
        rows.append(
            f'  {{code:{js_str(r["code"])},label:{js_str(r["label"])},'
            f'mapped:{r["mid_mapped"]},total:{r["mid_total"]},packs:[{packs}]}},')
    s = coverage_summary()
    # 网页的第三个 metric 卡要渲染"职业大类"个数，所以 big_classes 必须一起导出。
    # 曾经漏过它 —— 网页直接渲染出 "undefined"，而当时的跨引擎检查只比了
    # 另外五个 key，所以没抓到。**凡是网页会读的 key，这里一个都不能少。**
    summary = (
        f'  listed_total:{s["listed_total"]}, listed_mapped:{s["listed_mapped"]},'
        f' dictionary_total:{s["dictionary_total"]},'
        f' big_classes:{s["big_classes"]},'
        f' completeness:{round(s["completeness"], 4)}, breadth:{round(s["breadth"], 4)}'
    )
    return (
        "const OCC_COVERAGE = [\n" + "\n".join(rows) + "\n];\n"
        f"const OCC_SUMMARY = {{\n{summary}\n}};\n"
        f"const OCC_DICTIONARY_VINTAGE = {js_str(str(MIDS_IN_DICTIONARY_2022))};"
    )


def build_block() -> str:
    return (
        "/* VOCAB:BEGIN 由 scripts/sync_web_vocab.py 从 career_loop/matching/schema.py 自动生成，勿手改 */\n"
        f"const TAXONOMY = {{\n{render_dims(TAXONOMY)}\n}};\n"
        f"const GENERAL_DIMS = {{\n{render_dims(GENERAL_DIMS)}\n}};\n"
        f"const DOMAIN_PACKS = {{\n{render_packs()}\n}};\n"
        f"const CONTEXT_REQUIRED = {{\n{render_context()}\n}};\n"
        f"{render_ai_core()}\n"
        f"{render_boilerplate()}\n"
        f"{render_family_prompt()}\n"
        f"{render_family_keys()}\n"
        f"{render_daily_rules()}\n"
        f"{render_occupations()}\n"
        "/* VOCAB:END */\n"
    )


def build_cn() -> str:
    items = ",".join(f"{k}:{js_str(v)}" for k, v in DOMAIN_CN.items())
    return f"const DOMAIN_CN={{{items}}};"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检查是否漂移")
    args = ap.parse_args()

    src = HTML.read_text(encoding="utf-8")
    if BEGIN not in src or END not in src:
        print("index.html 里找不到 VOCAB:BEGIN / VOCAB:END 标记，跳过。")
        return 1

    i = src.index(BEGIN)
    j = src.index(END) + len(END) + 1
    new_block = build_block()
    new_src = src[:i] + new_block + src[j:]

    if not CN_RE.search(new_src):
        print("index.html 里找不到 const DOMAIN_CN 定义，跳过。")
        return 1
    new_src = CN_RE.sub(lambda m: build_cn(), new_src, count=1)

    if args.check:
        if new_src == src:
            print("OK 网页词表与 Python 词表一致。")
            return 0
        print("DRIFT 网页词表已漂移，请运行 python scripts/sync_web_vocab.py")
        return 1

    if new_src == src:
        print("已是最新，无需改动。")
        return 0
    HTML.write_text(new_src, encoding="utf-8")
    print(f"已同步 docs/index.html：{len(DOMAIN_PACKS)} 个岗位族、"
          f"{sum(len(v) for v in DOMAIN_PACKS.values())} 个族内能力项。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
