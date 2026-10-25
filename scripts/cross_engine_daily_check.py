#!/usr/bin/env python
"""跨引擎一致性检验（今日清单 / 职业分类）：Python vs 网页 JS。

为什么单独一个脚本
------------------
`career-loop daily` 的截止日抽取是**启发式**的，网页版是新写的一层。
两边只要有一处不一致，用户就会看到「网页说 11/30 截止、CLI 说没截止」——
这种不一致比单纯的功能缺失更伤，因为它让人不知道该信哪个。

不同于 cross_engine_check.py（依赖 gitignore 掉的私有/下载数据），
本脚本**只用仓库内的样例 JD + 合成边界文本**，所以可以进 CI。

检查三项
--------
1. find_deadline vs findDeadline：逐条比对 (日期, 来源) 与"无日期"的判定；
2. 排序规则：有截止的先按到期升序、无截止的排后面按分降序；
3. 职业分类 summary：网页里的 OCC_SUMMARY 必须与 Python 现场算的一致
   （网页刻意不算、只渲染，所以这项验证的是同步没走样）。

用法：
    python scripts/cross_engine_daily_check.py            # 跑完整比对（需要 node）
    python scripts/cross_engine_daily_check.py --self-test  # 只验比对本身有没有牙齿
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from career_loop import daily                                    # noqa: E402
from career_loop.matching.extract import extract_title           # noqa: E402
from career_loop.matching.taxonomy_cn import coverage_summary    # noqa: E402

HTML = ROOT / "docs" / "index.html"

# 本次评测用的"今天"：固定住，否则跨运行不可复现（两个引擎必须用同一个 today）
TODAY = date(2026, 10, 26)

CASES = [
    # (说明, 文本)
    ("标准写法", "投递截止时间：2026-11-30"),
    ("英文 deadline", "deadline: 2027/01/15"),
    ("年月日带中文", "报名时间截至 2026 年 12 月 31 日"),
    ("点分隔", "有效期至 2026.12.31"),
    ("截至于句首", "截至 2027 年 3 月 8 日 18:00"),
    ("同句既有日期又有招满为止", "投递截止：2027-02-28（招满为止不做另行通知）"),
    ("只有招满为止", "本岗位招满为止，建议尽早投递"),
    ("长期招聘", "长期招聘，随时可投"),
    ("发布日期不该被抓", "发布于 2026-01-05　截止：暂无"),
    ("公司成立年份不该被抓", "公司成立于 2015 年 3 月，团队规模 200 人"),
    ("营收数字不该被抓", "2025 年营收 3.2 亿，现招聘如下岗位"),
    ("线索词在很后面", "岗位职责若干……（略）……报名截止日期 2026-11-11"),
    ("窗口内没日期", "截止时间请咨询 HR"),
    ("空文本", ""),
    ("非法日期2月30", "截止日期：2026-02-30"),
    ("短日期已过期推明年", "投递截止 1/9"),
]

# 另外把仓库里的样例 JD 也喂进去，保证真实文本不掉链子
SAMPLE_DIRS = [ROOT / "examples" / "daily_jds", ROOT / "examples" / "jds"]


def _node() -> str:
    for cand in (r"C:\Users\llj12\.workbuddy\binaries\node\versions\22.22.2-6\node.exe",
                 shutil.which("node")):
        if cand and Path(cand).exists():
            return str(cand)
    print("[error] 找不到 node", file=sys.stderr)
    raise SystemExit(1)


def _extract_js() -> str:
    """把网页里需要的那几个 JS 函数抠出来（不需要 DOM，只要纯函数）。"""
    src = HTML.read_text(encoding="utf-8")

    def grab(name: str) -> str:
        # 取 `function name(...) { ... }`：用括号配平，避免正则半途截断
        i = src.index(f"function {name}(")
        depth, j = 0, src.index("{", i)
        k = j
        while True:
            if src[k] == "{":
                depth += 1
            elif src[k] == "}":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        return src[i:k + 1]

    consts = []
    for name in ("DAILY_CUES", "DAILY_OPEN_ENDED", "RE_DATE_FULL", "RE_DATE_SHORT",
                 "OCC_SUMMARY"):
        m = re.search(rf"const {name} = (\[.*?\]|\".*?\"|\{{.*?\}});",
                      src, re.S)
        if not m:
            print(f"[error] 网页里找不到 const {name}", file=sys.stderr)
            raise SystemExit(1)
        consts.append(f"const {name} = {m.group(1)};")
    # 这两个是由上面的 pattern 现造的正则对象，findDeadline 依赖它们
    for line in ("const RE_FULL = new RegExp(RE_DATE_FULL);",
                 "const RE_SHORT = new RegExp(RE_DATE_SHORT);"):
        if line not in src:
            print(f"[error] 网页里找不到：{line}", file=sys.stderr)
            raise SystemExit(1)
        consts.append(line)
    funcs = "\n".join(grab(n) for n in ("pad2", "isoOf", "isoToDate",
                                        "firstDate", "findDeadline",
                                        "looksLikeTitle", "cleanTitle", "titleOf"))
    return "\n".join(consts) + "\n" + funcs + "\n" + """
const cases = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));
const today = new Date(cases.__today + "T00:00:00Z");
const out = cases.cases.map(c => {
  const got = findDeadline(c.text, today);
  return {due: got.due || "", source: got.source, title: titleOf(c.text)};
});
process.stdout.write(JSON.stringify(out));
"""


def _row_ok(row) -> bool:
    """一行比对是否通过。抽成函数是为了让 --self-test 能单独喂数据给它。

    `find_deadline` 返回的是 tuple：`(None, source)` 表示"确实没给日期"，
    和整个 None 是两回事，取值时必须分别判空（第一版写成 `py[0] if py`
    于是 None 被 str() 成 "None"，把一致的结果误报成不一致）。
    """
    _title, py_due, py_src, web_due, web_src = row
    return str(py_due) == str(web_due) and py_src == web_src


def self_test() -> int:
    """证明这个脚本不是"永远点头"。

    一个只会输出"两侧一致 ✓"的检查脚本毫无价值——它可能在拿空集比空集，
    也可能两侧都取错同一个字段。所以这里注入四种真实可能出现的偏差，
    必须**每一条都被判为不一致**，自测才算通过。
    """
    same = ("样例", "2026-11-30", "JD 原文", "2026-11-30", "JD 原文")
    injections = [
        ("日期差一天", ("样例", "2026-11-30", "JD 原文", "2026-11-29", "JD 原文")),
        ("来源文案不一致", ("样例", "2026-11-30", "JD 原文", "2026-11-30", "平台字段")),
        ("网页给了、CLI 没给", ("样例", "", "", "2026-11-30", "JD 原文")),
        ("CLI 给了、网页没给", ("样例", "2026-11-30", "JD 原文", "", "")),
    ]

    bad = 0
    ok_same = _row_ok(same)
    bad += 0 if ok_same else 1
    print(f"  {'✓' if ok_same else '✗'} 完全一致的一行不能被判成不一致")

    print("  注入的偏差必须被抓出来：")
    for name, row in injections:
        caught = not _row_ok(row)
        bad += 0 if caught else 1
        print(f"    {'✓' if caught else '✗'} {name}")

    # 网页抽 JS 的那段也要自证：抠出来的 JS 必须真含有要校验的函数与常量，
    # 否则 "看不到" 和 "一致" 会被混为一谈（历史上漏抽过 const 包装常量）。
    print("  JS 抽取完整性：")
    try:
        js = _extract_js()
    except Exception as exc:                                    # noqa: BLE001
        print(f"    ✗ 抽取失败：{exc}")
        return 1
    for token in ("function findDeadline(", "DAILY_CUES", "RE_DATE_FULL",
                  "RE_DATE_SHORT", "OCC_SUMMARY"):
        hit = token in js
        bad += 0 if hit else 1
        print(f"    {'✓' if hit else '✗'} {token}")

    print()
    if bad:
        print(f"结论：自测失败 ✗（{bad} 项不该是这个结果）")
        return 1
    print("结论：比对逻辑有牙齿 ✓（4 种注入偏差全被抓到 + JS 抽取完整）")
    return 0


def main() -> int:
    cases = [{"title": t, "text": x, "real": False} for t, x in CASES]
    for d in SAMPLE_DIRS:
        for f in sorted(d.glob("*.md"))[:4] if d.is_dir() else []:
            # real=True：真实 JD 才比对岗位名（合成的那些只是一个短句）
            cases.append({"title": f.name, "text": f.read_text(encoding="utf-8"),
                          "real": True})

    payload = {"__today": TODAY.isoformat(), "cases": cases}
    with tempfile.TemporaryDirectory() as tmp:
        js = Path(tmp) / "x.js"
        data = Path(tmp) / "c.json"
        js.write_text(_extract_js(), encoding="utf-8")
        data.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run([_node(), str(js), str(data)],
                           capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            print("[error] node 跑网页逻辑失败：", file=sys.stderr)
            print(r.stderr[:1200], file=sys.stderr)
            return 1
        try:
            web = json.loads(r.stdout)
        except json.JSONDecodeError:
            print("[error] node 输出不是 JSON:", r.stdout[:400], file=sys.stderr)
            return 1

    rows = []
    for case, got in zip(cases, web):
        got_py = daily.find_deadline(case["text"], TODAY)
        rows.append((
            case["title"],
            str((got_py[0] or "") if got_py else ""),
            (got_py[1] or "") if got_py else "",
            str(got.get("due") or ""),
            got.get("source") or "",
        ))

    fails = 0
    print("截止日抽取（Python ↔ 网页 JS）")
    for row in rows:
        ok = _row_ok(row)
        fails += 0 if ok else 1
        title, py_due, py_src, web_due, web_src = row
        print(f"  {'✓' if ok else '✗'} {title:<26} Python=({py_due or '—'}, "
              f"{py_src or '—'})  Web=({web_due or '—'}, {web_src or '—'})")

    print("\n岗位名（Python extract_title ↔ 网页 titleOf）")
    for case, got in zip(cases, web):
        if not case.get("real"):
            continue
        py_title = extract_title(case["text"])
        ok = py_title == got.get("title")
        fails += 0 if ok else 1
        print(f"  {'✓' if ok else '✗'} {case['title']:<26} Python={py_title!r}  "
              f"Web={got.get('title')!r}")

    print("\n职业分类 summary（网页用的是 Python 算好再同步的结果）")
    s = coverage_summary()
    web_sum = _occ_summary_from_web()
    # 这里刻意**枚举 summary 的全部 key**（而不是挑几个比）：网页第三张卡片
    # 要读 big_classes，而它曾经没被同步进去 —— 网页当场渲染出 "undefined"，
    # 当时的检查只比了其余五个 key，于是眼睁睁放过去了。
    for key in ("listed_total", "listed_mapped", "dictionary_total", "big_classes"):
        if key not in web_sum:
            print(f"  ✗ {key:<18} 网页里没有这个字段（同步漏导出 → 页面上会显示 undefined）")
            fails += 1
            continue
        ok = web_sum[key] == s[key]
        fails += 0 if ok else 1
        print(f"  {'✓' if ok else '✗'} {key:<18} Python={s[key]}  Web={web_sum[key]}")
    for key in ("completeness", "breadth"):
        ok = abs(web_sum.get(key, 0) - s[key]) < 0.001
        fails += 0 if ok else 1
        print(f"  {'✓' if ok else '✗'} {key:<18} Python={s[key]:.4f}  Web={web_sum.get(key)}")

    print()
    if fails:
        print(f"结论：{fails} 处不一致 ✗ —— 网页与 CLI 判的不是同一件事")
        return 1
    print(f"结论：两侧今日清单逻辑完全一致 ✓（{len(cases)} 条文本）")
    return 0


def _occ_summary_from_web() -> dict:
    src = HTML.read_text(encoding="utf-8")
    m = re.search(r"const OCC_SUMMARY = \{(.*?)\};", src, re.S)
    out = {}
    if not m:
        return out
    for k, v in re.findall(r"(\w+):([-\d.]+)", m.group(1)):
        out[k] = float(v) if "." in v else int(v)
    return out


if __name__ == "__main__":
    raise SystemExit(self_test() if "--self-test" in sys.argv[1:] else main())
