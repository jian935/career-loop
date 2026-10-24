"""career-loop CLI：把 JD、经历、投递、回流、校准串成一条命令链。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import calibrate as calib_mod
from . import matching
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
    jd = store.get_jd(args.jd_id)
    prof = store.get_profile(args.profile_id)
    if not jd or not prof:
        print("JD 或候选人不存在"); return 1
    reqs, _ = matching.extract_requirements(jd["text"])
    matches, _ = matching.match(reqs, prof["text"])
    fit = matching.score(reqs, matches)
    aid = store.record_application(args.jd_id, args.profile_id, fit)
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
    store.set_status(args.app_id, args.status, args.note)
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
        "dashboard": cmd_dashboard,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
