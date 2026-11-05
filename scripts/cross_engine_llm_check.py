# -*- coding: utf-8 -*-
"""跨引擎一致性检验（LLM 族识别部分）：Python vs 网页 JS。

背景
----
v0.8.20 起网页 demo 也能用 LLM 判岗位族。网页的 `normalizeFamilies` /
`blendFamilies` 是 Python `career_loop.matching.family_llm` 的手写移植版——
两边只要有细微差异，网页判出来的族就和 CLI 不是同一件事，
「86.0% → 93.4%」这个对比就失去意义。

本脚本做三件事：
1. **归一化一致**：同一批（含边界）输入喂给两边的归一化函数，比对输出集合与顺序；
2. **混合一致**：同一批 (模型族, 规则族) 喂给两边的 blend 函数，比对输出；
3. **提示词逐字一致**：网页里的 FAMILY_PROMPT 必须与 Python 的
   `family_system_prompt()` 完全相同（封闭集不同 = 判的不是同一件事）。

用法：
    python scripts/cross_engine_llm_check.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from career_loop.matching.family_llm import (           # noqa: E402
    _normalize, family_system_prompt,
)

def _node() -> str:
    """在 PATH 里找 node。

    以前这里硬编码了本机托管路径（本地 user 目录下的 `.workbuddy/binaries/node/.../node.exe`），
    那条路径只在一台机器上成立：GitHub Actions 的 runner 上必然找不到。
    改成先查 PATH——runner 自带 node，本机 WorkBuddy 的 node 也在 PATH 里。
    """
    found = shutil.which("node")
    if found:
        return found
    print("[error] 找不到 node（CI 的 ubuntu/windows runner 自带 node）", file=sys.stderr)
    raise SystemExit(1)

# 归一化的边界输入：合法族 / 中文名 / 大小写 / 重复 / 非法 key / 非字符串 /
# ai_* 子族触发父族推导 / 空输入 / 非列表
NORM_CASES = [
    ["service"],
    ["客服"],
    ["service", "service"],
    ["SERVICE"],
    ["  sales  "],
    ["ai_nlp"],
    ["ai_nlp", "ai"],
    ["ai", "ai_nlp"],
    ["nonexistent_family"],
    ["service", 123, None, True],
    [],
    "not-a-list",
    {"a": 1},
    [None],
    ["客服", "sales", "不存在的族"],
    ["project_mgmt", "ai_cv", "营销", "marketing"],
]

# blend 的输入：(模型族列表, 规则族列表)
BLEND_CASES = [
    (["service"], ["service", "sales"]),
    (["ai_nlp"], ["ai_nlp", "ai", "backend"]),
    ([], ["sales", "hr"]),
    (["sales"], []),
    (["service"], ["hr"]),
    ([], []),
]


def _load_js() -> str:
    html_path = os.path.join(ROOT, "docs", "index.html")
    with open(html_path, encoding="utf-8") as fh:
        html = fh.read()
    m = re.search(r"<script>(.*)</script>", html, re.S)
    if not m:
        print("[error] 没在 docs/index.html 里找到 <script>", file=sys.stderr)
        raise SystemExit(1)
    return m.group(1)


STUB = """
const store={};
function makeEl(id){return{id,value:"",textContent:"",innerHTML:"",className:"",children:[],style:{},
  appendChild(c){this.children.push(c);},removeChild(c){const i=this.children.indexOf(c); if(i>=0)this.children.splice(i,1);},
  append(){},addEventListener(){},querySelector(){return makeEl("q");},remove(){},click(){},
  classList:{add(){},remove(){},toggle(){}}};}
global.document={getElementById:(id)=>store[id]||(store[id]=makeEl(id)),createElement:(t)=>makeEl(t),
  body:{appendChild(){}}};
if(!global.URL.createObjectURL){ global.URL.createObjectURL=()=>"blob:x"; global.URL.revokeObjectURL=()=>{}; }
global.location={search:""};global.Blob=function(){};
global.localStorage={_d:{},getItem(k){return this._d[k]||null;},setItem(k,v){this._d[k]=String(v);}};
global.setTimeout=()=>{};
global.fetch=()=>Promise.reject(new Error("test: no network"));
"""

DRIVER = """
const normCases = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));
const blendCases = JSON.parse(require("fs").readFileSync(process.argv[3], "utf8"));
const out = {
  norm: normCases.map(c => normalizeFamilies(c)),
  blend: blendCases.map(([a,b]) => blendFamilies(a,b)),
  prompt: FAMILY_PROMPT,
  keys: FAMILY_KEYS
};
require("fs").writeFileSync(process.argv[4], JSON.stringify(out));
"""


def run_node(js: str) -> dict:
    with tempfile.TemporaryDirectory() as td:
        js_path = os.path.join(td, "page.js")
        in_norm = os.path.join(td, "norm.json")
        in_blend = os.path.join(td, "blend.json")
        out_path = os.path.join(td, "out.json")
        with open(js_path, "w", encoding="utf-8") as fh:
            fh.write(STUB + js + "\n" + DRIVER)
        with open(in_norm, "w", encoding="utf-8") as fh:
            json.dump(NORM_CASES, fh, ensure_ascii=False)
        with open(in_blend, "w", encoding="utf-8") as fh:
            json.dump(BLEND_CASES, fh, ensure_ascii=False)
        res = subprocess.run([_node(), js_path, in_norm, in_blend, out_path],
                             capture_output=True, text=True, encoding="utf-8")
        if res.returncode != 0:
            print(res.stdout[-2000:], file=sys.stderr)
            print(res.stderr[-2000:], file=sys.stderr)
            raise SystemExit("Node 执行失败")
        with open(out_path, encoding="utf-8") as fh:
            return json.load(fh)


def main() -> int:
    node_out = run_node(_load_js())

    print("=" * 60)
    print("跨引擎一致性（LLM 族识别）：Python vs 网页 JS")
    print("=" * 60)

    # 1) 提示词逐字一致
    py_prompt = family_system_prompt()
    js_prompt = node_out["prompt"]
    prompt_same = py_prompt == js_prompt
    print(f"提示词逐字一致    ：{'✓' if prompt_same else '✗'}"
          f"（{len(py_prompt)} 字符）")
    if not prompt_same:
        print("  ✗ 网页的 FAMILY_PROMPT 与 Python 不一致 —— 跑 python scripts/sync_web_vocab.py")

    # 2) 归一化一致
    norm_bad = []
    for i, case in enumerate(NORM_CASES):
        py_out = _normalize(case)
        js_out = node_out["norm"][i]
        if py_out != js_out:
            norm_bad.append((i, case, py_out, js_out))
    print(f"归一化一致        ：{len(NORM_CASES) - len(norm_bad)}/{len(NORM_CASES)}")
    for i, case, py_out, js_out in norm_bad:
        print(f"  ✗ #{i} 输入={case!r}\n      py={py_out}\n      js={js_out}")

    # 3) blend 一致
    blend_bad = []
    for i, (llm_fams, rule_fams) in enumerate(BLEND_CASES):
        py_out = list(llm_fams) + [f for f in rule_fams if f not in llm_fams]
        js_out = node_out["blend"][i]
        if py_out != js_out:
            blend_bad.append((i, (llm_fams, rule_fams), py_out, js_out))
    print(f"混合（blend）一致 ：{len(BLEND_CASES) - len(blend_bad)}/{len(BLEND_CASES)}")
    for i, case, py_out, js_out in blend_bad:
        print(f"  ✗ #{i} 输入={case!r}\n      py={py_out}\n      js={js_out}")

    # 4) 合法族 key 集合一致
    from career_loop.matching.schema import DOMAIN_PACKS
    py_keys = list(DOMAIN_PACKS) + ["ai"]
    keys_same = py_keys == node_out["keys"]
    print(f"合法族 key 集合一致：{'✓' if keys_same else '✗'}"
          f"（{len(py_keys)} 个）")
    if not keys_same:
        print(f"  仅 py 有: {sorted(set(py_keys) - set(node_out['keys']))}")
        print(f"  仅 js 有: {sorted(set(node_out['keys']) - set(py_keys))}")

    ok = prompt_same and not norm_bad and not blend_bad and keys_same
    print("\n结论：" + ("两侧 LLM 族识别逻辑完全一致 ✓" if ok else "存在差异，需要继续对齐 ✗"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
