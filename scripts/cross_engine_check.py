# -*- coding: utf-8 -*-
"""跨引擎一致性检验：Python 引擎 vs 网页 JS 引擎。

为什么要这个脚本：
网页 demo 里的 JS 引擎是 Python 引擎的「手写移植版」。两边只要有细微差异，
评委在网页上看到的匹配结果就会和 CLI 不一样——这对一个主打「可证伪」的项目是致命的。
所以用**同一批真实中文 JD + 同一批英文 JD** 跑两边，逐条比对抽取结果。

做法：
1. 用 Node 跑网页里的 parseJD（从 docs/index.html 抽出 JS，在 Node 里执行）；
2. 用 Python 跑 career_loop.matching.extract_requirements；
3. 比对：(a) 能力项数量、(b) 命中的 key 集合、(c) custom 项数量。

用法：
  python scripts/cross_engine_check.py [--csv <中文 JD csv>] [--limit N]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from career_loop.matching.extract import extract_requirements

NODE = r"C:\Users\llj12\.workbuddy\binaries\node\versions\22.22.2-6\node.exe"

DEFAULT_CSV = os.path.join(ROOT, "data", "calibration", "final_outcomes_202609.csv")


def _load_js() -> str:
    """从 docs/index.html 抽出 <script> 内容。"""
    html_path = os.path.join(ROOT, "docs", "index.html")
    with open(html_path, encoding="utf-8") as fh:
        html = fh.read()
    m = re.search(r"<script>(.*)</script>", html, re.S)
    if not m:
        print("[error] 没在 docs/index.html 里找到 <script>", file=sys.stderr)
        raise SystemExit(1)
    return m.group(1)


def _run_node(js: str, texts: list[str]) -> list[dict]:
    """在 Node 里跑网页的 parseJD，返回每条的抽取结果。"""
    stub = """
const store={};
function makeEl(id){return{id,value:"",textContent:"",innerHTML:"",className:"",children:[],style:{},
  appendChild(c){this.children.push(c);},removeChild(c){const i=this.children.indexOf(c); if(i>=0)this.children.splice(i,1);},
  append(){},addEventListener(){},querySelector(){return makeEl("q");},remove(){},click(){},
  classList:{add(){},remove(){},toggle(){}}};}
global.document={getElementById:(id)=>store[id]||(store[id]=makeEl(id)),createElement:(t)=>makeEl(t),
  body:{appendChild(){}}};
// 注意：不要覆盖全局 URL —— Node 内置的 URL 是类，网页代码里的
// URL.createObjectURL 只是导出用；这里只补方法，不换掉整个类。
if(!global.URL.createObjectURL){ global.URL.createObjectURL=()=>"blob:x"; global.URL.revokeObjectURL=()=>{}; }
global.location={search:""};global.Blob=function(){};
global.localStorage={_d:{},getItem(k){return this._d[k]||null;},setItem(k,v){this._d[k]=String(v);}};
global.setTimeout=()=>{};
"""
    driver = """
const cases = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));
const out = cases.map(t => {
  const reqs = parseJD(t);
  return {
    keys: reqs.map(r => r.key),
    labels: reqs.map(r => r.label),
    weights: reqs.map(r => r.weight),
    custom: reqs.filter(r => r.custom).length,
    quotes: reqs.map(r => r.quote)
  };
});
require("fs").writeFileSync(process.argv[3], JSON.stringify(out));
"""
    with tempfile.TemporaryDirectory() as td:
        js_path = os.path.join(td, "page.js")
        drv_path = os.path.join(td, "driver.js")
        in_path = os.path.join(td, "in.json")
        out_path = os.path.join(td, "out.json")
        with open(js_path, "w", encoding="utf-8") as fh:
            fh.write(stub + js + "\n" + driver)
        with open(drv_path, "w", encoding="utf-8") as fh:
            fh.write(driver)
        with open(in_path, "w", encoding="utf-8") as fh:
            json.dump(texts, fh, ensure_ascii=False)
        res = subprocess.run([NODE, js_path, in_path, out_path],
                             capture_output=True, text=True, encoding="utf-8")
        if res.returncode != 0:
            print(res.stdout[-2000:], file=sys.stderr)
            print(res.stderr[-2000:], file=sys.stderr)
            raise SystemExit("Node 执行失败")
        with open(out_path, encoding="utf-8") as fh:
            return json.load(fh)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=DEFAULT_CSV, help="含 jd_text 列的 CSV")
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    texts: list[str] = []
    if os.path.exists(args.csv):
        with open(args.csv, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                t = row.get("jd_text") or ""
                if t.strip():
                    texts.append(t)
                if len(texts) >= args.limit:
                    break
    # 附一条英文 JD，验证英文降噪与分节也一致
    texts.append(
        "MINIMUM EDUCATION\nBachelor's degree required.\n"
        "ESSENTIAL DUTIES\nManage a team of 5-25 executive consultants in marketing.\n"
        "APPLY HERE\nHTTPS://WWW.INDEED.COM/JOB/X-123"
    )
    if not texts:
        print("没有可用的 JD 文本", file=sys.stderr)
        return 1

    node_out = _run_node(_load_js(), texts)

    total = 0
    same_set = 0
    same_count = 0
    same_custom = 0
    same_weight = 0
    diffs: list[tuple[int, dict, dict]] = []

    for i, t in enumerate(texts):
        py_reqs = extract_requirements(t, None)[0]
        # custom 项的 key 是内容哈希（Python 用 MD5、JS 用 djb2），
        # 只是个内部标识符、不影响任何用户可见结果，所以按 quote 归一化再比。
        py_keys = sorted(("custom:" + r.quote) if r.key.startswith("custom:") else r.key
                         for r in py_reqs)
        py_custom = sum(1 for r in py_reqs if r.key.startswith("custom:"))
        py_w = {("custom:" + r.quote) if r.key.startswith("custom:") else r.key: r.weight
                for r in py_reqs}
        js = node_out[i]
        js_keys = sorted(("custom:" + q) if k.startswith("custom:") else k
                          for k, q in zip(js["keys"], js["quotes"]))
        js_custom = js["custom"]
        js_w = {("custom:" + q) if k.startswith("custom:") else k: w
                for k, q, w in zip(js["keys"], js["quotes"], js["weights"])}

        total += 1
        # 比集合而非序列：Python 按 weight 降序输出，JS 按插入顺序，
        # 顺序差异不算行为不一致。
        if set(py_keys) == set(js_keys):
            same_set += 1
        if len(py_keys) == len(js_keys):
            same_count += 1
        if py_custom == js_custom:
            same_custom += 1
        if py_w == js_w:
            same_weight += 1
        else:
            diffs.append((i, {"keys": py_keys, "custom": py_custom,
                               "n": len(py_keys), "w": py_w},
                          {"keys": js_keys, "custom": js_custom,
                           "n": len(js_keys), "w": js_w}))

    print("=" * 60)
    print("跨引擎一致性：Python 引擎 vs 网页 JS 引擎")
    print("=" * 60)
    print(f"样本：{total} 条（真实中文 JD + 1 条英文 JD）")
    print(f"  能力项集合一致  ：{same_set}/{total}  ({same_set / total * 100:.1f}%)")
    print(f"  能力项数量一致  ：{same_count}/{total}  ({same_count / total * 100:.1f}%)")
    print(f"  custom 数量一致 ：{same_custom}/{total}  ({same_custom / total * 100:.1f}%)")
    print(f"  每项权重完全一致 ：{same_weight}/{total}  ({same_weight / total * 100:.1f}%)")

    if diffs:
        print(f"\n不一致的条目（前 5 条）：")
        for i, py, js in diffs[:5]:
            only_py = set(py["keys"]) - set(js["keys"])
            only_js = set(js["keys"]) - set(py["keys"])
            print(f"  #{i}  n={py['n']}/{js['n']}  custom={py['custom']}/{js['custom']}")
            if only_py:
                print(f"    仅 Python 有: {sorted(only_py)}")
            if only_js:
                print(f"    仅 JS 有    : {sorted(only_js)}")
            for k in sorted(set(py["w"]) & set(js["w"])):
                if py["w"][k] != js["w"][k]:
                    print(f"    权重不同 {k}: py={py['w'][k]} js={js['w'][k]}")

    ok = same_set == total and same_weight == total
    print("\n结论：" + ("两侧抽取结果完全一致 ✓" if ok else "存在差异，需要继续对齐 ✗"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
