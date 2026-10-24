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
        capture_output=True, text=True, cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    out = (r.stdout + r.stderr).strip()
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
