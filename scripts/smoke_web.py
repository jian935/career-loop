#!/usr/bin/env python
"""网页 demo 端到端冒烟：把 docs/index.html 的 JS 在 Node 里整跑一遍。

为什么要有这个脚本
------------------
网页这次新增了「今日清单」和「职业分类对账」两块 UI，而在此之前，网页侧的
验证只到**纯函数**层面（cross_engine_check / cross_engine_daily_check 都只抠
出几个函数跑）。纯函数全绿，页面照样可以是坏的：

- `s.big_classes` 没被同步进 VOCAB → 第三张卡片直接渲染出 **undefined**
  （这次真的发生了，最后是被肉眼发现的，不是被 CI 发现的）；
- 导出按钮依赖的 Blob / click 路径没人走过；
- 新增的事件绑定写错 id，`el(...)` 返回的元素和 render 用的不是同一个。

所以这里**加载整段 `<script>`**，用最小 DOM 桩把每个入口函数真的点一遍，
并把导出的 Blob 内容抓回来检查长得对不对。

用法：
    python scripts/smoke_web.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "docs" / "index.html"

STUB = r"""
// ---------- 最小 DOM 桩 ----------
// 关键：**innerHTML 要真的解析**。`exportReport()` 是从 DOM 里把岗位名读回来的
// （querySelector(".job-title")），如果桩返回一个空节点，报告里全是空标题，
// 冒烟就会假装通过——所以这里塞了一个极简 HTML 解析器。
const __blobs = [];
const __alerts = [];

function makeEl(id){
  const e = {
    id, tagName:"DIV", value:"", className:"",
    href:"", download:"", selectedIndex:0, checked:false, options:[], children:[],
    style:{}, dataset:{}, _h:{},
    classList:{add(){},remove(){},toggle(){},contains(){return false;}},
    appendChild(c){this.children.push(c); return c;},
    removeChild(c){const i=this.children.indexOf(c); if(i>=0)this.children.splice(i,1);},
    append(...cs){this.children.push(...cs);},
    addEventListener(t,f){this._h[t]=f;},
    removeEventListener(){}, remove(){}, focus(){}, click(){},
    setAttribute(){}, removeAttribute(){}, closest(){return null;},
    insertAdjacentHTML(){}, scrollIntoView(){}, getContext(){return null;},
  };
  e._ownText = "";
  e._html = "";
  Object.defineProperty(e, "innerHTML", {
    get(){ return e._html; },
    set(v){
      e._html = String(v);
      e.children = [];
      const root = parseHTML(e._html);
      e.children = root.children;
      e._ownText = root._ownText || "";
    },
  });
  Object.defineProperty(e, "textContent", {
    get(){ return (e._ownText || "") + e.children.map(c => c.textContent).join(""); },
    set(v){ e._ownText = String(v); e.children = []; e._html = ""; },
  });
  e.querySelector = sel => query(e, sel);
  e.querySelectorAll = sel => { const r = []; walk(e, n => { if(match(n, sel)) r.push(n); }); return r; };
  return e;
}

const VOID_TAGS = {BR:1, IMG:1, INPUT:1, HR:1, META:1, LINK:1, SOURCE:1};
function parseHTML(html){
  const root = makeEl("__frag");
  const stack = [root];
  const re = /<(\/?)([a-zA-Z][\w-]*)((?:"[^"]*"|'[^']*'|[^>"'])*?)(\/?)>|([^<]+)/g;
  let m;
  while((m = re.exec(html))){
    if(m[5] != null){
      const parent = stack[stack.length-1];
      parent._ownText = (parent._ownText || "") + m[5];
      continue;
    }
    if(m[1] === "/"){ if(stack.length > 1) stack.pop(); continue; }
    const tag = m[2].toUpperCase();
    const attrs = m[3] || "";
    const e = makeEl("");
    e.tagName = tag;
    const cm = /class\s*=\s*"([^"]*)"/.exec(attrs);
    if(cm) e.className = cm[1];
    const im = /\sid\s*=\s*"([^"]*)"/.exec(attrs);
    if(im) e.id = im[1];
    stack[stack.length-1].appendChild(e);
    if(m[4] !== "/" && !VOID_TAGS[tag]) stack.push(e);
  }
  return root;
}
function walk(node, fn){ for(const c of node.children){ fn(c); walk(c, fn); } }
function match(n, sel){
  sel = sel.trim();
  if(sel[0] === ".") return String(n.className || "").split(/\s+/).indexOf(sel.slice(1)) >= 0;
  if(sel[0] === "#") return n.id === sel.slice(1);
  return n.tagName === sel.toUpperCase();
}
function query(node, sel){
  const multi = sel.split(/\s+/).filter(Boolean);
  let scope = [node];
  for(const part of multi){
    const next = [];
    for(const s of scope) walk(s, n => { if(match(n, part)) next.push(n); });
    scope = next;
    if(!scope.length) return null;
  }
  return scope[0] || null;
}

const __store = {};
global.document = {
  getElementById(id){ return __store[id] || (__store[id] = makeEl(id)); },
  createElement(t){ const e = makeEl(t); e.tagName = String(t).toUpperCase(); return e; },
  createTextNode(t){ const e = makeEl(""); e._ownText = String(t); return e; },
  querySelector(sel){ return query(makeEl("doc"), sel); },
  querySelectorAll(){ return []; },
  addEventListener(){}, body:makeEl("body"), head:makeEl("head"),
  documentElement:makeEl("html"),
};
global.alert = m => __alerts.push(String(m));
global.Blob = function(parts, opts){
  this.parts = parts; this.type = (opts && opts.type) || "";
  this.size = String(parts[0] == null ? "" : parts[0]).length;
  __blobs.push(this);
};
// Node 自带的 URL 是 class，别整个覆盖掉（fs shim 会挂），只补方法
global.URL.createObjectURL = b => { __blobs.push(b); return "blob:smoke"; };
global.URL.revokeObjectURL = () => {};
global.location = { search:"", hash:"", href:"http://x/" };
global.localStorage = {
  _d:{}, getItem(k){ return this._d[k] || null; },
  setItem(k,v){ this._d[k]=String(v); }, removeItem(k){ delete this._d[k]; },
};
global.navigator = { clipboard:{ writeText(){} } };
global.setTimeout = (fn) => 0;      // 延迟动作（revokeObjectURL 之类）不需要真跑
global.clearTimeout = () => {};
global.setInterval = () => 0;
global.requestAnimationFrame = (fn) => 0;
"""

DRIVER = r"""
const dueData = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));
const out = {steps: [], errors: [], blobs: [], alerts: __alerts};

function step(name, fn){
  try {
    const info = fn();
    out.steps.push({name, ok:true, info: info == null ? "" : String(info)});
    return info;
  } catch (e) {
    out.steps.push({name, ok:false, info:String(e && e.message || e)});
    out.errors.push(name + "\n    " + String(e && e.stack || e).split("\n").slice(0,3).join("\n    "));
    return null;
  }
}

function setv(id, v){ const e = el(id); e.value = v; return e; }
function lastBlobText(){
  const b = __blobs[__blobs.length - 1];
  if(!b) return "";
  if(b.parts) return b.parts.join("");
  return String(b);
}
function grabBlobText(){
  // Blob 与外部 mod 之后可能又 push 了别的东西，取最新一个有文本的
  for(let i=__blobs.length-1; i>=0; i--){
    const b = __blobs[i];
    const t = b && b.parts ? b.parts.join("") : "";
    if(t) return t;
  }
  return "";
}

// 1) 单 JD 匹配全流程
step("单 JD：parseJD → compute → render", () => {
  const reqs = parseJD(SAMPLE_A_JD);
  if(!reqs.length) throw new Error("parseJD 一条都没抽出来");
  const r = compute(SAMPLE_A_JD, SAMPLE_PROFILE);
  if(typeof r.base !== "number" || !(r.base >= 0)) throw new Error("分数不是数字：" + r.base);
  render(r);
  return `${reqs.length} 项 / ${r.base.toFixed(1)}%`;
});
step("每个示例都能跑（loadSample + run）", () => {
  let n = 0;
  for(let i=0;i<SAMPLES.length;i++){ loadSample(i); run(); n++; }
  return `${n} 个示例`;
});

// 2) 批量排序 → 今日清单 → 三种导出
//    刻意用**带截止日的真实样例 JD**（examples/daily_jds）：两条给了具体日期、
//    一条写「招满为止」。只用合成 JD 的话，这条链路的日期分支一次都不会被走到。
const batchProfileText = SAMPLE_PROFILE;
const batchJDText = dueData.jds.map(d => d.text).join("\n---\n");
step("批量排序 rankJobs", () => {
  const jobs = rankJobs(batchJDText, batchProfileText);
  if(jobs.length !== dueData.jds.length) throw new Error("岗位数不对：" + jobs.length);
  if(jobs[0].raw === undefined) throw new Error("rankJobs 不再带 raw（今日清单要拿它找截止日）");
  return jobs.map(j => j.title + " " + j.score.toFixed(1) + "%").join(" | ");
});
step("渲染排序结果", () => { renderRanking(batchJDText, batchProfileText); return "ok"; });
step("今日清单 renderDaily", () => {
  setv("batchJDs", batchJDText); setv("batchProfile", batchProfileText);
  renderDaily();
  const items = lastDaily;
  if(!items.length) throw new Error("今日清单是空的");
  if(items[0].due === undefined) throw new Error("缺 due 字段");
  const html = items.map(i => JSON.stringify(i)).join("");
  if(html.indexOf("undefined") >= 0) throw new Error("清单里出现了 undefined：" + html.slice(0,200));
  const withDue = items.filter(i => i.due).length;
  const openEnded = items.filter(i => !i.due && i.dueSource.indexOf("招满为止") >= 0).length;
  if(withDue < 2) throw new Error(`样例 JD 里 2 条写了具体日期，网页只抓到 ${withDue} 条`);
  if(openEnded < 1) throw new Error("「招满为止」那条没被识别成『JD 没给日期』");
  // 第一个无截止日的必须排在所有有截止日的**后面**，这就是「先到期先投」
  const firstWithoutDue = items.findIndex(i => !i.due);
  if(firstWithoutDue >= 0 && items.slice(firstWithoutDue).some(i => i.due))
    throw new Error("排序错了：无截止日的插在有截止日的前面");
  for(const it of items){
    if(/^[#*\s]/.test(it.title || ""))
      throw new Error("岗位名带了 Markdown 标题符号：" + JSON.stringify(it.title) +
                      "（应与 CLI 的 extract_title 一致，剥掉 #）");
  }
  return `${withDue} 条有日期 / ${openEnded} 条招满为止 → ` +
         items.map(i => (i.due || "无")).join(" < ");
});
for (const fmt of ["md", "csv", "ics"]) {
  step("导出今日清单 ." + fmt, () => {
    setv("dailyFmt", fmt);
    exportDaily();
    const t = grabBlobText();
    if(!t) throw new Error("导出内容是空的");
    if(fmt === "md" && t.indexOf("- [ ]") < 0) throw new Error("Markdown 里没有勾选框");
    if(fmt === "csv" && t.indexOf("\"") !== 0) throw new Error("CSV 首字符应该被引号包住");
    if(fmt === "ics"){
      if(t.indexOf("BEGIN:VCALENDAR") < 0) throw new Error("ICS 缺 VCALENDAR 头");
      if(t.indexOf("END:VCALENDAR") < 0) throw new Error("ICS 没闭合");
      if(t.indexOf("VTODO") < 0) throw new Error("ICS 里没有代办项");
      if(t.indexOf("DUE;VALUE=DATE:") < 0)
        throw new Error("ICS 里一条待办都没带上截止日——样例 JD 是有日期的");
    }
    if(t.indexOf("undefined") >= 0) throw new Error("导出内容出现 undefined：" + t.slice(0,160));
    return t.slice(0, 60).replace(/\r?\n/g, "\\n");
  });
}
step("导出 Markdown 报告（单 JD 那条链路）", () => {
  exportReport();
  const t = grabBlobText();
  if(!t) throw new Error("报告是空的");
  if(t.indexOf("**  —") >= 0)
    throw new Error("报告里的岗位名是空的（从 DOM 读标题那段没读到东西）");
  return t.slice(0, 60).replace(/\r?\n/g, "\\n");
});

step("导出 PDF：buildPrintHtml 自检（无 undefined/NaN）", () => {
  const sample = {
    daily:false,
    ranked:[{title:"AI 产品经理", score:"62.0%", due:"2026-11-30", gap:"补强：数据指标设计"}],
    industries:[{name:"产品", cov:"80%"}],
    single:{ base:62.0,
      reqs:[{label:"需求分析",status:"full"},{label:"数据分析",status:"partial"},{label:"项目管理",status:"missing"}],
      ups:[{label:"数据分析",old:62.0,newScore:71.3,delta:9.3}] }
  };
  const h = buildPrintHtml(sample);
  if(!h || h.length < 80) throw new Error("buildPrintHtml 输出太短：" + (h?h.length:0));
  if(h.indexOf("undefined") >= 0) throw new Error("打印报告出现 undefined");
  if(h.indexOf("NaN") >= 0) throw new Error("打印报告出现 NaN");
  if(h.indexOf("单岗位匹配报告") < 0 || h.indexOf("该投哪些") < 0) throw new Error("缺少关键标题");
  return "ok " + h.length + " 字符";
});

// 3) 其余模块
step("全行业适配 renderScan", () => { renderScan(batchProfileText); return "ok"; });
step("实习方向推荐 renderInternships", () => { renderInternships(batchProfileText); return "ok"; });
step("职业分类对账 renderOccupations", () => {
  renderOccupations();
  const body = el("occBody");
  if(!body.children.length) throw new Error("对账表一行都没有");
  const metrics = el("occMetrics").innerHTML;
  if(metrics.indexOf("undefined") >= 0)
    throw new Error("指标卡里出现 undefined（同步漏字段了）：" + metrics.slice(0,200));
  return `${body.children.length} 个大类 / 指标卡 ${metrics.length} 字符`;
});
step("中文抽取实验室 renderLab", () => {
  setv("labJD", SAMPLE_A_JD);
  renderLab();
  if(el("labTotal").textContent === "") throw new Error("labTotal 没写值");
  return "抽出 " + el("labTotal").textContent + " 项";
});
step("证据墙对比图 renderCnEn", () => { renderCnEn(); return "ok"; });
step("真实回流样例 renderRfSample", () => { renderRfSample(); return "ok"; });

// 4) 闭环校准：塞三条数据再导出
step("校准看板：记 3 条 → renderCalib → 导出 CSV", () => {
  // 注意：真实 <input> 的 .value 永远是字符串（calAdd 里会 .trim()），
  // 所以这里必须传字符串，不能偷懒传数字——桩顺着来会掩盖真实的取值方式。
  const rows = [["产品 A", "78", "replied"], ["产品 B", "55", "applied"],
                ["产品 C", "88", "offer"]];
  for(const [role, score, st] of rows){
    setv("calRole", role); setv("calScore", score); setv("calStatus", st);
    calAdd();
  }
  renderCalib();
  if(el("calN").textContent !== "3")
    throw new Error("记了 3 条但计数是 " + el("calN").textContent);
  calExport();
  const t = grabBlobText();
  if(!t) throw new Error("CSV 导出是空的");
  return `r=${el("calR").textContent}，导出 ${t.length} 字符`;
});

// 5) 着重检查渲染结果里没有 undefined / NaN —— 这是"漏同步"最常见的样子：
//    数据字典少导出一个字段，页面不报错，只是那个位置印着 undefined（或算百分比
//    得出 NaN）。两者都要扫，因为指标卡现在是「取字段 → 乘 100 → 拼接」。
step("整页渲染没印出 undefined / NaN", () => {
  const bad = [];
  for(const id of ["occMetrics", "occBody", "occHint", "rankHead", "labTotal",
                   "calN", "calR", "calRate", "industryList", "interns"]){
    const e = el(id);
    const txt = (e.innerHTML || "") + " " + (e.textContent || "");
    if(txt.indexOf("undefined") >= 0) bad.push(id + "(undefined)");
    if(txt.indexOf("NaN") >= 0) bad.push(id + "(NaN)");
  }
  if(bad.length) throw new Error("这些区域渲染出了坏值：" + bad.join(", "));
  return "10 个区域都干净";
});

// 6) 事件绑定必须真的绑到了存在的 id（拼错 id 是最常见的静默失败）
step("事件绑定指向的元素 id 都真实存在", () => {
  const html = require("fs").readFileSync(process.argv[3], "utf8");
  const used = new Set();
  const re = /el\("([A-Za-z0-9_-]+)"\)\.addEventListener/g;
  let m;
  while((m = re.exec(html))) used.add(m[1]);
  const missing = [...used].filter(id => html.indexOf('id="' + id + '"') < 0);
  if(missing.length) throw new Error("绑定了不存在的 id：" + missing.join(", "));
  return [...used].join(", ");
});

if (__alerts.length) out.alertsNote = __alerts.slice(0, 5);
process.stdout.write(JSON.stringify(out));
"""


def _node() -> str:
    for cand in (r"C:\Users\llj12\.workbuddy\binaries\node\versions\22.22.2-6\node.exe",
                 shutil.which("node")):
        if cand and Path(cand).exists():
            return str(cand)
    print("[error] 找不到 node", file=sys.stderr)
    raise SystemExit(1)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    return self_test() if "--self-test" in argv else _run()


def self_test() -> int:
    """证明这个冒烟不是"永远绿灯"。

    挑三种**真实发生过的**网页坏法注入，每一种都必须被判红：
      1. 同步漏字段（OCC_SUMMARY 少一个 key）→ 页面印出 undefined；
      2. DOM 读取不判空（querySelector(...).textContent 写死）→ 导出整段崩；
      3. JS 语法错（函数名改坏）→ 整段 <script> 起不来。
    外加第 4 种：把刚修好的"岗位名剥 Markdown 标题"改回去。
    最后必须还原现场，并证明真实网页依然是绿的。
    """
    original = HTML.read_text(encoding="utf-8")
    bad = 0
    print("[self-test] 注入四种网页坏法，每一种都必须被抓出来：")
    cases = [
        ("同步漏导出 coverage（指标卡会算出 NaN%）",
         original.replace(" coverage:", " ")),
        ("DOM 读取不判空（还原写死的 querySelector().textContent）",
         original.replace('return n ? (n.textContent || "").trim() : "";',
                          "return n.textContent.trim();")),
        ("JS 语法错（把函数名改坏）",
         original.replace("function renderOccupations()",
                          "function renderOccupationsBroken(")),
        ("岗位名忘了剥 Markdown 标题（回到带『#』的旧行为）",
         original.replace('return String(s||"").replace(/^[#*\\s]+/,"")',
                          'return String(s||"")')),
    ]
    try:
        for name, sabotaged in cases:
            if sabotaged == original:
                print(f"  ✗ {name} —— 注入没生效（补丁形状变了？）")
                bad += 1
                continue
            HTML.write_text(sabotaged, encoding="utf-8")
            caught = _run(quiet=True) != 0
            bad += 0 if caught else 1
            print(f"  {'✓' if caught else '✗'} {name}")
    finally:
        HTML.write_text(original, encoding="utf-8")

    ok = _run(quiet=True) == 0
    bad += 0 if ok else 1
    print(f"  {'✓' if ok else '✗'} 还原后真实网页依然是绿的")

    print()
    if bad:
        print(f"结论：自测失败 ✗（{bad} 项结果不对）")
        return 1
    print("结论：冒烟脚本有牙齿 ✓（4 种真实坏法全被抓到，且真实网页仍全绿）")
    return 0


def _run(quiet: bool = False) -> int:
    import re
    import tempfile

    # 喂进网页的 JD 必须用**真实样例**（两条带具体截止日、一条「招满为止」），
    # 否则今日清单的日期分支一次都不会被走到。
    due_jds = sorted((ROOT / "examples" / "daily_jds").glob("*.md"))
    if not due_jds:
        print("[error] 找不到 examples/daily_jds/*.md", file=sys.stderr)
        return 1
    due = {"jds": [{"name": f.name, "text": f.read_text(encoding="utf-8")} for f in due_jds]}

    src = HTML.read_text(encoding="utf-8")
    m = re.search(r"<script>(.*)</script>", src, re.S)
    if not m:
        print("[error] docs/index.html 里没找到 <script>", file=sys.stderr)
        return 1
    js = m.group(1)

    with tempfile.TemporaryDirectory() as tmp:
        due_f = Path(tmp) / "due.json"
        due_f.write_text(json.dumps(due, ensure_ascii=False), encoding="utf-8")
        f = Path(tmp) / "smoke.js"
        f.write_text(STUB + "\n" + js + "\n" + DRIVER, encoding="utf-8")
        r = subprocess.run([_node(), str(f), str(due_f), str(HTML)],
                           capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            if not quiet:
                print("[error] 网页 JS 跑挂了：", file=sys.stderr)
                print(r.stderr[:3000], file=sys.stderr)
            return 1
        try:
            out = json.loads(r.stdout)
        except json.JSONDecodeError:
            if not quiet:
                print("[error] 输出不是 JSON:", r.stdout[:400], file=sys.stderr)
            return 1

    if quiet:
        return 1 if out["errors"] else 0

    print("网页 demo 端到端冒烟（整段 <script> 在 Node 里跑，DOM 用最小桩）")
    for s in out["steps"]:
        info = s["info"]
        if len(info) > 78:
            info = info[:78] + "…"
        print(f"  {'✓' if s['ok'] else '✗'} {s['name']:<34} {info}")
    if out.get("alertsNote"):
        print("\n  注：冒烟期间弹出了 alert ——", out["alertsNote"])
    print()
    if out["errors"]:
        print(f"结论：{len(out['errors'])} 个入口炸了 ✗")
        for e in out["errors"]:
            print("  -", e)
        return 1
    print(f"结论：{len(out['steps'])} 个入口全部跑通 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
