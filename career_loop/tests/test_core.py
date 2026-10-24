"""core 行为契约：抽取、匹配、校准、评测。"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from career_loop import calibrate, collect, internship, matching, recommend, store
from career_loop.eval import load_dataset, run_eval


class TestMatching(unittest.TestCase):
    def test_strong_negative_is_missing(self):
        reqs = [matching.Requirement("coding_tools", "AI 编程工具", 1, "nice")]
        res = matching.match_by_rules(reqs, "没用过任何 AI 编程工具。")
        self.assertEqual(res["coding_tools"].status, "missing")

    def test_action_verb_makes_full(self):
        reqs = [matching.Requirement("python", "Python", 3, "must")]
        res = matching.match_by_rules(reqs, "用 Python 写了后端服务。")
        self.assertEqual(res["python"].status, "full")

    def test_heading_not_a_requirement(self):
        jd = "# AI 产品经理\n\n任职要求：\n1. 熟练使用 Python。\n"
        reqs, _ = matching.extract_requirements(jd)
        quotes = " ".join(r.quote for r in reqs)
        self.assertNotIn("AI 产品经理", quotes)

    def test_score_bounded(self):
        jd = "要求熟练使用 Python，也了解 RAG。"
        prof = "用 Python 写了服务。"
        reqs, _ = matching.extract_requirements(jd)
        matches, _ = matching.match(reqs, prof)
        v = matching.score(reqs, matches)
        self.assertGreaterEqual(v, 0.0)
        self.assertLessEqual(v, 100.0)


class TestCalibrate(unittest.TestCase):
    def test_monotonic_buckets(self):
        scores = [30, 35, 55, 60, 80, 90, 95]
        positives = [False, False, False, True, True, True, True]
        r = calibrate.calibrate(scores, positives)
        self.assertGreater(r.correlation, 0.5)
        # 高分段正反馈率应高于低分段
        self.assertGreater(r.buckets[-1].positive_rate, r.buckets[0].positive_rate)

    def test_empty(self):
        r = calibrate.calibrate([], [])
        self.assertEqual(r.n, 0)


class TestEval(unittest.TestCase):
    def test_baseline_passes_currated_set(self):
        ds = load_dataset(str(Path(__file__).parent.parent.parent / "data" / "eval_sample.jsonl"))

        def matcher(jd, profile):
            reqs, _ = matching.extract_requirements(jd)
            return {r.key: matching.match_by_rules(reqs, profile).get(r.key).status for r in reqs}

        s = run_eval(ds, matcher)
        self.assertGreaterEqual(s.accuracy, 0.9)


class TestStore(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "t.db")
            store.init(db)
            pid = store.add_profile("me", "用 Python 写了后端。", db)
            jid = store.add_jd("后端 JD", "要求熟练使用 Python。", [
                matching.Requirement("python", "Python", 3, "must")
            ], db)
            reqs, _ = matching.extract_requirements("要求熟练使用 Python。")
            matches, _ = matching.match(reqs, "用 Python 写了后端。")
            fit = matching.score(reqs, matches)
            aid = store.record_application(jid, pid, fit, db)
            store.set_status(aid, "interview", db=db)
            rows = store.list_applications(db)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "interview")


class TestRecommend(unittest.TestCase):
    def test_recommend_ranks_descending(self):
        profile = "用 Python 写了后端服务，做过数据分析看板。"
        jds = [
            ("后端开发工程师", "要求精通 Python，熟悉 Web 框架与数据库。"),
            ("AI 产品经理", "要求熟悉大模型原理，会提示词工程，能做数据分析。"),
            ("Agent 开发", "要求会用 Agent 框架，掌握函数调用，有 RAG 经验。"),
        ]
        ranked = recommend.recommend(profile, jds)
        self.assertEqual(len(ranked), 3)
        self.assertGreaterEqual(ranked[0].score, ranked[1].score)
        self.assertGreaterEqual(ranked[1].score, ranked[2].score)

    def test_leverage_detects_one_cap_away(self):
        # Agent 框架是核心硬门槛(3分)，Python 了解(2分)，total=5；
        # profile 缺 agent -> base 40%，补上 agent -> 100%，跨过 60 线。
        profile = "熟悉 Python，做过数据分析。"
        jds = [("Agent 核心岗", "任职要求：\n1. 精通 Agent 框架。\n2. 了解 Python。")]
        lev = recommend.gap_leverage(profile, jds, threshold=60.0)
        agent_item = next((x for x in lev if x["key"] == "agent"), None)
        self.assertIsNotNone(agent_item)
        self.assertEqual(agent_item["gained"], 1)

    def test_leverage_zero_when_already_over_threshold(self):
        # 已经全部满足，补哪一项都不会有边际收益。
        profile = "精通 Agent 框架，会用 Python。"
        jds = [("Agent 核心岗", "任职要求：\n1. 精通 Agent 框架。\n2. 了解 Python。")]
        lev = recommend.gap_leverage(profile, jds, threshold=70.0)
        agent_item = next((x for x in lev if x["key"] == "agent"), None)
        self.assertIsNotNone(agent_item)
        self.assertEqual(agent_item["gained"], 0)


class TestCollect(unittest.TestCase):
    def test_normalize_strips_noise(self):
        raw = "一键投递 立即申请\n联系方式：hr@fake.com 或 13800138000\nhttps://example.com\n# AI 产品经理\n任职要求：熟悉 Python。"
        clean = collect.normalize_jd(raw)
        self.assertNotIn("一键投递", clean)
        self.assertNotIn("hr@fake.com", clean)
        self.assertNotIn("13800138000", clean)
        self.assertNotIn("https://example.com", clean)
        self.assertIn("AI 产品经理", clean)
        self.assertIn("Python", clean)

    def test_collect_ingests_and_dedupes(self):
        with tempfile.TemporaryDirectory() as d:
            rawdir = os.path.join(d, "raw")
            os.makedirs(rawdir)
            db = os.path.join(d, "t.db")
            store.init(db)
            # 两个不同 JD
            Path(os.path.join(rawdir, "a.md")).write_text(
                "# 岗位A\n任职要求：精通 Python。", encoding="utf-8")
            Path(os.path.join(rawdir, "b.md")).write_text(
                "# 岗位B\n任职要求：熟悉 RAG。", encoding="utf-8")
            r1 = collect.collect_dir(rawdir, db)
            self.assertEqual(r1.ingested, 2)
            self.assertEqual(r1.skipped, 0)
            # 重复采集：应全部跳过
            r2 = collect.collect_dir(rawdir, db)
            self.assertEqual(r2.ingested, 0)
            self.assertEqual(r2.skipped, 2)
            self.assertEqual(len(store.list_jds(db)), 2)

    def test_demand_with_profile(self):
        jds = [
            ("岗A", "任职要求：\n1. 精通 Agent 框架。\n2. 了解 Python。"),
            ("岗B", "任职要求：\n1. 熟悉 RAG。\n2. 了解 Python。"),
        ]
        # 经历里完全没有 Agent 和 RAG，Python 有
        profile = "用 Python 写了后端服务。"
        rep = collect.capability_demand(jds, profile)
        self.assertTrue(rep.has_profile)
        self.assertEqual(rep.total_jds, 2)
        # 每个被要求的能力都应算出覆盖率
        keys = {it.key for it in rep.items}
        self.assertIn("agent", keys)
        self.assertIn("rag", keys)
        agent = next(it for it in rep.items if it.key == "agent")
        self.assertAlmostEqual(agent.coverage, 0.0)   # 完全缺失
        python = next(it for it in rep.items if it.key == "python")
        self.assertGreater(python.coverage, 0.0)       # 部分/完全具备


class TestCounterfactual(unittest.TestCase):
    def test_fixing_missing_raises_score(self):
        reqs = [
            matching.Requirement("agent", "Agent", 3, "must"),
            matching.Requirement("python", "Python", 2, "must"),
        ]
        matches = {
            "agent": matching.MatchResult("agent", "missing"),
            "python": matching.MatchResult("python", "full"),
        }
        base, rows = matching.counterfactual(reqs, matches)
        self.assertAlmostEqual(base, 40.0)
        self.assertEqual(rows[0][0].key, "agent")
        self.assertAlmostEqual(rows[0][3], 100.0)
        self.assertAlmostEqual(rows[0][2], 60.0)

    def test_all_full_has_no_rows(self):
        reqs = [matching.Requirement("python", "Python", 2, "must")]
        matches = {"python": matching.MatchResult("python", "full")}
        base, rows = matching.counterfactual(reqs, matches)
        self.assertAlmostEqual(base, 100.0)
        self.assertEqual(rows, [])


class TestGeneralization(unittest.TestCase):
    """非 AI 岗位 / 词表外要求也要能分析。"""

    def test_general_dims_recognized(self):
        jd = "任职要求：\n1. 具备良好的沟通能力和责任心。\n2. 有较强的学习能力。"
        reqs, _ = matching.extract_requirements(jd)
        keys = {r.key for r in reqs}
        self.assertTrue({"communication", "ownership", "learning"} <= keys, keys)

    def test_custom_requirement_kept(self):
        jd = "任职要求：\n1. 熟练操作数控机床并读懂机械图纸。"
        reqs, _ = matching.extract_requirements(jd)
        self.assertTrue(any(r.key.startswith("custom:") for r in reqs),
                        [r.key for r in reqs])

    def test_custom_match_by_overlap(self):
        reqs = [matching.Requirement(
            "custom:abc", "数控机床操作", 2, "must",
            quote="熟练操作数控机床并读懂机械图纸。",
        )]
        ms, _ = matching.match(reqs, "在工厂实习时操作过数控机床，能看懂机械图纸。")
        self.assertIn(ms["custom:abc"].status, ("full", "partial"))

    def test_non_ai_job_has_domain_requirements(self):
        jd = "财务会计\n任职要求\n1. 熟悉纳税申报。\n2. 熟练使用金蝶财务软件。"
        reqs, _ = matching.extract_requirements(jd)
        keys = {r.key for r in reqs}
        self.assertTrue({"fin_tax", "fin_software"} <= keys, keys)


class TestRealWorldRegressions(unittest.TestCase):
    """真实简历/真实 JD 暴露过的误判，锁死。"""

    def test_prompt_engineering_is_not_deployment(self):
        jd = "任职要求：\n1. 熟练使用提示词工程，能独立把模型调到一个可用的状态。"
        reqs, _ = matching.extract_requirements(jd)
        keys = {r.key for r in reqs}
        self.assertIn("prompt_eng", keys)
        self.assertNotIn("engineering", keys)

    def test_conversion_rate_is_not_ecommerce(self):
        jd = "任职要求：\n1. 能搭建基础看板、定义漏斗与转化率指标。"
        reqs, _ = matching.extract_requirements(jd)
        keys = {r.key for r in reqs}
        self.assertIn("data_analysis", keys)
        self.assertNotIn("ec_shop", keys)

    def test_prototype_counts_as_ux(self):
        reqs = [matching.Requirement("ds_ux", "交互/UX", 2, "must")]
        res = matching.match_by_rules(reqs, "输出流程图、墨刀原型、完整PRD。")
        self.assertEqual(res["ds_ux"].status, "full")


class TestInternship(unittest.TestCase):
    def test_goal_ranks_matching_direction_first(self):
        prof = ("工商管理本科，做过 AIGC 画师工具，访谈 20+ 画师，"
                "用 ComfyUI 和提示词，写过 PRD 和原型。")
        res = internship.rank(prof, goal="ai")
        self.assertTrue(res[0].goal_match)
        self.assertTrue(all(r.goal_match for r in res[:3]))

    def test_timeline_for_2028(self):
        from datetime import date
        tl = internship.timeline(2028, today=date(2026, 10, 1))
        self.assertEqual(tl[0]["start"], "2026.10")
        self.assertTrue(tl[0]["current"])
        self.assertEqual(tl[-1]["start"], "2028.03")
        self.assertEqual(len(tl), 5)

    def test_presets_available(self):
        self.assertGreaterEqual(len(internship.load_presets()), 8)


class TestLLMWiring(unittest.TestCase):
    def test_llm_mode_is_used_when_available(self):
        class FakeLLM:
            available = True

            def json(self, system, user):
                if "requirements" in system:
                    return {"requirements": [{
                        "key": "python", "label": "Python", "weight": 2,
                        "kind": "must", "quote": "要求熟悉 Python",
                    }]}
                return {"matches": [{
                    "key": "python", "status": "full",
                    "evidence": "用 Python 写了服务",
                }]}

        fake = FakeLLM()
        reqs, mode = matching.extract_requirements("要求熟悉 Python。", fake)
        self.assertEqual(mode, "llm")
        self.assertEqual([r.key for r in reqs], ["python"])

        matches, used = matching.match(reqs, "用 Python 写了服务。", fake)
        self.assertEqual(used, "llm")
        self.assertEqual(matches["python"].status, "full")

    def test_doctor_runs(self):
        from career_loop import cli
        self.assertEqual(cli.main(["doctor"]), 0)


class TestDotenv(unittest.TestCase):
    def test_parse_env_file(self):
        from career_loop.cli import _parse_env_file
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text(
                'OPENAI_API_KEY="sk-x"\n'
                "export OPENAI_MODEL=deepseek-flash\n"
                "# comment\n"
                "NOT_A_PAIR\n",
                encoding="utf-8",
            )
            env = _parse_env_file(p)
            self.assertEqual(env["OPENAI_API_KEY"], "sk-x")
            self.assertEqual(env["OPENAI_MODEL"], "deepseek-flash")
            self.assertNotIn("NOT_A_PAIR", env)


class TestCliDbRouting(unittest.TestCase):
    """锁住 CLI 一定要把 --db 透传给 store，别串到默认库。"""

    def test_apply_and_log_use_given_db(self):
        from career_loop import cli

        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "c.db")
            prof = os.path.join(d, "p.md")
            jd = os.path.join(d, "j.md")
            Path(prof).write_text("用 Python 写了后端服务。", encoding="utf-8")
            Path(jd).write_text("# 后端\n任职要求：精通 Python。", encoding="utf-8")
            self.assertEqual(cli.main(["--db", db, "init"]), 0)
            self.assertEqual(cli.main(["--db", db, "add-profile", "--name", "me", "--file", prof]), 0)
            self.assertEqual(cli.main(["--db", db, "add-jd", "--file", jd]), 0)
            self.assertEqual(cli.main(["--db", db, "apply", "--jd-id", "1", "--profile-id", "1"]), 0)
            self.assertEqual(cli.main(["--db", db, "log", "--app-id", "1", "--status", "interview"]), 0)
            rows = store.list_applications(db)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "interview")

    def test_collect_missing_dir_returns_error(self):
        from career_loop import cli

        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "c.db")
            rc = cli.main(["--db", db, "collect", "--dir", os.path.join(d, "nope")])
            self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
