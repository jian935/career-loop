"""career-loop CLI：把 JD、经历、投递、回流、校准串成一条命令链。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import calibrate as calib_mod
from . import collect as collect_mod
from . import matching
from . import recommend as rec_mod
from . import store
from .eval import load_dataset, run_eval


def _read(path: str) -> str:
    return Path(path).expanduser().read_text(encoding="utf-8")


def _read_jsonl(path: str) -> list[dict]:
    return load_dataset(path)


def _ensure_stdout_utf8() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass


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
    reqs, _ = matching.extract_requirements(text)
    jid = store.add_jd(matching.extract_title(text), text, reqs, args.db)
    print(f"已保存 JD #{jid}：{matching.extract_title(text)}（{len(reqs)} 项能力）")
    for r in reqs:
        print(f"  - [{r.weight}] {r.label}")
    return 0


def cmd_match(args) -> int:
    text = _read(args.jd)
    profile = _read(args.profile)
    reqs, mode = matching.extract_requirements(text)
    matches, _ = matching.match(reqs, profile)
    assessment = matching.Assessment(
        requirements=reqs, matches=matches,
        score=matching.score(reqs, matches),
        jd_title=matching.extract_title(text), mode=mode,
    )
    report = matching.render(assessment, Path(args.profile).stem)
    Path(args.out).write_text(report, encoding="utf-8")
    print(f"匹配度 {assessment.score}%  ·  模式 {mode}  ·  报告已写入 {args.out}")
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
    reqs, _ = matching.extract_requirements(jd["text"])
    matches, _ = matching.match(reqs, prof["text"])
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

    ranked = rec_mod.recommend(profile, jds)
    print(f"你的经历 × {len(jds)} 个 JD，按匹配分排序：")
    for i, r in enumerate(ranked[:args.top], 1):
        print(f"  {i}. {r.score:>5}%  {r.title}")

    lev = rec_mod.gap_leverage(profile, jds, args.threshold)
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
    try:
        import streamlit  # noqa: F401
    except ImportError:
        print("未安装 streamlit，先 `pip install streamlit`。")
        return 1
    import os
    import subprocess
    import sys
    from pathlib import Path

    path = Path(__file__).parent / "dashboard.py"
    env = os.environ.copy()
    if args.db:
        env["CAREER_LOOP_DB"] = args.db
    print(f"启动看板（演示数据）：streamlit run {path}")
    return subprocess.run([sys.executable, "-m", "streamlit", "run", str(path)], env=env).returncode


def cmd_whatif(args) -> int:
    text = _read(args.jd)
    profile = _read(args.profile)
    reqs, mode = matching.extract_requirements(text)
    matches, used = matching.match(reqs, profile)
    base, rows = matching.counterfactual(reqs, matches)
    print(f"当前匹配度 {base}%  ·  模式 {used}")
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
    sub = p.add_subparsers(dest="command")

    sub.add_parser("init", help="初始化本地数据库")

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

    ev = sub.add_parser("eval", help="跑标注评测集，给匹配引擎打分")
    ev.add_argument("--data", default="data/eval_sample.jsonl")
    ev.add_argument("--badcases", default="badcases.jsonl")

    sub.add_parser("dashboard", help="启动 Streamlit 看板")

    wi = sub.add_parser("whatif", help="反事实：补上哪一项能力，匹配分涨最多")
    wi.add_argument("--jd", required=True)
    wi.add_argument("--profile", required=True)
    wi.add_argument("--top", type=int, default=5)

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
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1
    _ensure_stdout_utf8()
    handlers = {
        "init": cmd_init, "add-profile": cmd_add_profile, "add-jd": cmd_add_jd,
        "match": cmd_match, "apply": cmd_apply, "status": cmd_status,
        "log": cmd_log, "calibrate": cmd_calibrate, "eval": cmd_eval,
        "dashboard": cmd_dashboard, "recommend": cmd_recommend,
        "collect": cmd_collect, "demand": cmd_demand, "whatif": cmd_whatif,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
