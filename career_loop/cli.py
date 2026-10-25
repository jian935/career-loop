"""career-loop CLI：把 JD、经历、投递、回流、校准串成一条命令链。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import calibrate as calib_mod
from . import collect as collect_mod
from . import explore as explore_mod
from . import internship as intern_mod
from . import matching
from . import recommend as rec_mod
from . import store
from .eval import load_dataset, run_eval
from .matching.schema import FAMILY_CN as DOMAIN_CN  # noqa: F401（sync_web_vocab 依赖此名）


def _read(path: str) -> str:
    return Path(path).expanduser().read_text(encoding="utf-8")


def _read_jsonl(path: str) -> list[dict]:
    return load_dataset(path)


def _parse_env_file(path: Path) -> dict[str, str]:
    """Minimal .env parser: KEY=VALUE, optional `export`, quotes, comments."""
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


def _load_dotenv() -> None:
    """Load .env from cwd or repo root without overriding real env vars."""
    for candidate in (Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"):
        if not candidate.exists():
            continue
        try:
            for key, value in _parse_env_file(candidate).items():
                os.environ.setdefault(key, value)
        except OSError:
            pass


def _ensure_stdout_utf8() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _domain_text(text: str) -> str:
    doms = matching.detect_domains(text)
    return " / ".join(DOMAIN_CN.get(d, d) for d in doms[:3]) or "通用"


def _make_llm(args=None):
    """Return a configured LLM, or None so every command falls back to rules."""
    if getattr(args, "no_llm", False) or os.getenv("CAREER_LOOP_NO_LLM") == "1":
        return None
    llm = matching.LLM()
    return llm if llm.available else None


def cmd_domains(args) -> int:
    """判岗位族。--backend 默认 blend：LLM 首选优先 + 规则补充（实测 any-in 93.4% / top-1 73.5%）。"""
    text = _read(args.file)
    llm = _make_llm(args) if args.backend != "rules" else None
    verdict = matching.detect_families(text, llm, mode=args.backend)
    names = " / ".join(DOMAIN_CN.get(d, d) for d in verdict.families) or "（未判出）"
    print(f"岗位族：{names}")
    print(f"keys   {verdict.families}")
    line = f"模式   {verdict.used}"
    if verdict.note:
        line += f"（{verdict.note}）"
    print(line)
    return 0


def cmd_llm_proxy(args) -> int:
    """启动本地 LLM 代理，让浏览器里的网页 demo 能用上你自己配置的模型。

    浏览器直连 OpenAI 兼容接口有两个硬障碍：多数服务商不给 CORS 头（浏览器
    直接 fetch 会被拦），以及 API Key 不该粘进网页。这个代理跑在 127.0.0.1，
    Key 留在本地，网页只跟本机说话。
    """
    from . import llm_proxy
    llm_proxy.serve(port=args.port, token=args.token,
                    allow_any_origin=args.allow_any_origin,
                    open_browser=not args.no_open)
    return 0


def cmd_doctor(args) -> int:
    import platform
    from .matching.llm import CACHE_DIR

    llm = matching.LLM()
    print(f"Python   {platform.python_version()}  ({platform.system()})")
    print(f"DB       {args.db or store.get_db()}")
    print(f"LLM      {'已配置' if llm.available else '未配置（规则基线）'}")
    print(f"  model  {llm.model}")
    print(f"  base   {llm.base_url}")
    print(f"  cache  {'on' if llm.cache else 'off'}  {CACHE_DIR}")
    ev = Path("data/eval_sample.jsonl")
    print(f"评测集   {'OK' if ev.exists() else '缺失'}  {ev}")
    return 0


def cmd_init(args) -> int:
    store.init(args.db)
    print(f"已初始化数据库：{args.db or store.get_db()}")
    return 0


def cmd_add_profile(args) -> int:
    store.init(args.db)
    pid = store.add_profile(args.name, _read(args.file), args.db)
    print(f"已保存候选人 #{pid}：{args.name}")
    return 0


def cmd_add_jd(args) -> int:
    store.init(args.db)
    text = _read(args.file)
    reqs, _ = matching.extract_requirements(text, _make_llm(args))
    jid = store.add_jd(matching.extract_title(text), text, reqs, args.db)
    print(f"已保存 JD #{jid}：{matching.extract_title(text)}（{len(reqs)} 项能力）")
    for r in reqs:
        print(f"  - [{r.weight}] {r.label}")
    return 0


def cmd_match(args) -> int:
    text = _read(args.jd)
    profile = _read(args.profile)
    llm = _make_llm(args)
    reqs, _ = matching.extract_requirements(text, llm)
    matches, mode = matching.match(reqs, profile, llm)
    assessment = matching.Assessment(
        requirements=reqs, matches=matches,
        score=matching.score(reqs, matches),
        jd_title=matching.extract_title(text), mode=mode,
    )
    report = matching.render(assessment, Path(args.profile).stem)
    Path(args.out).write_text(report, encoding="utf-8")
    print(f"匹配度 {assessment.score}%  ·  模式 {mode}  ·  岗位族 {_domain_text(text)}  ·  报告已写入 {args.out}")
    if args.json:
        out = Path(args.out).with_suffix(".json")
        out.write_text(json.dumps({
            "score": assessment.score, "mode": mode,
            "requirements": [r.__dict__ for r in reqs],
            "matches": {k: v.__dict__ for k, v in matches.items()},
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON 已写入 {out}")
    return 0


def cmd_apply(args) -> int:
    store.init(args.db)
    jd = store.get_jd(args.jd_id, args.db)
    prof = store.get_profile(args.profile_id, args.db)
    if not jd or not prof:
        print("JD 或候选人不存在"); return 1
    llm = _make_llm(args)
    reqs, _ = matching.extract_requirements(jd["text"], llm)
    matches, _ = matching.match(reqs, prof["text"], llm)
    fit = matching.score(reqs, matches)
    aid = store.record_application(args.jd_id, args.profile_id, fit, args.db)
    print(f"已记录投递 #{aid}：{jd['title']} × {prof['name']}，预测匹配分 {fit}%")
    return 0


def cmd_status(args) -> int:
    rows = store.list_applications(args.db)
    if not rows:
        print("还没有投递记录。用 `apply` 添加，或用 `calibrate --data data/demo_applications.jsonl` 看演示。")
        return 0
    print(f"{'id':>3}  {'匹配分':>5}  {'状态':<10} {'候选人':<8} {'JD'}")
    for r in rows:
        print(f"{r['id']:>3}  {r['fit_score']:>5}  {r['status']:<10} {r['profile_name']:<8} {r['jd_title']}")
    return 0


def cmd_log(args) -> int:
    store.init(args.db)
    store.set_status(args.app_id, args.status, args.note, args.db)
    print(f"#{args.app_id} 状态更新为 {args.status}")
    return 0


def cmd_calibrate(args) -> int:
    if args.data:
        rows = _read_jsonl(args.data)
        scores = [float(r["fit_score"]) for r in rows]
        positives = [bool(r["positive"]) for r in rows]
    else:
        rows = store.calibration_rows(args.db)
        scores = [r.fit_score for r in rows]
        positives = [r.positive for r in rows]
    if len(scores) < 5:
        print("样本太少，先积累至少 5 条投递结果。"); return 1
    report = calib_mod.calibrate(scores, positives)
    print(f"\n样本量 {report.n}　整体正反馈率 {report.positive_rate}")
    print(f"匹配分 ↔ 真实结果 相关系数 r = {report.correlation}")
    print("\n分桶正反馈率：")
    for b in report.buckets:
        bar = "#" * int(b.positive_rate * 30)
        print(f"  {b.lo:>3}-{b.hi:<3}  n={b.n:<3}  率={b.positive_rate:<5} {bar}")
    print(f"\n结论：{report.verdict}")
    if args.json:
        Path(args.json).write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON 已写入 {args.json}")
    return 0


def cmd_reflow(args) -> int:
    """一条命令跑完整回流闭环：读记录 → 算分 → 校准 → 归因 → 出报告。"""
    from . import reflow as rf

    src = Path(args.records)
    if not src.exists():
        print(f"记录文件不存在：{src}"); return 1
    profile = _read(args.profile)
    if not profile.strip():
        print("经历文件为空，无法打分", file=sys.stderr); return 1

    records = rf.load_records(src)
    if not records:
        print(f"没读到任何记录：{src}"); return 1

    # 校准必须可复现：默认走规则模式（离线、确定性）。
    # 需要 LLM 抽取时显式加 --use-llm。
    llm = matching.LLM() if getattr(args, "use_llm", False) else None
    if getattr(args, "use_llm", False) and not llm.available:
        print("⚠️ 已指定 --use-llm 但没有可用的模型配置，已回退到规则模式。")
    res = rf.analyze_reflow(records, profile, args.mode, llm)

    # 写 SQLite：让 status / calibrate 命令也能用上这批记录
    if args.db_write:
        store.init(args.db)
        pid = store.add_profile(args.profile_name, profile, args.db)
        for s in res.scored:
            if s.score is None:
                continue
            jid = store.add_jd(s.role or "(未命名岗位)", s.record.get("jd_text", ""), [], args.db)
            aid = store.record_application(jid, pid, s.score, args.db)
            store.set_status(aid, s.status, s.note, args.db)
        print(f"[db] {len(res.scored_usable)} 条已写入 {args.db or '默认库'}"
              f"（可用 `career-loop status` 查看）\n")

    print(rf.render_console_summary(res))
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            rf.render_report(res, title=args.title, data_note=args.data_note),
            encoding="utf-8",
        )
        print(f"\n报告已写入 {out}")
    return 0


def cmd_eval(args) -> int:
    ds = load_dataset(args.data)
    def matcher(jd, profile):
        reqs, _ = matching.extract_requirements(jd)
        return {r.key: matching.match_by_rules(reqs, profile).get(r.key).status for r in reqs}
    summary = run_eval(ds, matcher)
    print(f"评测集 {summary.total} 条　规则基线一致率 {summary.accuracy}")
    print(f"逐能力：")
    for k, v in sorted(summary.per_capability.items()):
        print(f"  {k:<18} {v['accuracy']}  ({v['correct']}/{v['total']})")
    if summary.badcases:
        print(f"\n{len(summary.badcases)} 条 badcase 已写入 {args.badcases}")
        with open(args.badcases, "w", encoding="utf-8") as f:
            for b in summary.badcases:
                f.write(json.dumps(b, ensure_ascii=False) + "\n")
    else:
        print("\n无 badcase。")
    return 0


def cmd_recommend(args) -> int:
    from pathlib import Path

    profile = _read(args.profile)
    jd_dir = Path(args.jds)
    if not jd_dir.is_dir():
        print(f"目录不存在：{args.jds}"); return 1
    jds = []
    for f in sorted(jd_dir.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        jds.append((matching.extract_title(text), text))
    if not jds:
        print("目录里没有 .md JD 文件"); return 1

    llm = _make_llm(args)
    ranked = rec_mod.recommend(profile, jds, llm)
    print(f"你的经历 × {len(jds)} 个 JD，按匹配分排序：")
    for i, r in enumerate(ranked[:args.top], 1):
        print(f"  {i}. {r.score:>5}%  {r.title}")

    lev = rec_mod.gap_leverage(profile, jds, args.threshold, llm)
    print(f"\n补上这些能力，能让你跨过 {args.threshold:.0f}% 线的 JD 数量最多（性价比最高缺口）：")
    shown = 0
    for item in lev:
        if item["gained"] == 0:
            continue
        shown += 1
        if shown > args.top:
            break
        print(f"  + {item['label']}：可多解锁 {item['gained']} 个 JD")
        for t in item["jds"][:3]:
            print(f"      · {t}")
    if shown == 0:
        print("  （当前没有「补一项就能跨线」的缺口，缺口已较均衡。）")
    return 0


def cmd_dashboard(args) -> int:
    """起 Streamlit 看板：漏斗 / 校准散点（带置信区间）/ 缺口排行。

    数据源通过环境变量传给子进程（Streamlit 自己会重跑脚本，
    命令行参数传不过去），看板侧从 env 里读默认值，也能在侧边栏手动改。
    """
    try:
        import streamlit  # noqa: F401
    except ImportError:
        print("未安装 streamlit，先 `pip install streamlit`（或 pip install \"career-loop[ui]\"）。")
        return 1
    import os
    import subprocess
    import sys
    from pathlib import Path

    path = Path(__file__).parent / "dashboard.py"
    env = os.environ.copy()
    if args.db:
        env["CAREER_LOOP_DB"] = args.db
    env["CAREER_LOOP_BOARD_RECORDS"] = args.records or ""
    env["CAREER_LOOP_BOARD_PROFILE"] = args.profile or "examples/profile_me.md"
    cmd = [sys.executable, "-m", "streamlit", "run", str(path), "--server.headless=true"]
    if args.port:
        cmd += ["--server.port", str(args.port)]
    src = args.records or (args.db or "本地库/演示数据")
    print(f"启动看板　数据源：{src}")
    print("（Ctrl+C 结束。数据源不对就在看板左侧改，改完即时重算。）")
    return subprocess.run(cmd, env=env).returncode


def cmd_scan(args) -> int:
    profile = _read(args.profile)
    jobs = explore_mod.load_jobs(args.jobs)
    if args.category:
        c = args.category.lower()
        jobs = [j for j in jobs if c in str(j["category"]).lower()]
    if not jobs:
        print("没有可扫描的岗位"); return 1
    llm = _make_llm(args)
    print(f"扫描 {len(jobs)} 个岗位（LLM={'on' if llm else 'off'}）...")
    level = None if args.level == "all" else args.level
    rep = explore_mod.scan(profile, jobs, llm, top=args.top, workers=args.workers,
                           level=level, goal=args.goal)
    print(f"成功 {rep.ok}/{rep.total} · {rep.categories} 个行业 · 模式 {rep.mode_counts}\n")

    if args.goal:
        targets = [r for r in rep.jobs if r.goal_match][:5]
        print(f"目标方向（{args.goal}）命中 {sum(1 for r in rep.jobs if r.goal_match)} 个：")
        for i, r in enumerate(targets, 1):
            gap = f"{r.top_gaps[0][1]} +{r.top_gaps[0][2]}" if r.top_gaps else "无"
            print(f"  {i}. {r.score:>5}%  [{r.level:<6}] {r.title[:38]:<38} 缺口: {gap}")
        print()

    print("最适配岗位：")
    for i, r in enumerate(rep.jobs[:10], 1):
        gap = f"{r.top_gaps[0][1]} +{r.top_gaps[0][2]}" if r.top_gaps else "无"
        print(f"  {i:>2}. {r.score:>5}%  [{r.level:<6}] {r.title[:36]:<36} {r.category[:18]:<18} 缺口: {gap}")

    print("\n行业适配：")
    for ind in rep.industries[:10]:
        print(f"  {ind.category[:26]:<26} n={ind.n_jobs:<3} best={ind.best_score:<5} avg={ind.avg_score}")

    print("\n最该补的能力：")
    for key, label, n, fix in rep.gap_counts[:5]:
        print(f"  {label} ×{n}  → {fix[:48]}")

    intern_rows = None
    if args.cohort:
        intern_rows = intern_mod.rank(profile, goal=args.goal)
    if args.report:
        Path(args.report).write_text(
            explore_mod.render_markdown(rep, Path(args.profile).stem, intern_rows, args.cohort),
            encoding="utf-8",
        )
        print(f"\n报告已写入 {args.report}")
    return 0


def cmd_intern(args) -> int:
    profile = _read(args.profile)
    presets = intern_mod.load_presets(args.presets)
    results = intern_mod.rank(profile, presets, args.goal)
    print(f"目标方向：{args.goal or '未指定'}  ·  共 {len(results)} 个方向")
    print("按「目标契合 + 匹配分」排序：\n")
    for i, r in enumerate(results[:args.top], 1):
        mark = "✓" if r.goal_match else "—"
        gap = f"{r.top_gap} +{r.top_gain}" if r.top_gap else "无缺口"
        print(f"  {i}. {r.score:>5}%  {r.title:<24} 目标{mark}  最大缺口：{gap}")
    if args.cohort:
        print(f"\n{args.cohort} 届时间线：")
        for p in intern_mod.timeline(args.cohort):
            cur = "  ← 当前阶段" if p["current"] else ""
            print(f"  {p['phase']:<8} {p['start']} – {p['end']}  {p['goal']}{cur}")
    if args.report:
        Path(args.report).write_text(
            intern_mod.render_markdown(results, args.goal, args.cohort, Path(args.profile).stem),
            encoding="utf-8",
        )
        print(f"\n报告已写入 {args.report}")
    return 0


def cmd_whatif(args) -> int:
    text = _read(args.jd)
    profile = _read(args.profile)
    llm = _make_llm(args)
    reqs, _ = matching.extract_requirements(text, llm)
    matches, used = matching.match(reqs, profile, llm)
    base, rows = matching.counterfactual(reqs, matches)
    print(f"当前匹配度 {base}%  ·  模式 {used}  ·  岗位族 {_domain_text(text)}")
    print("\n补上哪一项最划算（假设补到「已具备」，按涨幅排序）：")
    label = {"full": "已具备", "partial": "部分", "missing": "缺失"}
    shown = 0
    for req, status, delta, new in rows:
        if delta <= 0:
            continue
        shown += 1
        if shown > args.top:
            break
        print(f"  {req.label:<14} [{label.get(status, status)}]  {base}% → {new}%  (+{delta})")
    if shown == 0:
        print("  （已全部覆盖，没有可提升的项。）")
    return 0


def cmd_collect(args) -> int:
    if not Path(args.dir).is_dir():
        print(f"目录不存在：{args.dir}"); return 1
    store.init(args.db)
    res = collect_mod.collect_dir(args.dir, args.db)
    total = len(store.list_jds(args.db))
    print(f"采集完成：新增 {res.ingested} 个 JD，跳过重复 {res.skipped} 个。")
    print(f"当前库内共 {total} 个 JD。")
    jds = store.list_jds(args.db)
    rep = collect_mod.capability_demand(jds)
    print("\n岗位需求热力（按总权重排序，取前 10）：")
    for it in rep.items[:10]:
        print(f"  {it.label:<14} 需求权重 {it.demand_weight:<3} 出现在 {it.demand_count} 个 JD")
    if args.report:
        Path(args.report).write_text(collect_mod.render_demand(rep), encoding="utf-8")
        print(f"\n需求报告已写入 {args.report}")
    return 0


def cmd_demand(args) -> int:
    store.init(args.db)
    jds = store.list_jds(args.db)
    if not jds:
        print("库里还没有 JD，先用 `collect` 或 `add-jd` 录入。"); return 1
    profile = _read(args.profile) if args.profile else None
    rep = collect_mod.capability_demand(jds, profile)
    print(f"统计 {rep.total_jds} 个 JD 的能力需求：")
    for it in rep.items:
        if profile is None:
            print(f"  {it.label:<14} 需求权重 {it.demand_weight:<3} 出现在 {it.demand_count} 个 JD")
        else:
            cov = f"{it.coverage:.0%}" if it.coverage is not None else "-"
            pri = f"{it.priority:.0f}" if it.priority is not None else "-"
            print(f"  {it.label:<14} 需求{it.demand_weight:<3} 你覆盖{cov:<4} 优先级{pri}")
    if args.report:
        Path(args.report).write_text(collect_mod.render_demand(rep), encoding="utf-8")
        print(f"\n需求报告已写入 {args.report}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="career-loop",
        description="AI 求职漏斗：预测匹配 → 记录投递 → 回流结果 → 校准模型。",
    )
    p.add_argument("--db", default=None, help="SQLite 数据库路径（默认 ~/.career_loop/loop.db）")
    p.add_argument("--no-llm", action="store_true", help="强制规则模式（即使配置了 Key）")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("init", help="初始化本地数据库")
    sub.add_parser("doctor", help="自检：Python / LLM / 缓存 / 评测集")
    lp = sub.add_parser("llm-proxy", help="启动本地 LLM 代理（供网页 demo 调用）")
    lp.add_argument("--port", type=int, default=8787, help="监听端口（默认 8787）")
    lp.add_argument("--token", default="", help="调用令牌（默认启动时随机生成）")
    lp.add_argument("--allow-any-origin", action="store_true",
                    help="允许任意 Origin 访问（默认只放行 file:// 与 localhost）")
    lp.add_argument("--no-open", action="store_true", help="不自动打开浏览器")

    dd = sub.add_parser("domains", help="判岗位族；--backend 可选 LLM 后端（默认 blend）")
    dd.add_argument("--file", required=True, help="JD 文本文件（md / txt）")
    dd.add_argument("--backend", choices=["rules", "llm", "auto", "blend"], default="blend",
                    help="rules=纯词表；llm=纯模型（失败回退规则）；"
                         "auto=规则先判、规则空结果时才问模型（省调用）；"
                         "blend=LLM 首选优先+规则补充（实测最优）")

    ap = sub.add_parser("add-profile", help="保存候选人经历")
    ap.add_argument("--file", required=True)
    ap.add_argument("--name", required=True)

    aj = sub.add_parser("add-jd", help="保存 JD 并抽取能力项")
    aj.add_argument("--file", required=True)

    m = sub.add_parser("match", help="生成 JD × 经历的匹配报告")
    m.add_argument("--jd", required=True)
    m.add_argument("--profile", required=True)
    m.add_argument("--out", default="report.md")
    m.add_argument("--json", action="store_true")

    aa = sub.add_parser("apply", help="记录一次投递（自动算预测匹配分）")
    aa.add_argument("--jd-id", type=int, required=True)
    aa.add_argument("--profile-id", type=int, required=True)

    sub.add_parser("status", help="列出投递记录")

    lg = sub.add_parser("log", help="更新投递状态")
    lg.add_argument("--app-id", type=int, required=True)
    lg.add_argument("--status", required=True, choices=["applied", "replied", "interview", "offer", "rejected"])
    lg.add_argument("--note", default="")

    cb = sub.add_parser("calibrate", help="校准：匹配分能否预测真实结果")
    cb.add_argument("--data", default=None, help="或用 jsonl 演示（字段 fit_score, positive）")
    cb.add_argument("--json", default=None)

    rf = sub.add_parser(
        "reflow",
        help="回流闭环：一条命令跑完 读记录→算分→校准 r→漏斗归因→出报告",
    )
    rf.add_argument("--records", required=True, help="投递记录 CSV / JSONL / JSON（自动识别列名）")
    rf.add_argument("--profile", required=True, help="你的经历文件（md / txt）")
    rf.add_argument("--mode", choices=["early", "terminal"], default="terminal",
                    help="口径：terminal=终局录取（只有 offer 算正反馈）；early=早期互动信号")
    rf.add_argument("--out", default=None, help="把 markdown 报告写到这个文件")
    rf.add_argument("--title", default="投递回流校准报告", help="报告标题")
    rf.add_argument("--data-note", default="", help="报告里标注的数据来源说明")
    rf.add_argument("--db-write", action="store_true",
                    help="同时把记录写进 SQLite，让 status / calibrate 也能用")
    rf.add_argument("--profile-name", default="候选人", help="写入 SQLite 时用的名字")
    rf.add_argument("--use-llm", action="store_true",
                    help="用模型抽取能力项（默认规则模式，保证离线可复现）")

    ev = sub.add_parser("eval", help="跑标注评测集，给匹配引擎打分")
    ev.add_argument("--data", default="data/eval_sample.jsonl")
    ev.add_argument("--badcases", default="badcases.jsonl")

    du = sub.add_parser("dashboard", help="启动看板：漏斗 + 校准散点 + 缺口排行")
    du.add_argument("--records", help="回流记录文件（CSV/JSONL），优先级高于本地库")
    du.add_argument("--profile", help="经历文件", default="examples/profile_me.md")
    du.add_argument("--db", help="SQLite 路径（默认 ~/.career_loop/loop.db）")
    du.add_argument("--port", type=int, help="端口（默认 8501）")

    wi = sub.add_parser("whatif", help="反事实：补上哪一项能力，匹配分涨最多")
    wi.add_argument("--jd", required=True)
    wi.add_argument("--profile", required=True)
    wi.add_argument("--top", type=int, default=5)

    sc = sub.add_parser("scan", help="简历 × 一批岗位 → 全行业适配 + 缺口 + 推荐")
    sc.add_argument("--profile", required=True)
    sc.add_argument("--jobs", required=True, help="岗位 JSONL，或放 JD 的目录")
    sc.add_argument("--top", type=int, default=20)
    sc.add_argument("--workers", type=int, default=6)
    sc.add_argument("--category", default=None, help="只扫包含该关键词的行业")
    sc.add_argument("--level", choices=["intern", "junior", "mid", "senior", "all"],
                    default="junior", help="目标职级；更高职级按比例降权（all=不降权）")
    sc.add_argument("--cohort", type=int, default=None)
    sc.add_argument("--goal", default=None)
    sc.add_argument("--report", default=None)

    it = sub.add_parser("intern", help="实习方向推荐：目标契合 + 匹配分，可算届别时间线")
    it.add_argument("--profile", required=True)
    it.add_argument("--goal", default=None, help="目标方向标签，如 ai / data / product")
    it.add_argument("--cohort", type=int, default=None, help="毕业年份，如 2028")
    it.add_argument("--top", type=int, default=6)
    it.add_argument("--presets", default=None, help="自定义实习岗位 JSONL（默认用内置 10 个方向）")
    it.add_argument("--report", default=None)

    cc = sub.add_parser("collect", help="W3：批量采集目录里的原始 JD 并入库（自动去重）")
    cc.add_argument("--dir", required=True, help="放原始 JD（.md/.txt）的目录")
    cc.add_argument("--report", default=None, help="可选：把需求热力报告写到这个 md 文件")

    dm = sub.add_parser("demand", help="跨整批 JD 汇总需求热力（可结合经历算该补什么）")
    dm.add_argument("--profile", default=None, help="可选：你的经历文件，算补能力优先级")
    dm.add_argument("--report", default=None, help="可选：把带优先级的需求报告写到 md 文件")

    rc = sub.add_parser("recommend", help="人→JD：给一批 JD 排序，并算补什么最划算")
    rc.add_argument("--profile", required=True)
    rc.add_argument("--jds", required=True, help="放多个 JD .md 的目录")
    rc.add_argument("--threshold", type=float, default=70.0)
    rc.add_argument("--top", type=int, default=5)

    return p


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1
    _ensure_stdout_utf8()
    handlers = {
        "init": cmd_init, "doctor": cmd_doctor,
        "add-profile": cmd_add_profile, "add-jd": cmd_add_jd,
        "match": cmd_match, "apply": cmd_apply, "status": cmd_status,
        "log": cmd_log, "calibrate": cmd_calibrate, "eval": cmd_eval,
        "reflow": cmd_reflow,
        "dashboard": cmd_dashboard, "recommend": cmd_recommend,
        "collect": cmd_collect, "demand": cmd_demand, "whatif": cmd_whatif,
        "intern": cmd_intern, "scan": cmd_scan, "domains": cmd_domains,
        "llm-proxy": cmd_llm_proxy,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
