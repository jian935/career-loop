# -*- coding: utf-8 -*-
"""End-to-end CLI audit. Exits non-zero if any check fails.

Runs on Linux, macOS and Windows with a clean Python 3.10+ (no third-party deps).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RESULTS: list[tuple[str, bool, str]] = []


def run(args: list[str], expect: int = 0, contains: str | list[str] | None = None,
        name: str = "", db: str | None = None) -> None:
    db = db or DB
    r = subprocess.run(
        [sys.executable, "-m", "career_loop", "--db", db, *args],
        # Windows runner 的控制台是 cp1252，而子进程（本项目 CLI）输出 UTF-8 中文。
        # 不指定 encoding 时 subprocess 按 locale 解码 → UnicodeDecodeError（byte 0x9d），
        # 且解码失败后 stdout/stderr 会是 None，下一行拼接再抛 TypeError。
        # 其它脚本（cross_engine_* / smoke_web / test_core）都写了 encoding="utf-8"，这里对齐。
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": str(ROOT), "CAREER_LOOP_NO_LLM": "1"},
    )
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    ok = r.returncode == expect
    if contains:
        for c in ([contains] if isinstance(contains, str) else contains):
            ok = ok and c in out
    RESULTS.append((name or " ".join(args[:1]), ok, out[-300:]))


def check_eval_baseline() -> None:
    from career_loop import matching
    from career_loop.eval import load_dataset, run_eval

    ds = load_dataset(str(ROOT / "data" / "eval_sample.jsonl"))

    def matcher(jd: str, profile: str) -> dict[str, str]:
        reqs, _ = matching.extract_requirements(jd)
        return {r.key: matching.match_by_rules(reqs, profile).get(r.key).status for r in reqs}

    summary = run_eval(ds, matcher)
    ok = summary.accuracy >= 0.9
    RESULTS.append(("eval baseline >= 0.9", ok, f"accuracy={summary.accuracy} n={summary.total}"))


def main() -> int:
    global DB
    tmp = Path(tempfile.mkdtemp(prefix="careerloop_audit_"))
    DB = str(tmp / "audit.db")
    empty = str(tmp / "empty.db")

    run(["init"], name="init")
    run(["doctor"], name="doctor")
    run(["add-profile", "--name", "测试我", "--file", "examples/profile_me.md"], name="add-profile")
    run(["add-jd", "--file", "examples/jds/jd_backend_pm.md"], name="add-jd")

    report = tmp / "report.md"
    run(["match", "--jd", "examples/jds/jd_backend_pm.md",
         "--profile", "examples/profile_me.md", "--out", str(report), "--json"],
        contains=["匹配度", "模式"], name="match")
    RESULTS.append(("match writes md", report.exists(), str(report)))
    RESULTS.append(("match writes json", report.with_suffix(".json").exists(), ""))

    run(["apply", "--jd-id", "1", "--profile-id", "1"], contains="已记录投递", name="apply")
    run(["status"], contains=["测试我"], name="status")
    run(["log", "--app-id", "1", "--status", "interview"], contains="状态更新", name="log")
    run(["status"], contains="interview", name="status reflects log")

    run(["calibrate", "--data", "data/demo_applications.jsonl"],
        contains=["相关系数", "样本量"], name="calibrate(demo)")
    run(["calibrate"], expect=1, contains="样本太少", name="calibrate(too few)")
    run(["eval", "--data", "data/eval_sample.jsonl", "--badcases", str(tmp / "bc.jsonl")],
        contains="一致率", name="eval")
    run(["recommend", "--profile", "examples/profile_me.md", "--jds", "examples/jds",
         "--threshold", "70"], contains=["按匹配分排序", "性价比最高缺口"], name="recommend")
    run(["whatif", "--jd", "examples/jds/jd_agent_dev.md",
         "--profile", "examples/profile_me.md"], contains=["当前匹配度", "最划算"], name="whatif")
    run(["intern", "--profile", "examples/profile_me.md", "--goal", "ai", "--cohort", "2028"],
        contains=["目标方向", "届时间线"], name="intern")
    run(["scan", "--profile", "examples/profile_me.md", "--jobs", "examples/jds",
         "--level", "junior"], contains=["最适配岗位", "行业适配"], name="scan")

    run(["collect", "--dir", "examples/raw_jds", "--report", str(tmp / "demand.md")],
        contains="采集完成", name="collect")
    run(["collect", "--dir", "examples/raw_jds"], contains="跳过重复 4", name="collect(dedupe)")
    RESULTS.append(("collect writes report", (tmp / "demand.md").exists(), ""))
    run(["demand"], contains="能力需求", name="demand")
    run(["demand", "--profile", "examples/profile_me.md",
         "--report", str(tmp / "d2.md")], contains="你覆盖", name="demand(profile)")

    junk = tmp / "junk.md"
    junk.write_text("这是一段没有任何能力关键词的说明文字。", encoding="utf-8")
    run(["add-jd", "--file", str(junk)], contains="已保存 JD", name="add-jd(empty reqs)")
    run(["match", "--jd", str(junk), "--profile", "examples/profile_me.md",
         "--out", str(tmp / "j.md")], contains="匹配度", name="match(empty reqs)")

    run(["apply", "--jd-id", "999", "--profile-id", "999"], expect=1, contains="不存在",
        name="apply(bad id)")
    empty_dir = tmp / "emptyjd"
    empty_dir.mkdir()
    run(["recommend", "--profile", "examples/profile_me.md", "--jds", str(empty_dir)],
        expect=1, contains="没有 .md", name="recommend(empty dir)")
    run(["init"], name="init(empty)", db=empty)
    run(["demand"], expect=1, contains="还没有 JD", name="demand(empty db)", db=empty)
    run(["collect", "--dir", str(tmp / "nope")], expect=1, contains="目录不存在",
        name="collect(missing dir)")
    run(["log", "--app-id", "1", "--status", "bad"], expect=2, name="log(bad status)")

    # daily：三种导出都得在同一份数据上跑得通，且文件非空
    daily_out = tmp / "today.md"
    run(["daily", "--profile", "examples/profile_me.md", "--jds", "examples/daily_jds",
         "--top", "3", "--out", str(daily_out)],
        contains=["今日投递清单", "截止"], name="daily(md)")
    RESULTS.append(("daily(md file written)",
                    daily_out.exists() and "- [ ] " in daily_out.read_text(encoding="utf-8"),
                    f"exists={daily_out.exists()}"))
    csv_out = tmp / "today.csv"
    run(["daily", "--profile", "examples/profile_me.md", "--jds", "examples/daily_jds",
         "--out", str(csv_out), "--format", "csv"], name="daily(csv)")
    RESULTS.append(("daily(csv has rows)",
                    csv_out.exists() and len(csv_out.read_text(encoding="utf-8").splitlines()) > 1,
                    f"exists={csv_out.exists()}"))
    ics_out = tmp / "today.ics"
    run(["daily", "--profile", "examples/profile_me.md", "--jds", "examples/daily_jds",
         "--out", str(ics_out), "--format", "ics"], name="daily(ics)")
    ok = False
    if ics_out.exists():
        body = ics_out.read_text(encoding="utf-8")
        ok = body.startswith("BEGIN:VCALENDAR") and body.rstrip().endswith("END:VCALENDAR")
    RESULTS.append(("daily(ics well formed)", ok, "missing or malformed"))
    run(["daily", "--profile", "examples/profile_me.md", "--jds", str(tmp / "nope")],
        expect=1, contains="路径不存在", name="daily(missing dir)")
    run(["daily", "--profile", "examples/profile_me.md", "--jds", "examples/daily_jds",
         "--due", "2026-13-40"], expect=1, contains="YYYY-MM-DD", name="daily(bad due)")

    # occupations：README 宣称"可对齐到职业分类大典"，这条命令就是那个承诺的入口。
    # 断言里带上具体口径而不是只看返回码：只检查"跑得通"等于什么都没检查——
    # 这个模块曾经是零引用的死代码，跑得通却从没人调。
    #
    # v0.8.26 重写了口径（旧版分母是自己挑的 39 个中类，于是只有 100% + 49%），
    # 现在强制三口径同屏：覆盖率 62/79、完整度 62/76、目录整理度 76/79。
    # 数字从 taxonomy_cn 现算，别写死——写死过一次，口径一改这条就失真。
    from career_loop.matching import taxonomy_cn  # 本地导入：audit 只依赖 CLI 行为

    s = taxonomy_cn.coverage_summary()
    run(["occupations"],
        contains=[f"{s['supported']}/{s['dictionary_total']}",
                  f"{s['supported']}/{s['enumerated']}",
                  f"{s['enumerated']}/{s['dictionary_total']}",
                  "启发式"],
        name="occupations")

    check_eval_baseline()

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print("=" * 70)
    for name, ok, detail in RESULTS:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        if not ok:
            print("       " + detail.replace("\n", "\n       "))
    print("=" * 70)
    print(f"passed {passed}/{len(RESULTS)}")

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
