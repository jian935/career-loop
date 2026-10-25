"""core 行为契约：抽取、匹配、校准、评测。"""

import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from career_loop import calibrate, collect, daily, dashdata, explore, internship, matching, recommend, reflow, store
from career_loop.cli import build_parser
from career_loop.eval import load_dataset, run_eval
# 注意：matching 包把 render 函数重导出到同名位置了，
# 所以必须 from ...render import，from career_loop.matching import render 拿到的是函数。
from career_loop.matching.render import _verdict, render as render_fn
from career_loop.matching import taxonomy_cn


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


class TestGenericWordRegressions(unittest.TestCase):
    """词表扩到 65 个岗位族后，通用词把 JD 归错族的误判，锁死。

    这些词的共同特点：单看词本身没错，但在别的岗位语境里是通用动作，
    一旦放进某个族就会凭空造出一个「缺口」。
    """

    def test_solution_design_is_not_consulting_delivery(self):
        jd = "任职要求\n1. 负责 MaaS 平台、知识库平台等核心产品的方案设计。"
        keys = {r.key for r in matching.extract_requirements(jd)[0]}
        self.assertNotIn("csl_delivery", keys, keys)

    def test_monitoring_effect_is_not_devops_monitoring(self):
        jd = "任职要求\n1. 制定大模型业务效果评估标准，监控并保障模型落地效果。"
        keys = {r.key for r in matching.extract_requirements(jd)[0]}
        self.assertNotIn("devops_monitor", keys, keys)

    def test_reading_papers_is_not_research(self):
        jd = "任职要求\n1. 英文能力良好，可查阅海外 AI 资料、论文、竞品动态。"
        keys = {r.key for r in matching.extract_requirements(jd)[0]}
        self.assertNotIn("rs_paper", keys, keys)

    def test_competitor_analysis_is_not_consulting(self):
        jd = "任职要求\n1. 负责需求挖掘、竞品分析、数据复盘。"
        keys = {r.key for r in matching.extract_requirements(jd)[0]}
        self.assertNotIn("csl_industry", keys, keys)
        self.assertIn("data_analysis", keys, keys)

    def test_short_keyword_not_crowded_out(self):
        """词表变大后，一行可能命中十几个能力；两字词不能被长词挤掉。"""
        from career_loop.matching.match import _claim_lines, _profile_lines
        line = ("2028届工商管理本科应届生，熟悉商业供应链逻辑，深耕AIGC应用实践，"
                "熟练掌握提示词工程、主流大模型、ComfyUI绘图工作流，"
                "梳理了画师业务流程并定位到三个最大痛点。")
        owned = _claim_lines(_profile_lines(line))
        self.assertIn("domain", owned, sorted(owned))
        self.assertIn("prompt_eng", owned, sorted(owned))

    def test_ops_job_still_detects_monitoring(self):
        """上一条收紧了「监控」，运维岗本身不能被误伤。"""
        jd = "任职要求\n1. 搭建监控告警体系，能做故障排查。"
        keys = {r.key for r in matching.extract_requirements(jd)[0]}
        self.assertIn("devops_monitor", keys, keys)

    def test_consulting_job_still_detects_delivery(self):
        jd = "任职要求\n1. 参与咨询项目，能独立开展客户访谈并输出汇报材料。"
        keys = {r.key for r in matching.extract_requirements(jd)[0]}
        self.assertIn("csl_delivery", keys, keys)

    def test_translate_into_solution_is_not_translation(self):
        """「把业务问题翻译成 Agent 方案」是产品话术，不是笔译。"""
        jd = "任职要求\n1. 负责大模型产品的需求设计与落地，把业务问题翻译成 Agent 方案。"
        keys = {r.key for r in matching.extract_requirements(jd)[0]}
        self.assertNotIn("tr_written", keys, keys)

    def test_translation_job_still_detects_translation(self):
        jd = "任职要求\n1. 负责技术文档笔译与本地化，维护术语库。"
        keys = {r.key for r in matching.extract_requirements(jd)[0]}
        self.assertIn("tr_written", keys, keys)

    def test_tax_policy_is_not_civil_service_writing(self):
        """「熟悉国家税务政策」不该被算成公文写作。"""
        jd = "任职要求\n1. 熟悉国家税务政策，能独立完成纳税申报。"
        keys = {r.key for r in matching.extract_requirements(jd)[0]}
        self.assertNotIn("pub_document", keys, keys)
        self.assertIn("fin_tax", keys, keys)

    def test_civil_service_job_still_detects_document(self):
        jd = "任职要求\n1. 能独立起草公文与汇报材料，熟悉相关政策法规。"
        keys = {r.key for r in matching.extract_requirements(jd)[0]}
        self.assertIn("pub_document", keys, keys)


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


class TestFamilyLLMBackend(unittest.TestCase):
    """v0.8.17：岗位族识别的可选 LLM 后端（默认行为必须与规则逐字节一致）。"""

    class _FakeLLM:
        available = True

        def __init__(self, reply=None, exc=None):
            self._reply = reply
            self._exc = exc
            self.calls = 0

        def json(self, system, user):
            self.calls += 1
            if self._exc:
                raise self._exc
            return self._reply

    def test_valid_json_families(self):
        fake = self._FakeLLM({"families": ["service", "retail"], "confidence": 0.9})
        fams = matching.detect_family_llm("接听客户来电，处理投诉。门店陈列补货。", fake)
        self.assertEqual(fams, ["service", "retail"])

    def test_unknown_family_filtered_chinese_name_mapped(self):
        fake = self._FakeLLM({"families": ["客服", "product_manager", "retail"]})
        fams = matching.detect_family_llm("接听客户来电。", fake)
        self.assertEqual(fams, ["service", "retail"])  # 中文名映射 + 未知族丢弃

    def test_ai_parent_derived_from_subfamily(self):
        fake = self._FakeLLM({"families": ["ai_nlp"]})
        fams = matching.detect_family_llm("做文本分类与微调。", fake)
        self.assertEqual(fams, ["ai_nlp", "ai"])  # 镜像规则的父族推导

    def test_malformed_reply_raises(self):
        fake = self._FakeLLM({"nothing": 1})
        with self.assertRaises(matching.LLMError):
            matching.detect_family_llm("任何文本", fake)

    def test_llm_failure_falls_back_to_rules_with_note(self):
        jd = "负责客服接线与投诉处理。"
        fake = self._FakeLLM(exc=matching.LLMError("HTTP 401"))
        v = matching.detect_families(jd, fake, mode="llm")
        self.assertEqual(v.used, "rules")
        self.assertIn("service", v.families)
        self.assertIn("回退", v.note)

    def test_no_llm_falls_back_to_rules(self):
        jd = "负责客服接线与投诉处理。"
        for mode in ("llm", "auto"):
            v = matching.detect_families(jd, None, mode=mode)
            self.assertEqual(v.used, "rules")
            self.assertIn("未配置", v.note)

    def test_auto_skips_llm_when_rules_hit(self):
        class ExplodingLLM(self._FakeLLM):
            def json(self, system, user):
                raise AssertionError("auto 模式不该在规则命中时调用 LLM")

        jd = "负责客服接线与投诉处理。"
        v = matching.detect_families(jd, ExplodingLLM(), mode="auto")
        self.assertEqual(v.used, "rules")
        self.assertEqual(v.families, matching.detect_domains(jd))

    def test_auto_asks_llm_only_when_rules_empty(self):
        jd = "吃苦耐劳，服从公司各项安排。"
        self.assertEqual(matching.detect_domains(jd), [])  # 前提：规则确实空判
        fake = self._FakeLLM({"families": ["service"]})
        v = matching.detect_families(jd, fake, mode="auto")
        self.assertEqual(v.used, "rules+llm")
        self.assertEqual(v.families, ["service"])
        self.assertEqual(fake.calls, 1)

    def test_rules_mode_never_touches_llm(self):
        fake = self._FakeLLM({"families": ["retail"]})
        v = matching.detect_families("负责客服接线与投诉处理。", fake, mode="rules")
        self.assertEqual(v.used, "rules")
        self.assertEqual(fake.calls, 0)

    def test_blend_orders_llm_first_then_rules_extras(self):
        jd = "负责客服接线与投诉处理，维护客户关系。"
        rules = matching.detect_domains(jd)
        self.assertIn("service", rules)
        fake = self._FakeLLM({"families": ["retail", "service"]})
        v = matching.detect_families(jd, fake, mode="blend")
        self.assertEqual(v.used, "llm+rules")
        self.assertEqual(v.families[0], "retail")      # LLM 首选排最前（top-1 准）
        self.assertEqual(v.families[1], "service")     # 规则命中补后（召回全）
        self.assertEqual(set(v.families), set(["retail"]) | set(rules))

    def test_blend_without_llm_falls_back_to_rules(self):
        jd = "负责客服接线与投诉处理。"
        v = matching.detect_families(jd, None, mode="blend")
        self.assertEqual(v.used, "rules")
        self.assertIn("未配置", v.note)
        self.assertEqual(v.families, matching.detect_domains(jd))

    def test_blend_llm_failure_falls_back_to_rules(self):
        jd = "负责客服接线与投诉处理。"
        fake = self._FakeLLM(exc=matching.LLMError("网络错误"))
        v = matching.detect_families(jd, fake, mode="blend")
        self.assertEqual(v.used, "rules")
        self.assertIn("回退", v.note)

    def test_prompt_covers_every_family(self):
        from career_loop.matching.schema import DOMAIN_PACKS, FAMILY_CN
        prompt = matching.family_llm.family_system_prompt()
        for key in list(DOMAIN_PACKS) + ["ai"]:
            self.assertIn(f"- {key}：", prompt)
        # FAMILY_CN 必须恰好覆盖词表族 + ai 父族，防止新增族静默漏名
        self.assertEqual(set(FAMILY_CN), set(DOMAIN_PACKS) | {"ai"})

    def test_cli_domains_command(self):
        from career_loop import cli
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "jd.md"
            p.write_text("岗位职责：接听客户来电，处理投诉与退换货。\n", encoding="utf-8")
            self.assertEqual(cli.main(["domains", "--file", str(p), "--backend", "rules"]), 0)


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

    def test_llm_can_add_new_capability(self):
        class FakeLLM:
            available = True

            def json(self, system, user):
                return {"requirements": [
                    {"key": "custom:tea_brewing", "label": "茶艺冲泡",
                     "weight": 2, "kind": "must", "quote": "熟悉六大茶类冲泡"},
                    {"key": "tea_cert", "label": "茶艺证书",
                     "weight": 1, "kind": "nice", "quote": "持有中级茶艺师证书"},
                ]}

        reqs, mode = matching.extract_requirements("茶艺师\n任职要求\n熟悉六大茶类冲泡。", FakeLLM())
        keys = {r.key for r in reqs}
        self.assertEqual(mode, "llm")
        self.assertIn("custom:tea_brewing", keys)
        self.assertIn("llm:tea_cert", keys)

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


class TestExplore(unittest.TestCase):
    def test_load_jobs_jsonl(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "jobs.jsonl"
            p.write_text(json.dumps({
                "id": "1", "title": "后端", "company": "X",
                "category": "SWE", "description": "要求 Python。",
            }, ensure_ascii=False) + "\n", encoding="utf-8")
            jobs = explore.load_jobs(str(p))
            self.assertEqual(jobs[0]["title"], "后端")
            self.assertEqual(jobs[0]["category"], "SWE")

    def test_detect_level(self):
        self.assertEqual(explore.detect_level("Senior Product Manager"), "senior")
        self.assertEqual(explore.detect_level("Director of Operations"), "exec")
        self.assertEqual(explore.detect_level("Product Manager Intern"), "intern")
        self.assertEqual(explore.detect_level("Associate Product Manager"), "junior")
        self.assertNotEqual(explore.detect_level("Engineering Manager - Security Standard"), "intern")
        self.assertEqual(explore.detect_level("Engineering Manager"), "senior")
        self.assertEqual(explore.detect_level("X", "", "Entry-level"), "junior")
        self.assertEqual(explore.detect_level("X", "", "Senior"), "senior")

    def test_scan_penalizes_senior(self):
        prof = "用 Python 写了后端服务。"
        jobs = [
            {"id": "s", "title": "高级后端工程师", "company": "A", "category": "SWE",
             "description": "任职要求：精通 Python。"},
            {"id": "j", "title": "初级后端工程师", "company": "B", "category": "SWE",
             "description": "任职要求：精通 Python。"},
        ]
        rep = explore.scan(prof, jobs, llm=None, level="junior")
        self.assertEqual(rep.jobs[0].title, "初级后端工程师")

    def test_scan_rules(self):
        prof = "用 Python 写了后端服务。"
        jobs = [
            {"id": "1", "title": "后端", "company": "A", "category": "SWE",
             "description": "任职要求：精通 Python。"},
            {"id": "2", "title": "设计", "company": "B", "category": "Design",
             "description": "任职要求：熟练使用 Figma。"},
        ]
        rep = explore.scan(prof, jobs, llm=None)
        self.assertEqual(rep.total, 2)
        self.assertEqual(rep.categories, 2)
        self.assertEqual(rep.jobs[0].title, "后端")
        self.assertGreaterEqual(rep.jobs[0].score, rep.jobs[1].score)


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


class TestNegationScope(unittest.TestCase):
    """否定辖域判定：否定词 + 动作词 不能被当成正向证据。

    早期实现用固定短语表穷举否定词（"没做过"/"没用过"…），
    于是「没搭建过工作流」「没独立负责过项目」「没写过正式文档」
    这类**否定词 + 动作词**的组合因为没被短语表覆盖，被判成了 full。
    改成按辖域判定后这类句子一律降级，且不能误伤肯定句。
    """

    JD = "需要有 Agent 开发经验，能搭建多智能体工作流。"

    def _status(self, profile: str, jd: str | None = None) -> str:
        reqs, _ = matching.extract_requirements(jd or self.JD, None)
        got = matching.match_by_rules(reqs, profile).get("agent")
        return got.status if got else "missing"

    def test_negated_action_is_not_full(self):
        self.assertNotEqual(self._status("没搭建过多智能体工作流"), "full")

    def test_negated_action_is_partial(self):
        self.assertEqual(self._status("没搭建过多智能体工作流"), "partial")

    def test_negation_scope_spans_filler_words(self):
        # 「没自己独立搭建过」——否定词与动作词之间隔着填充词，辖域仍成立
        self.assertEqual(
            self._status("了解 Agent 的基本概念，跟过教程但没自己独立搭建过工作流。"),
            "partial",
        )

    def test_limiter_weakens_evidence(self):
        # 「只在课程作业里跑通过」——动作被"只"限定，不算完整落地
        self.assertEqual(
            self._status("没搭建过多智能体工作流，只在课程作业里跑通过单 Agent 例子。"),
            "partial",
        )

    def test_inhibitors_are_not_negation(self):
        # 「不仅…还…」/「不断…」/「未来…」整体是肯定语义
        for profile in (
            "不仅实现了 Agent 工作流，还落地到生产环境",
            "不断迭代优化了 Agent 流程",
        ):
            self.assertEqual(self._status(profile), "full", profile)

    def test_positive_sentence_still_full(self):
        self.assertEqual(self._status("独立搭建过多智能体 Agent 工作流并上线"), "full")

    def test_other_capability_action_does_not_leak(self):
        # 后半句的"落地"属于别的能力，不能拿来给 Agent 当正向证据
        jd = "需要有良好的文案与文档撰写能力。"
        reqs, _ = matching.extract_requirements(jd, None)
        got = matching.match_by_rules(reqs, "没写过正式文档，但独立落地过内容运营项目。")
        self.assertEqual(got["writing"].status, "partial")


class TestEnglishJDNoise(unittest.TestCase):
    """英文 JD 的模板噪声不能变成能力要求。

    实测公开英文数据集：custom 垃圾项占抽取总数 29.5%，
    严重稀释匹配分的区分度（缺口清单里全是 "ESSENTIAL DUTIES" 这类标题）。
    """

    def _custom_labels(self, jd: str) -> list[str]:
        reqs, _ = matching.extract_requirements(jd, None)
        return [r.label for r in reqs if r.key.startswith("custom:")]

    def test_uppercase_heading_is_not_a_requirement(self):
        # 标题行本身被滤掉，但下面那句真实要求仍要抽出来（custom 项）
        jd = "MINIMUM EDUCATION\nBachelor's degree required."
        labels = self._custom_labels(jd)
        self.assertEqual(len(labels), 1, labels)
        self.assertNotIn("MINIMUM EDUCATION", labels[0])

    def test_url_line_is_not_a_requirement(self):
        jd = "APPLY HERE\nHTTPS://WWW.INDEED.COM/JOB/DIRECTOR-9C0196508A30CB63"
        self.assertEqual(self._custom_labels(jd), [])

    def test_greeting_line_is_not_a_requirement(self):
        jd = "HELLO FOLKS,HOPE YOU ARE HAVING A GREAT DAY."
        self.assertEqual(self._custom_labels(jd), [])

    def test_real_requirement_still_extracted(self):
        jd = "ESSENTIAL DUTIES\nManage a team of 5-25 executive consultants in marketing."
        reqs, _ = matching.extract_requirements(jd, None)
        customs = [r for r in reqs if r.key.startswith("custom:")]
        self.assertEqual(len(customs), 1, [r.label for r in customs])
        self.assertIn("consultants", customs[0].quote)
        self.assertNotIn("ESSENTIAL DUTIES", customs[0].quote)


class TestSalesFamilyDiscriminators(unittest.TestCase):
    """sales 族用真实数据补的判别词，不许误伤别的族。

    这些词来自公开数据集 SALES 类的 clean_skills 统计，
    补进来后 SALES 族识别从 69.8% 提到 78.4%（总体 91.9% → 93.6%）。
    """

    def test_sales_jd_detected_as_sales(self):
        from career_loop.matching.schema import detect_domains

        jd = (
            "Job title: Sales Representative Category: SALES "
            "Skills: relationship building, customer relationship management, "
            "lead generation, b2b sales, sales techniques, account management."
        )
        self.assertIn("sales", detect_domains(jd))

    def test_new_sales_words_do_not_steal_hr(self):
        from career_loop.matching.schema import detect_domains

        jd = "Job title: HR Manager Category: HR Skills: recruiting, employee engagement, training."
        self.assertIn("hr", detect_domains(jd))

    def test_new_sales_words_do_not_steal_finance(self):
        from career_loop.matching.schema import detect_domains

        jd = "Job title: Accountant Category: FINANCE Skills: accounting, budgeting, tax, gaap."
        self.assertIn("finance", detect_domains(jd))


class TestChineseInlineJD(unittest.TestCase):
    """中文 JD 常把整份 JD 压在一行里，不拆会漏掉大量要求。

    真实写法（来自一批真实中文 JD）：

        岗位职责：1、负责智能家电MCU固件开发；2、调试外设驱动、蓝牙通信；
        3、版本自测、bug闭环。任职要求：1、自动化/电子；2、熟悉C语言；…

    不拆的话整段被当成一行，canonical_hits 只能命中一个词
    （实测这类 JD 平均只抽出 1 个能力项，"蓝牙通信""示波器"全漏）。
    """

    JD = ("岗位职责：1、参与云原生存储组件的设计、编码与单元测试；2、跟进线上问题排查、性能调优；"
          "3、参与技术方案评审，沉淀技术文档。任职要求：1、计算机相关本科及以上；"
          "2、熟悉Go/C++，了解Linux内核、RPC框架；3、熟悉Redis、MySQL等存储；4、有K8s、etcd相关项目优先。")

    def test_inline_segments_are_split(self):
        from career_loop.matching.extract import _split_sections

        segs = [line for _, line in _split_sections(self.JD)]
        self.assertGreaterEqual(len(segs), 6, segs)
        self.assertTrue(any("Linux内核" in s for s in segs), segs)
        self.assertTrue(any("MySQL" in s for s in segs), segs)

    def test_inline_split_keeps_section_weights(self):
        from career_loop.matching.extract import _split_sections

        secs = {line: sec for sec, line in _split_sections(self.JD)}
        # 「有K8s、etcd相关项目优先」里的"优先"不能被当成 nice 段标题
        k8s = [s for s in secs if "K8s" in s]
        self.assertTrue(k8s)
        self.assertEqual(secs[k8s[0]], "must", secs)

    def test_inline_split_keeps_real_duties(self):
        from career_loop.matching.extract import _split_sections

        segs = [line for _, line in _split_sections(self.JD)]
        # 「跟进线上问题排查」动词不在标题表里，但它是真实职责，不能丢
        self.assertTrue(any("线上问题排查" in s for s in segs), segs)

    def test_inline_split_improves_recall(self):
        reqs, _ = matching.extract_requirements(self.JD, None)
        keys = {r.key for r in reqs}
        self.assertIn("be_db", keys)          # Redis / MySQL
        self.assertIn("devops_linux", keys)   # Linux 内核
        self.assertIn("writing", keys)        # 技术文档


class TestChineseVocabFromRealData(unittest.TestCase):
    """从真实中文 JD 补的词，要能命中且不误伤其他族。"""

    def test_embedded_keywords_hit(self):
        jd = "岗位职责：1、负责智能家电MCU固件开发；2、调试外设驱动、蓝牙通信。任职要求：1、熟悉C语言；2、了解蓝牙协议。"
        reqs, _ = matching.extract_requirements(jd, None)
        keys = {r.key for r in reqs}
        self.assertIn("emb_mcu", keys, keys)

    def test_devops_keywords_hit(self):
        jd = "岗位职责：1、参与云原生存储组件的设计与编码。任职要求：1、熟悉K8s、etcd相关项目优先。"
        reqs, _ = matching.extract_requirements(jd, None)
        keys = {r.key for r in reqs}
        self.assertTrue({"devops_container", "be_db"} & keys, keys)

    def test_new_words_do_not_steal_hr(self):
        jd = "岗位职责：1、负责员工招聘与绩效管理。任职要求：1、熟悉kpi体系；2、有培训经验优先。"
        reqs, _ = matching.extract_requirements(jd, None)
        keys = {r.key for r in reqs}
        self.assertIn("hr_recruit", keys, keys)

    def test_overgeneric_ts_is_not_frontend(self):
        # "ts" 会命中 "consultan-ts"，属于过泛词，不能进前端族
        jd = "ESSENTIAL DUTIES\nManage a team of 5-25 executive consultants in marketing."
        reqs, _ = matching.extract_requirements(jd, None)
        self.assertNotIn("fe_framework", {r.key for r in reqs})


class TestCrossEngineConsistency(unittest.TestCase):
    """网页 JS 引擎必须和 Python 引擎抽出一模一样的能力项。

    网页 demo 是 Python 引擎的手写移植版。两边一旦有差异，
    评委在网页上看到的匹配结果就会和 CLI 不一样——对主打「可证伪」的
    项目是致命的。所以用真实中文 JD 逐条比对（scripts/cross_engine_check.py）。
    """

    def test_cross_engine_check_passes(self):
        import subprocess
        import sys
        from pathlib import Path

        root = Path(__file__).parent.parent
        script = root / "scripts" / "cross_engine_check.py"
        if not script.exists():
            self.skipTest("cross_engine_check.py 不存在")
        node = r"C:\Users\llj12\.workbuddy\binaries\node\versions\22.22.2-6\node.exe"
        if not Path(node).exists():
            self.skipTest("本机没有 node，跳过跨引擎比对")
        res = subprocess.run(
            [sys.executable, str(script), "--limit", "12"],
            capture_output=True, text=True, encoding="utf-8", cwd=str(root),
        )
        self.assertEqual(res.returncode, 0, res.stdout[-1500:] + res.stderr[-800:])

    def test_inline_split_exists_in_webpage_js(self):
        """网页 JS 必须有中文内联切分，否则中文 JD 只能抽出 1 项。"""
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent.parent
        html = (root / "docs" / "index.html").read_text(encoding="utf-8")
        self.assertIn("function splitInlineSegments", html)
        self.assertIn("function isNoiseLine", html)
        # 分节标记里要有英文的
        self.assertIn("essential duties", html)


class TestChineseVocabularyCoverage(unittest.TestCase):
    """用公开中文 JD 数据集补的词，要能命中，且不误伤其他族。

    公开数据集：HuggingFace ngtranai09/china_job（8,674 条真实中文招聘 JD）。
    中文族识别从 72.2% 提到 77.8% 就是靠这批词。
    """

    def _detect(self, text: str) -> list[str]:
        from career_loop.matching.schema import detect_domains

        return detect_domains(text)

    def test_customer_service_words_hit(self):
        jd = "岗位职责：1、负责在线客户咨询解答，处理工单记录与客户问题跟进。"
        self.assertIn("service", self._detect(jd))

    def test_project_management_words_hit(self):
        jd = "岗位职责：1、负责项目进度管理与项目交付，协调资源确保项目按期落地。"
        self.assertIn("project_mgmt", self._detect(jd))

    def test_banking_words_hit(self):
        jd = "岗位职责：1、负责信用卡消费信贷审批与贷后管理，排查逾期风险。"
        self.assertIn("banking", self._detect(jd))

    def test_legal_words_hit(self):
        jd = "岗位职责：1、负责合同起草与审核，参与知识产权相关法务工作。"
        self.assertIn("legal", self._detect(jd))

    def test_generic_consulting_word_is_not_used(self):
        # 「咨询」在 9.3% 的中文 JD 里都出现（含保险咨询/招聘咨询），过泛，
        # 只能用「咨询顾问/管理咨询/咨询项目」这类具体组合
        from career_loop.matching.schema import DOMAIN_PACKS

        csl = DOMAIN_PACKS["consulting"]
        kws = {k for spec in csl.values() for k in spec["kw"]}
        self.assertNotIn("咨询", kws)
        self.assertNotIn("顾问", kws)
        self.assertIn("咨询顾问", kws)

    def test_new_words_do_not_steal_ai_roles(self):
        jd = "岗位职责：1、负责大模型算法研发，训练推荐模型并搭建 RAG 检索链路。"
        preds = self._detect(jd)
        self.assertIn("ai", preds, preds)

    def test_machine_learning_basics_is_covered(self):
        # 「机器学习基础」曾完全不在词表里（中文 AI 岗最普遍的门槛要求）
        jd = "任职要求：1、统计/数学/计算机；2、熟悉Python、Pandas；3、了解机器学习基础。"
        reqs, _ = matching.extract_requirements(jd, None)
        self.assertIn("llm_basics", {r.key for r in reqs})

    def test_machine_learning_word_is_not_overgeneric(self):
        # 「机器学习」不能出现在与 AI 无关的族里
        from career_loop.matching.schema import ALL_DIMS

        owners = [k for k, spec in ALL_DIMS.items()
                  if any("机器学习" in kw for kw in spec["kw"])]
        self.assertEqual(owners, ["llm_basics"], owners)


class TestReflowCalibration(unittest.TestCase):
    """投递回流分析的口径锁定。

    这些测试的作用是**防止口径漂移**：状态映射、归因、方向分类一旦被改动，
    历史报告里的 r 就对不上了，而且没人会发现。
    """

    def test_early_status_only_counts_real_recruiter_action(self):
        # 平台状态词不算招聘方动作 → 不算正反馈
        for text in ("待联系", "待笔试通知", "待HR跟进", "HR未查看", "简历已读，暂未回复"):
            self.assertEqual(
                reflow.normalize_early_status(text), reflow.STATUS_APPLIED, text
            )
        # 招聘方真的动了 → 正反馈
        for text in ("HR发起沟通", "HR感兴趣", "简历被标记有意向", "简历初筛通过",
                     "发起面试邀约"):
            self.assertIn(
                reflow.normalize_early_status(text), reflow.EARLY_POSITIVE, text
            )

    def test_terminal_only_offer_is_positive(self):
        # 终局口径：进面试但淘汰不是正反馈
        self.assertEqual(
            reflow.normalize_terminal_outcome("面试环节淘汰"),
            reflow.STATUS_INTERVIEW_ELIMINATED,
        )
        self.assertNotIn(
            reflow.STATUS_INTERVIEW_ELIMINATED, reflow.TERMINAL_POSITIVE
        )
        self.assertIn(reflow.STATUS_OFFER, reflow.TERMINAL_POSITIVE)
        self.assertEqual(
            reflow.normalize_terminal_outcome("发放offer"), reflow.STATUS_OFFER
        )
        self.assertEqual(
            reflow.normalize_terminal_outcome("简历筛选拒绝"), reflow.STATUS_REJECTED
        )
        self.assertEqual(
            reflow.normalize_terminal_outcome("无反馈沉默"), reflow.STATUS_SILENT
        )

    def test_modes_give_different_positive_sets(self):
        # 两种口径的正反馈集合必须不同，否则就白分了
        self.assertNotEqual(reflow.EARLY_POSITIVE, reflow.TERMINAL_POSITIVE)
        self.assertLess(
            len(reflow.TERMINAL_POSITIVE), len(reflow.EARLY_POSITIVE)
        )

    def test_rejection_attribution_splits_external_vs_controllable(self):
        self.assertEqual(
            reflow.attribute_rejection("岗位HC冻结，暂缓招聘"),
            reflow.ATTR_EXTERNAL,
        )
        self.assertEqual(
            reflow.attribute_rejection("缺少云原生相关项目经验"),
            reflow.ATTR_CONTROLLABLE,
        )

    def test_direction_classification_is_stable(self):
        self.assertEqual(reflow.classify_direction("推荐算法实习生"), "算法/AI")
        self.assertEqual(reflow.classify_direction("用户增长运营"), "运营/增长")
        self.assertEqual(reflow.classify_direction("安全攻防研究员"), "安全")
        self.assertEqual(reflow.classify_direction("某个不存在的岗位"), "其他")

    def test_load_records_sniffs_csv_columns(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.csv"
            p.write_text(
                "投递ID,公司名称,岗位名称,JD原文,终局结果,回流备注\n"
                "D1,某公司,后端开发,熟悉 Go 与 Redis,发放offer,薪资不错\n"
                "D2,某公司2,前端开发,精通 Vue,简历筛选拒绝,HC 冻结\n",
                encoding="utf-8-sig",
            )
            recs = reflow.load_records(p)
            self.assertEqual(len(recs), 2)
            self.assertEqual(recs[0]["id"], "D1")
            self.assertEqual(recs[0]["company"], "某公司")
            self.assertEqual(recs[0]["role"], "后端开发")
            self.assertIn("Redis", recs[0]["jd_text"])
            self.assertEqual(recs[0]["outcome_text"], "发放offer")
            self.assertEqual(recs[1]["outcome_text"], "简历筛选拒绝")

    def test_load_records_sniffs_jsonl(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.jsonl"
            p.write_text(
                '{"id":"A1","role":"算法","jd_text":"熟悉机器学习","outcome":"发放offer"}\n'
                '{"id":"A2","role":"运营","jd_text":"内容策划","outcome":"简历筛选拒绝"}\n',
                encoding="utf-8",
            )
            recs = reflow.load_records(p)
            self.assertEqual(len(recs), 2)
            self.assertEqual(recs[0]["id"], "A1")
            self.assertEqual(recs[1]["role"], "运营")

    def test_record_without_jd_is_excluded_from_correlation(self):
        """没有 JD 原文的记录只能进漏斗，不能进相关系数。"""
        recs = [
            {"id": "1", "role": "后端开发", "jd_text": "熟悉 Go 与 Redis、MySQL 存储",
             "outcome_text": "发放offer", "note": ""},
            {"id": "2", "role": "前端开发", "jd_text": "", "outcome_text": "简历筛选拒绝",
             "note": "HC 冻结"},
        ]
        res = reflow.analyze_reflow(recs, "熟悉 Go 与 Redis，做过后端开发。", "terminal")
        self.assertEqual(res.total, 2)
        self.assertEqual(len(res.scored_usable), 1)
        # 漏斗统计仍然包含两条
        self.assertEqual(res.status_counts["offer"], 1)
        self.assertEqual(res.status_counts["rejected"], 1)

    def test_score_spread_diagnosis_detects_overlap(self):
        """正负两组分数重叠时，诊断应说"更像数据本身无关"。"""
        recs = []
        for i in range(6):
            recs.append({"id": f"p{i}", "role": "算法工程师",
                         "jd_text": "熟悉 Python 与机器学习",
                         "outcome_text": "发放offer", "note": ""})
        for i in range(6):
            recs.append({"id": f"n{i}", "role": "算法工程师",
                         "jd_text": "熟悉 Python 与机器学习",
                         "outcome_text": "简历筛选拒绝", "note": "缺少项目经验"})
        res = reflow.analyze_reflow(recs, "熟悉 Python，做过机器学习项目。", "terminal")
        self.assertIsNotNone(res.spread)
        self.assertIn("重叠", res.spread.diagnose())

    def test_report_states_mode_and_boundary(self):
        recs = [
            {"id": f"{i}", "role": "后端开发", "jd_text": "熟悉 Go 与 Redis",
             "outcome_text": "发放offer" if i < 3 else "简历筛选拒绝", "note": ""}
            for i in range(8)
        ]
        res = reflow.analyze_reflow(recs, "熟悉 Go，做过后端开发。", "terminal")
        md = reflow.render_report(res, title="T")
        self.assertIn("终局录取", md)
        self.assertIn("匹配分不是录取概率", md)
        self.assertIn("Pearson r", md)

    def test_early_report_warns_terminal_is_different(self):
        recs = [
            {"id": f"{i}", "role": "运营", "jd_text": "内容策划与活动运营",
             "outcome_text": "HR发起沟通" if i < 3 else "已读不回", "note": ""}
            for i in range(8)
        ]
        res = reflow.analyze_reflow(recs, "做过内容运营。", "early")
        md = reflow.render_report(res)
        self.assertIn("早期信号 ≠ 终局结果", md)

    def test_unknown_mode_raises(self):
        with self.assertRaises(ValueError):
            reflow.analyze_reflow([], "x", "bogus")


class TestAnonymizationAudit(unittest.TestCase):
    """脱敏审计脚本的自测。

    一个只会说"通过"的检查脚本毫无价值——必须验证它**真能抓到泄露**，
    同时**不误报**正常的行业名词。
    """

    @staticmethod
    def _audit(text: str, rows: list[dict]) -> list[str]:
        import importlib.util
        import tempfile

        root = Path(__file__).parent.parent.parent
        spec = importlib.util.spec_from_file_location(
            "audit_anon", root / "scripts" / "audit_anonymization.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.md"
            p.write_text(text, encoding="utf-8")
            return mod.audit_file(p, rows)

    def setUp(self):
        self.rows = [
            {"id": "D1", "company": "旷视", "role": "AI产品经理",
             "outcome": "简历筛选拒绝", "note": "缺少To G项目经验"},
            {"id": "D2", "company": "商汤", "role": "智慧城市解决方案",
             "outcome": "面试环节淘汰", "note": "售前方案汇报逻辑不够清晰"},
        ]

    def test_clean_report_passes(self):
        text = "| D1 | 企业 28 | AI产品经理 | 61.1 | 9 | 2 | rejected |"
        self.assertEqual(self._audit(text, self.rows), [])

    def test_real_company_with_role_on_same_line_is_caught(self):
        text = "| D1 | 旷视 | AI产品经理 | 61.1 | rejected |"
        problems = self._audit(text, self.rows)
        self.assertTrue(problems, problems)

    def test_original_note_is_caught(self):
        problems = self._audit("缺少To G项目经验", self.rows)
        self.assertTrue(problems, problems)

    def test_personal_info_is_caught(self):
        problems = self._audit("陈默，塔里木大学工商管理", self.rows)
        self.assertTrue(problems, problems)

    def test_industry_name_alone_is_not_a_leak(self):
        # 「用友」「金蝶」是词表里的财务软件行业名词，单独出现不是泄露
        text = "财务软件(用友/金蝶/SAP) 词表条目"
        self.assertEqual(self._audit(text, self.rows), [])

    def test_company_name_alone_is_not_a_leak(self):
        # 公司名出现在行业讨论里、且没有和具体岗位/结果同行 → 不是泄露
        text = "商汤在计算机视觉领域有代表性"
        self.assertEqual(self._audit(text, self.rows), [])


class TestGenericWordContextGuard(unittest.TestCase):
    """过泛词的语境约束（v0.8.13）。

    背景：真实中文 JD 实测发现，「服务」在 465 条 JD 里是"服务质量/服务标准"
    （物流运营语境），却被算成「工程落地与部署」；
    「证照」多为"资质证件"而非「档案管理」。
    实测误抽率：engineering 精确率 44%、adm_archive 仅 8%。
    修复后：92.7% / 92.1%，且召回几乎没损失。
    """

    def _keys(self, jd: str) -> set:
        reqs, _ = matching.extract_requirements(jd, None)
        return {r.key for r in reqs}

    def test_service_quality_is_not_engineering(self):
        jd = "岗位职责：提升服务质量、建立服务标准，打造热心的服务团队。"
        self.assertNotIn("engineering", self._keys(jd))

    def test_real_engineering_still_recognized(self):
        jd = "任职要求：熟悉后端开发，熟练使用 Docker 部署数据库服务。"
        self.assertIn("engineering", self._keys(jd))

    def test_license_is_not_archive_management(self):
        # 「办理证照」是资质事务，不是档案管理——语境表里不能有「年检」这种会误判的词
        jd = "岗位职责：负责公司各类证照的办理与变更对接。"
        self.assertNotIn("adm_archive", self._keys(jd))

    def test_license_archive_management_is_recognized(self):
        # 真正做资质档案管理的还是要认出来
        jd = "岗位职责：负责资质证照的档案归档与用印管理。"
        self.assertIn("adm_archive", self._keys(jd))

    def test_real_archive_still_recognized(self):
        jd = "岗位职责：负责档案归档、印章用印管理与档案借阅登记。"
        self.assertIn("adm_archive", self._keys(jd))

    def test_generic_word_alone_does_not_trigger(self):
        # 「业务」单独出现不应触发 domain
        jd = "岗位职责：负责业务对接与客户服务。"
        self.assertNotIn("domain", self._keys(jd))

    def test_domain_context_still_recognized(self):
        jd = "需要深入理解某业务场景的痛点与流程。"
        self.assertIn("domain", self._keys(jd))

    def test_context_guard_is_synced_to_webpage(self):
        """语境约束表必须同步到网页，否则两边结果会不一致。"""
        from pathlib import Path

        root = Path(__file__).parent.parent.parent
        html = (root / "docs" / "index.html").read_text(encoding="utf-8")
        self.assertIn("const CONTEXT_REQUIRED", html)
        self.assertIn("function contextOk", html)
        # 表里不能出现能力项自己的泛词（否则等于没约束）
        from career_loop.matching.schema import CONTEXT_REQUIRED

        for key, words in CONTEXT_REQUIRED.items():
            generic = {"engineering": "服务", "domain": "业务",
                       "product_sense": "需求", "adm_archive": "证照"}[key]
            self.assertNotIn(generic, words,
                             f"{key} 的语境表里不能含自己的泛词 {generic!r}")


class TestRealJDExtractionSet(unittest.TestCase):
    """真实中文 JD 抽取评测集（v0.8.13，W6 核心）。

    合成短句集（eval_sample.jsonl）测的是"引擎会不会处理这句话"，
    这套测的是"引擎在**真实中文 JD 文本**上抽得准不准"——
    真实 JD 有模板噪声、福利条款、学历要求、跨行内联，合成短句测不出这些。
    """

    @classmethod
    def setUpClass(cls):
        cls.rows = [
            json.loads(l)
            for l in (Path(__file__).parent.parent.parent
                      / "data" / "eval_real_jd.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]

    def _keys(self, text: str) -> list[str]:
        reqs, _ = matching.extract_requirements(text, None)
        return sorted({r.key for r in reqs if not r.key.startswith("custom:")})

    def test_set_is_not_empty_and_has_both_kinds(self):
        kinds = {r["kind"] for r in self.rows}
        self.assertEqual(kinds, {"positive", "negative"}, kinds)
        self.assertGreaterEqual(len(self.rows), 40)

    def test_all_annotated_rows_match(self):
        bad = []
        for r in self.rows:
            got = self._keys(r["text"])
            if got != r["expect"]:
                bad.append((r["id"], r["expect"], got))
        self.assertEqual(bad, [], f"{len(bad)} 条与标注不一致：{bad[:3]}")

    def test_negative_cases_extract_nothing(self):
        """负例：真实 JD 里的非能力行（学历/福利/法律声明）不该抽出能力项。"""
        neg = [r for r in self.rows if r["kind"] == "negative"]
        self.assertGreaterEqual(len(neg), 5)
        for r in neg:
            self.assertEqual(self._keys(r["text"]), [], r["text"])

    def test_covers_many_capabilities(self):
        caps = {k for r in self.rows for k in r["expect"]}
        self.assertGreaterEqual(len(caps), 15, sorted(caps))

    def test_texts_are_real_not_synthetic(self):
        """这些样本应该像真实 JD（带序号、带标点、口语化），不是玩具句子。"""
        import re

        for r in self.rows:
            self.assertGreaterEqual(len(r["text"]), 8, r["text"])
        # 至少一半带真实 JD 的编号格式（全角「3、」或半角「3.」都行）
        numbered = sum(
            1 for r in self.rows
            if re.match(r"^\s*\d+[、.．)）]", r["text"])
            or re.match(r"^[（(]\d+[)）]", r["text"])
        )
        self.assertGreaterEqual(numbered, len(self.rows) // 3,
                                f"只有 {numbered}/{len(self.rows)} 条带编号")


class TestBoilerplateAndFamilyRecall(unittest.TestCase):
    """v0.8.14：平台样板清除 + 弱族词表召回补充的行为契约。

    背景：公开中文 JD 集里 75% 的 JD 带「职位来源于智联招聘」来源声明、
    41% 带反诈免责声明，让 hr/admin 词表假命中；同时 banking/securities/
    legal/healthcare 等族缺核心词（投资经理 JD 判不出 banking）。
    """

    def test_source_attribution_stripped(self):
        from career_loop.matching.boilerplate import strip_boilerplate
        out = strip_boilerplate("该职位来源于智联招聘。 岗位职责：负责档案管理。")
        self.assertNotIn("智联招聘", out)
        self.assertNotIn("招聘", out)
        self.assertIn("档案管理", out)

    def test_antifraud_disclaimer_stripped(self):
        from career_loop.matching.boilerplate import strip_boilerplate
        out = strip_boilerplate(
            "任职要求：本科学历。以担保或任何理由索要财物，扣押证照，均涉嫌违法。")
        self.assertNotIn("扣押证照", out)
        self.assertIn("本科学历", out)

    def test_real_archive_content_kept(self):
        """真行政内容不能被误剥（清除器只认平台特有措辞）。"""
        from career_loop.matching.boilerplate import strip_boilerplate
        src = "负责公司证照、印章管理及年审，组织招聘配置工作。"
        self.assertEqual(strip_boilerplate(src), src)

    def test_boilerplate_does_not_fake_hr_or_admin(self):
        """只有样板 + 中性内容的 JD，不该判出 hr/admin。"""
        jd = "该职位来源于智联招聘。 岗位职责：负责客户对接与资料整理。"
        doms = matching.detect_domains(jd)
        self.assertNotIn("hr", doms)
        self.assertNotIn("admin", doms)

    def test_investment_jd_detects_banking(self):
        """投资经理类 JD 必须判出 banking（修前 60 条 miss 的主类型）。"""
        jd = ("岗位职责：负责投资项目的搜集、储备及筛选，参与尽职调查，"
              "开展投后管理。任职要求：金融、经济相关专业。")
        doms = matching.detect_domains(jd)
        self.assertIn("banking", doms)
        self.assertIn("securities", doms)

    def test_law_firm_jd_detects_legal(self):
        jd = ("岗位职责：独立承办诉讼案件，负责案源拓展。"
              "任职要求：法学专业，持有律师执业证，熟悉律所工作。")
        self.assertIn("legal", matching.detect_domains(jd))

    def test_streamer_jd_detects_film(self):
        """直播/才艺类 JD 文本不出现「主播」二字，也要能判出 film。"""
        jd = "岗位职责：负责直播内容策划与才艺表演，维护粉丝关系。"
        self.assertIn("film", matching.detect_domains(jd))

    def test_seo_jd_detects_operations(self):
        jd = ("岗位职责：负责网站SEO优化，提升搜索引擎排名与关键词覆盖。"
              "任职要求：熟悉建站与网站架构。")
        self.assertIn("operations", matching.detect_domains(jd))

    def test_business_analysis_jd_detects_data_analysis(self):
        """data_analysis 族 v0.8.14 才建成，此前标签不可达。"""
        jd = ("岗位职责：负责业务分析与报表体系建设，沉淀数据分析方法。"
              "任职要求：熟练使用 Tableau 与 SQL。")
        self.assertIn("data_analysis", matching.detect_domains(jd))

    def test_recsys_jd_detects_ai_parent(self):
        """命中 ai_* 子族即应推出 ai 父族（对照集两个 MISS 的修法）。"""
        jd = ("任职要求\n1. 熟悉推荐系统召回与排序链路\n"
              "2. 有特征工程和模型调优经验\n3. 能用 SQL 做数据分析")
        doms = matching.detect_domains(jd)
        self.assertIn("ai_recsys", doms)
        self.assertIn("ai", doms)

    def test_reception_alone_is_not_service(self):
        """「接待」已从 service 词表移除（精确率 2.4%，行政/酒店词）。"""
        jd = "岗位职责：接待来访客户，做好会议服务与秩序维护。"
        self.assertNotIn("service", matching.detect_domains(jd))

    def test_service_jd_without_reception_still_detects_service(self):
        """反向测试：删「接待」不能弄坏真客服 JD 的识别。"""
        jd = ("岗位职责：1. 接听客户来电，处理客户投诉与售后问题 "
              "2. 记录工单并跟进处理结果 3. 维护客户满意度")
        self.assertIn("service", matching.detect_domains(jd))

    def test_quote_excludes_boilerplate(self):
        """抽取出的 quote 不该带免责声明（用户不该在证据里看到它）。"""
        from career_loop.matching.extract import extract_by_rules
        jd = ("该职位来源于智联招聘。\n岗位职责：负责公司档案、印章管理与证照年审。\n"
              "以担保或任何理由索要财物，扣押证照，均涉嫌违法。")
        reqs = extract_by_rules(jd)
        self.assertTrue(reqs)
        for r in reqs:
            self.assertNotIn("扣押证照", r.quote)
            self.assertNotIn("智联招聘", r.quote)

    def test_disclaimer_does_not_create_archive_capability(self):
        """免责声明里的「证照」不该抽出 adm_archive 能力项（修前精确率 8%）。"""
        from career_loop.matching.extract import extract_by_rules
        jd = ("任职要求：本科学历，专业不限。\n"
              "以担保或任何理由索要财物，扣押证照，均涉嫌违法。")
        keys = [r.key for r in extract_by_rules(jd)]
        self.assertNotIn("adm_archive", keys)


class TestLLMProxy(unittest.TestCase):
    """本地 LLM 代理（网页 demo 用它绕开 CORS，并把 Key 留在本机）。"""

    class _FakeLLM:
        model = "fake-model"
        base_url = "http://fake"
        available = True
        stats = {"http_calls": 0, "cache_hits": 0, "failures": 0}

        def __init__(self, reply='{"families":["service"],"confidence":0.9}', fail=None):
            self.reply = reply
            self.fail = fail
            self.calls = []

        def chat(self, system, user, temperature=0.2):
            self.calls.append((system, user))
            if self.fail:
                from career_loop.matching.llm import LLMError
                raise LLMError(self.fail)
            return self.reply

    def _start(self, fake=None, port=0, allow_any_origin=False):
        import threading
        import urllib.error
        import urllib.request
        from career_loop import llm_proxy

        fake = fake or self._FakeLLM()
        handler = type("H", (llm_proxy._Handler,), {
            "llm": fake, "token": "tok-123", "allow_any_origin": allow_any_origin,
        })
        httpd = llm_proxy.ThreadingHTTPServer(("127.0.0.1", port), handler)
        threading.Thread(target=llm_proxy._serve_quietly, args=(httpd,), daemon=True).start()
        self.addCleanup(httpd.shutdown)
        self.addCleanup(httpd.server_close)
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        self.base = base
        self.fake = fake

        def call(path, payload=None, token="tok-123", origin=None, method=None):
            import urllib.error
            import urllib.request
            data = json.dumps(payload).encode() if payload is not None else None
            headers = {"Content-Type": "application/json"}
            if token is not None:
                headers["X-CL-Token"] = token
            if origin:
                headers["Origin"] = origin
            req = urllib.request.Request(base + path, data=data, headers=headers,
                                         method=method or ("POST" if data else "GET"))
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    return resp.status, json.loads(resp.read().decode())
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode()
                try:
                    return exc.code, json.loads(raw)
                except json.JSONDecodeError:
                    return exc.code, {"error": raw[:120]}

        return call

    def test_health_reports_model_and_key(self):
        call = self._start()
        code, body = call("/health")
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["model"], "fake-model")
        self.assertTrue(body["has_key"])

    def test_health_reports_missing_key(self):
        fake = self._FakeLLM()
        fake.available = False
        call = self._start(fake)
        code, body = call("/health")
        self.assertEqual(code, 200)
        self.assertFalse(body["has_key"])

    def test_wrong_token_is_rejected(self):
        call = self._start()
        code, body = call("/llm", {"user": "hi"}, token="wrong")
        self.assertEqual(code, 401)

    def test_missing_user_is_rejected(self):
        call = self._start()
        code, body = call("/llm", {})
        self.assertEqual(code, 400)

    def test_oversized_body_is_rejected_without_connection_reset(self):
        """超限时必须先把请求体读掉，否则客户端收到的是 connection reset 而不是 413。"""
        call = self._start()
        code, body = call("/llm", {"user": "x" * 300_000})
        self.assertEqual(code, 413)
        self.assertIn("error", body)

    def test_foreign_origin_is_rejected(self):
        call = self._start()
        code, body = call("/llm", {"user": "hi"}, origin="https://evil.example")
        self.assertEqual(code, 403)

    def test_local_origin_is_allowed(self):
        call = self._start()
        code, body = call("/llm", {"user": "hi"}, origin="http://localhost:3000")
        self.assertEqual(code, 200)

    def test_successful_call_returns_text(self):
        call = self._start()
        code, body = call("/llm", {"system": "S", "user": "U"})
        self.assertEqual(code, 200)
        self.assertIn("service", body["text"])
        self.assertEqual(self.fake.calls[0], ("S", "U"))

    def test_upstream_error_is_reported_as_502(self):
        call = self._start(self._FakeLLM(fail="HTTP 401: bad key"))
        code, body = call("/llm", {"user": "hi"})
        self.assertEqual(code, 502)
        self.assertIn("401", body["error"])

    def test_model_cannot_be_overridden_by_the_caller(self):
        """网页不能指定模型——否则别人能用你的 Key 去刷更贵的模型。"""
        call = self._start()
        code, body = call("/llm", {"user": "hi", "model": "gpt-4o"})
        self.assertEqual(code, 200)
        self.assertEqual(body["model"], "fake-model")

    def test_binds_loopback_only(self):
        """代理只能绑 127.0.0.1，不能对外暴露。"""
        from career_loop import llm_proxy
        httpd = llm_proxy.ThreadingHTTPServer(("127.0.0.1", 0),
                                              llm_proxy._Handler)
        try:
            self.assertEqual(httpd.server_address[0], "127.0.0.1")
        finally:
            httpd.server_close()


class TestDocsConsistency(unittest.TestCase):
    """中英文 README 的数字对称性 / 链接有效性。

    这个项目的纪律是「数字必须和引擎真实值一致」。英文 README 是新增的，
    两份文档很容易各改一边、悄悄漂移——所以把一致性做成回归锁。
    """

    ROOT = Path(__file__).resolve().parent.parent.parent

    # 关键数字 → 必须同时出现在中英文两版里
    KEY_NUMBERS = (
        "66", "171", "60", "93.6%", "86.0%", "93.4%", "0.193", "56.6%", "73.5%",
        "52%", "78%", "70%", "83%", "45", "10,613", "13.8", "86.2%", "100.0%",
        "1,167", "1,838", "41", "75", "3%", "16", "50", "29", "0.694",
        "-0.059", "0.03", "9,544", "122,560", "8,674", "35+",
    )

    @staticmethod
    def _count_tests() -> int:
        """数出本模块里真实的测试方法数（不看文档怎么说）。

        单测条数以前是写死在 KEY_NUMBERS 里的常量，结果很快就过时了
        （加了新测试没人想起改 README，文档里一直是旧数字）。
        改成从类里数，数字自己走，文档写错就红。
        """
        import inspect
        mod = sys.modules[__name__]
        total = 0
        for _, obj in vars(mod).items():
            if inspect.isclass(obj) and issubclass(obj, unittest.TestCase):
                total += len([m for m in dir(obj) if m.startswith("test")])
        return total

    def test_version_is_consistent_across_manifests(self):
        """版本号必须三处一致：pyproject / CHANGELOG 顶部 / 网页上的角标。

        加这条是因为它真的漂移过——CHANGELOG 已经写到 0.8.21，
        pyproject 还停在 0.8.18，`pip install -e .` 装的包版本是错的。
        """
        import re
        pyproject = (self.ROOT / "pyproject.toml").read_text(encoding="utf-8")
        ver = re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1)
        top = re.search(r"^## \[([^\]]+)\]", (self.ROOT / "CHANGELOG.md").read_text(
            encoding="utf-8"), re.M).group(1)
        self.assertEqual(top, ver, f"CHANGELOG 顶部 {top} ≠ pyproject {ver}")
        self.assertIn(f"v{ver}",
                      (self.ROOT / "docs" / "index.html").read_text(encoding="utf-8"),
                      f"网页角标没跟着升到 v{ver}")

    def test_every_cli_command_is_documented(self):
        """每个已注册的子命令都必须在 README 里出现，反之亦然。

        这条锁来自一次体检：`taxonomy_cn.py` 里有完整的
        `coverage_matrix() / render_coverage()`，README 两处宣称"可对齐到职业
        分类大典"，但全仓库零调用 —— 评审照着文档找不到命令，只能读源码。
        能力的敌人不是写错，是**没有入口**。反过来，README 写了不存在的命令
        同样是假承诺，所以两边都查。
        """
        import re
        from career_loop import cli
        route_names = set(getattr(cli, "ROUTES", {}).keys())
        route_names |= {n for n, m in vars(cli).items()
                        if n.startswith("cmd_") and callable(m)}
        route_names = {n[4:].replace("_", "-") for n in route_names} - {"help"}
        self.assertTrue(route_names, "没抓到任何命令名，检查 cli 结构是否变了")

        zh, en = self._read("README.md"), self._read("README.en.md")
        documented = self._documented_commands(zh) | self._documented_commands(en)
        missing = sorted(route_names - documented)
        phantom = sorted(documented - route_names)
        self.assertTrue(not missing, f"已注册但两版 README 都没提的命令：{missing}")
        self.assertTrue(not phantom, f"README 写了但实际不存在的命令：{phantom}")

    @staticmethod
    def _documented_commands(text: str) -> set[str]:
        """只认**命令行**里的 `career-loop xxx`：代码块内、且出现在一行开头。

        一开始图省事全文正则匹配，结果把英文散文里的
        "career-loop web demo:" "career-loop also asks you to ..." 也当成了命令
        （两条假阳性）。限定两种位置后就干净了：代码块里的命令行，
        以及内联反引号 `` `career-loop xxx` `` —— 后者同样是货真价实的承诺
        （README 里 `domains` / `occupations` 就是这么写的）。
        """
        import re
        out = set()
        blocks = re.findall(r"```(?:bash|sh|shell|console)?\s*\n(.*?)```", text, re.S)
        for block in blocks:
            for line in block.splitlines():
                m = re.match(r"\s*career-loop\s+([a-z][a-z-]*)", line)
                if m:
                    out.add(m.group(1))
        for m in re.finditer(r"`\s*career-loop\s+([a-z][a-z-]*)", text):
            out.add(m.group(1))
        return out

    def test_unit_test_count_matches_readme(self):
        """README 里写的单测条数必须等于实际条数（含 badge）。"""
        n = self._count_tests()
        zh, en = self._read("README.md"), self._read("README.en.md")
        # 用 assertTrue 而不是 assertIn：后者失败时会把整篇 README 打进回溯里
        self.assertTrue(f"{n} 个单元测试" in zh, f"README.md 单测条数应写 {n}")
        self.assertTrue(f"{n} unit tests" in en, f"README.en.md 单测条数应写 {n}")
        self.assertTrue(f"tests-{n}%20passing" in en, "英文 README 徽章上的数字没跟着改")

    @classmethod
    def _read(cls, name: str) -> str:
        path = cls.ROOT / name
        if not path.exists():
            raise unittest.SkipTest(f"{name} 不存在")
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _anchors(text: str) -> set[str]:
        import re
        out = set()
        for line in text.splitlines():
            m = re.match(r"^#{1,6}\s+(.*)$", line)
            if not m:
                continue
            t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", m.group(1).strip())
            t = re.sub(r"[*`~]", "", t).strip().lower()
            t = re.sub(r"[^\w\s-]", "", t)
            out.add(re.sub(r"\s+", "-", t))
        return out

    def test_english_readme_exists(self):
        self.assertTrue((self.ROOT / "README.en.md").exists(),
                        "英文 README 是拿星标的地基，不能被删掉")

    def test_key_numbers_appear_in_both_readmes(self):
        """同一组关键数字必须同时出现在中英文两版里——只改一边就会在这里炸。"""
        zh = self._read("README.md")
        en = self._read("README.en.md")
        missing = [n for n in self.KEY_NUMBERS
                   if not (n in zh and n in en)]
        self.assertEqual(missing, [], f"中英文 README 数字不对称：{missing}")

    def test_internal_anchors_resolve(self):
        """README 内部的目录锚点必须真的指向某个标题（改了标题忘了改链接会在这里炸）。"""
        import re
        for name in ("README.md", "README.en.md"):
            text = self._read(name)
            have = self._anchors(text)
            for link in set(re.findall(r"\]\(#([^)]+)\)", text)):
                self.assertIn(link, have, f"{name} 的锚点 #{link} 没有对应标题")

    def test_referenced_files_exist(self):
        """README 里引用的本地文件必须真实存在（避免 404 链接）。"""
        import re
        pat = re.compile(r"\]\((docs/[^)#]+|examples/[^)#]+|scripts/[^)#]+|"
                         r"data/[^)#]+|LICENSE|README\.md|README\.en\.md)\)")
        for name in ("README.md", "README.en.md"):
            text = self._read(name)
            for path in set(pat.findall(text)):
                self.assertTrue((self.ROOT / path).exists(),
                                f"{name} 引用了不存在的文件：{path}")

    def test_readmes_cross_link_each_other(self):
        """两版必须互链，否则英文读者找不到中文版、反之亦然。"""
        self.assertIn("README.en.md", self._read("README.md"))
        self.assertIn("README.md", self._read("README.en.md"))

    def test_video_duration_claim_is_consistent(self):
        """视频实际 135 秒 = 2 分 15 秒；两版 README 都不能再写"3 分钟"。"""
        for name in ("README.md", "README.en.md"):
            text = self._read(name)
            self.assertNotIn("3 分钟演示视频", text, f"{name} 仍把视频写成 3 分钟")
            self.assertNotIn("3-minute demo video", text, f"{name} 仍把视频写成 3 分钟")


class TestDailyPlan(unittest.TestCase):
    """每日投递清单。

    这块最容易出错的是**日期**：从 JD 里抓截止日是启发式，
    抓错比抓不到更糟（用户会照着错的日期安排投递）。所以边界用例写得多。
    """

    DAY = date(2026, 10, 26)

    def test_full_date_near_cue(self):
        got = daily.find_deadline("投递截止：2026年11月30日，逾期不再接受。", self.DAY)
        self.assertEqual(got, ("2026-11-30", "JD 原文"))

    def test_dashed_and_slashed_formats(self):
        self.assertEqual(daily.find_deadline("截止 2026-11-30", self.DAY)[0], "2026-11-30")
        self.assertEqual(daily.find_deadline("deadline: 2026/12/01", self.DAY)[0], "2026-12-01")

    def test_year_omitted_uses_this_year(self):
        """JD 常写「11月30日截止」不带年份——默认今年。"""
        self.assertEqual(daily.find_deadline("简历投递截止 11月30日", self.DAY)[0], "2026-11-30")

    def test_year_omitted_rolls_to_next_year_if_past(self):
        """写「1月5日」而今天已经过了 1 月 → 应该是明年，不是「已过期」的今年。"""
        got = daily.find_deadline("截止 1月5日", self.DAY)
        self.assertEqual(got, ("2027-01-05", "JD 原文"))

    def test_open_ended_means_no_date(self):
        """「招满为止」没给具体日期：返回 None + 一句来源说明，绝不猜一个。"""
        due, note = daily.find_deadline("本岗位招满为止，建议尽早投递。", self.DAY)
        self.assertIsNone(due)
        self.assertIn("招满为止", note)

    def test_real_date_wins_over_open_ended_in_the_same_sentence(self):
        """真 bug：JD 常写「截止日期：2027-02-28（招满为止不做另行通知）」。

        里面既有具体日期又有「招满为止」。先判「招满为止」会把真实日期吃掉，
        于是清单上少一条截止日——这是**静默丢信息**，比猜错更隐蔽。
        """
        due, note = daily.find_deadline(
            "简历投递截止日期：2027-02-28（招满为止不做另行通知）。", self.DAY)
        self.assertEqual(due, "2027-02-28")
        self.assertEqual(note, "JD 原文")

    def test_random_date_in_body_is_not_a_deadline(self):
        """发布日期 / 公司成立日期不能当成投递截止日。"""
        for text in ("发布时间：2026-10-01", "公司成立于 2015 年，2025 年营收过亿。"):
            self.assertIsNone(daily.find_deadline(text, self.DAY)[0], text)

    def test_no_cue_no_date(self):
        self.assertEqual(daily.find_deadline("要求熟悉 Python。", self.DAY), (None, ""))

    def test_plan_sorts_due_before_score(self):
        """有截止日的先到期排前；没截止日的排后面、按分降序。"""
        jds = [
            daily.Job(title="高分无期限", text="要求：熟悉 Python、有后端项目经验。"),
            daily.Job(title="急的低分", text="要求：会用 SQL 查数据。截止时间：2026-10-28"),
            daily.Job(title="晚的", text="要求：懂大模型原理。截止日期 2026-12-20"),
        ]
        plan = daily.build_plan(jds, "我用 Python 写过后端服务，也懂大模型原理和 SQL。",
                                today=self.DAY)
        self.assertEqual([i.title for i in plan.items][:2], ["急的低分", "晚的"])
        self.assertEqual(plan.items[-1].title, "高分无期限")

    def test_min_score_filters(self):
        jds = [daily.Job(title="够不着", text="要求：精通 Kubernetes、熟悉服务网格与内核调优。")]
        plan = daily.build_plan(jds, "我会写 Python。", today=self.DAY, min_score=60.0)
        self.assertEqual(plan.items, [])

    def test_default_due_only_when_jd_has_none(self):
        """--due 是兜底：JD 自己写了日期时不能被覆盖。"""
        jds = [daily.Job(title="自带截止", text="要求：会 Python。截止 2026-11-11")]
        plan = daily.build_plan(jds, "我用 Python 写过服务。", today=self.DAY,
                                default_due="2026-10-30")
        self.assertEqual(plan.items[0].due, "2026-11-11")
        self.assertEqual(plan.items[0].due_source, "JD 原文")

    def test_best_fix_has_positive_gain(self):
        jds = [daily.Job(title="AI 岗", text="要求：熟悉 Python、了解 RAG 与提示词工程。")]
        plan = daily.build_plan(jds, "我用 Python 做过项目。", today=self.DAY)
        self.assertIsNotNone(plan.items[0].best_fix)
        name, base, new = plan.items[0].best_fix
        self.assertGreater(new, base)

    def test_markdown_is_a_real_checklist(self):
        jds = [daily.Job(title="X 岗", text="要求：会 Python。截止 2026-11-01")]
        plan = daily.build_plan(jds, "我用 Python 写过服务。", today=self.DAY)
        md = daily.to_markdown(plan)
        self.assertIn("- [ ] ", md)
        self.assertIn("2026-11-01", md)
        self.assertIn("JD 原文", md)  # 日期来源必须出现在清单里

    def test_csv_row_count(self):
        jds = [daily.Job(title="X 岗", text="要求：会 Python。"),
               daily.Job(title="Y 岗", text="要求：会 SQL。")]
        plan = daily.build_plan(jds, "我用 Python 和 SQL 做过项目。", today=self.DAY)
        rows = [r for r in daily.to_csv(plan).splitlines() if r.strip()]
        self.assertEqual(len(rows), len(plan.items) + 1)  # 含表头

    def test_ics_is_well_formed(self):
        jds = [daily.Job(title="X 岗", text="要求：会 Python。截止 2026-11-01")]
        plan = daily.build_plan(jds, "我用 Python 写过服务。", today=self.DAY)
        ics = daily.to_ics(plan)
        self.assertTrue(ics.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertTrue(ics.endswith("END:VCALENDAR\r\n"))
        self.assertEqual(ics.count("BEGIN:VTODO"), ics.count("END:VTODO") == 1 or 1)
        self.assertIn("DUE;VALUE=DATE:20261101", ics)
        self.assertIn("STATUS:NEEDS-ACTION", ics)

    def test_ics_escapes_reserved_characters(self):
        """SUMMARY / DESCRIPTION 里的逗号、分号、换行必须转义，否则整个文件解析失败。"""
        plan = daily.DailyPlan(day="2026-10-26", items=[
            daily.DailyItem(title="产品, 高级; 岗", score=50.0, due="2026-11-01",
                            due_source="JD 原文", best_fix=("缺, 项", 50.0, 60.0)),
        ])
        ics = daily.to_ics(plan)
        self.assertIn("\\,", ics)
        self.assertIn("\\;", ics)
        self.assertNotIn("SUMMARY:产品, 高级", ics)

    def test_empty_profile_is_not_scored(self):
        plan = daily.build_plan([daily.Job(title="X", text="要求：会 Python。")], " ",
                                today=self.DAY)
        self.assertEqual(plan.items, [])
        self.assertTrue(plan.notes)


class TestRenderReport(unittest.TestCase):
    """`career-loop match` 产出的 report.md 是项目主要交付物（README 头图就是它），
    但这一层覆盖率只有 9% —— 意思是报告长什么样，从来没有任何断言。

    补测试当晚就抓到一个真 bug：quote / evidence 里的管道符有转义，
    **label 没有**。而 label 恰恰最危险——自定义能力项的标签是从 JD 原文
    抽出来的短语，像 "Java|Python|Go" 这种技能罗列很常见，一个 `|` 就让
    能力矩阵和 4 周路线两张表同时错位。所以核心断言是**表格列数一致**。
    """

    @staticmethod
    def _assess(specs, mode: str = "rule", title: str = "测试岗位") -> matching.Assessment:
        """specs: [(key, label, weight, status, quote, evidence)]"""
        from career_loop.matching.schema import MatchResult, Requirement
        reqs, matches = [], {}
        for key, label, weight, status, quote, evidence in specs:
            reqs.append(Requirement(key=key, label=label, weight=weight,
                                    kind="must", quote=quote))
            matches[key] = MatchResult(key=key, status=status, evidence=evidence)
        return matching.Assessment(requirements=reqs, matches=matches,
                                   jd_title=title, mode=mode)

    NASTY = "技能|罗列\n换行也在里面"
    BASE = [
        ("python", "Python", 3, "full", "熟悉 Python", "做过 X 项目"),
        ("rag", "RAG", 2, "partial", "有 RAG 经验优先", "课程作业"),
        ("agent", "Agent", 1, "missing", "用过 Agent 加分", ""),
    ]

    def _table_column_counts(self, md: str) -> dict[str, set[int]]:
        """按表格分组，返回每个表出现过的列数集合——一个正常表格只能有一种。"""
        groups: dict[str, set[int]] = {}
        current: list[str] = []
        for line in md.splitlines():
            if line.startswith("|"):
                current.append(line)
            elif current:
                groups.setdefault(str(len(current)), set()).add(
                    current[0].count("|"))
                groups[str(len(current))].update(l.count("|") for l in current)
                current = []
        if current:
            groups.setdefault(str(len(current)), set()).update(
                l.count("|") for l in current)
        return groups

    def test_tables_keep_columns_aligned_with_hostile_text(self):
        """把 `|` 和换行塞进 label / quote / evidence，表格不能多出或少掉一列。"""
        specs = [
            (k, lbl if i == 0 else lbl, w, st,
             self.NASTY if i == 0 else q, self.NASTY if i == 0 else ev)
            for i, (k, lbl, w, st, q, ev) in enumerate(self.BASE)
        ]
        md = render_fn(self._assess(specs))
        for rows, counts in self._table_column_counts(md).items():
            self.assertEqual(len(counts), 1,
                             f"表格（{rows} 行）列数不一致：{sorted(counts)}\n{md}")

    def test_hostile_text_is_flattened_everywhere(self):
        """管道符只害表格，**换行还会害标题和列表项**——两种位置都要压平。

        缺口标题、JD 依据、简历句都不是表格，但 `- **JD 依据**：a\\nb` 的
        后半句会被甩出列表。所以这里断言的是原始字符串**整个报告里都不出现**。
        """
        specs = [("python", self.NASTY, 3, "missing", self.NASTY, self.NASTY)]
        md = render_fn(self._assess(specs))
        # 1) 表格行里不能有裸管道符（会多出一列）
        self.assertEqual([l for l in md.splitlines()
                          if l.startswith("| ") and "技能|罗列" in l], [])
        self.assertIn("技能／罗列", md)
        # 2) 原始字符串（含换行）整个文档里都不该出现
        self.assertNotIn("技能|罗列\n换行也在里面", md)
        self.assertNotIn("\n换行也在里面", md)
        # 3) 标题/列表项已经压成一行
        self.assertIn("### 1. 技能|罗列 换行也在里面（权重 3", md)
        for line in md.splitlines():
            if line.startswith("- "):
                self.assertNotIn("\n", line)

    def test_verdict_has_four_bands(self):
        """4 档结论的边界必须逐档可断言——这是报告里唯一的一句判断。"""
        cases = [
            (100.0, "强匹配"), (75.0, "强匹配"),
            (74.9, "基本匹配"), (60.0, "基本匹配"),
            (59.9, "明显缺口"), (40.0, "明显缺口"),
            (39.9, "当前不是这个岗位的主场"), (0.0, "当前不是这个岗位的主场"),
        ]
        for value, expect in cases:
            self.assertTrue(expect in _verdict(value), f"{value} 分应判为「{expect}」")

    def test_hard_gap_count_is_called_out(self):
        """权重 3 的缺口是 '核心硬要求'，结论句里必须单独点出来。"""
        md = render_fn(self._assess([
            ("python", "Python", 3, "missing", "必须会 Python", ""),
        ]))
        self.assertIn("1 项是权重 3 的核心硬要求", md)
        no_hard = render_fn(self._assess([
            ("agent", "Agent", 2, "missing", "会用 Agent 加分", ""),
        ]))
        self.assertNotIn("核心硬要求", no_hard)

    def test_status_counts_match_the_data(self):
        md = render_fn(self._assess(self.BASE))
        self.assertIn("1 项已覆盖、1 项部分覆盖、1 项缺失", md)

    def test_no_gap_branch_has_its_own_advice(self):
        """全命中时不能落进 `if gap_list` 之外还输出空章节。"""
        md = render_fn(self._assess([
            ("python", "Python", 3, "full", "熟悉 Python", "做过"),
            ("rag", "RAG", 2, "full", "有 RAG 经验", "做过"),
        ]))
        self.assertIn("没有识别到缺口", md)
        self.assertIn("建议配置 API Key 用语义匹配复核", md)

    def test_roadmap_caps_at_four_weeks(self):
        """5 个以上缺口时也只给 4 周计划，第 5 个不能变成 '第 5 周'。"""
        keys = ["python", "rag", "agent", "prompt_eng", "eval", "data_analysis"]
        specs = [(k, f"能力{k}", 3, "missing", f"要求 {k}", "") for k in keys]
        md = render_fn(self._assess(specs))
        self.assertIn("第 4 周", md)
        self.assertNotIn("第 5 周", md)

    def test_report_carries_mode_and_resume_sentences(self):
        for mode, expect in (("rule", "规则基线"), ("llm", "LLM 语义匹配")):
            md = render_fn(self._assess(self.BASE, mode=mode))
            self.assertIn(expect, md)
            self.assertIn("# 测试岗位 · 匹配报告", md)
            self.assertIn("可直接写进简历的句子", md)


class TestDockerfileStatic(unittest.TestCase):
    """README 说「Docker 见 Dockerfile」，但这个文件曾经从未被自动化验证过。

    本机没有 docker，CI 里加一个 build job；这里跑的是**离线静态校验**——
    它不需要 docker，因此挂在普通单测里，改 Dockerfile 当场就能红。
    静态校验放不住镜像能不能拉的下来，那部分交给 CI 那个 docker job。
    """

    def test_dockerfile_passes_static_check(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
        try:
            import check_dockerfile as cd
        finally:
            sys.path.pop(0)
        problems = cd.check()
        self.assertEqual(problems, [], "Dockerfile 静态校验不过：\n  " + "\n  ".join(problems))

    def test_runtime_assets_are_not_empty(self):
        """推断器本身要能找到东西——找到 0 个说明路径规则失效了，检查会空转。"""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
        try:
            import check_dockerfile as cd
        finally:
            sys.path.pop(0)
        assets = cd.pytest_assets()
        self.assertTrue(any(a.startswith("data/") for a in assets),
                        f"没推断出 data/ 下的运行时资产：{assets}")


class TestOccupationCoverage(unittest.TestCase):
    """README 宣称「可对齐到职业分类大典」，就必须有命令能把它跑出来。

    这组测试的背景是一次体检发现：taxonomy_cn.py 全仓库零引用，是死代码，
    而 README 两处指向它。更危险的是 coverage_matrix() 会给出 39/39 = 100%，
    这个数字单独拿出来读，会被理解成"覆盖了大典全部中类"——实际只收录了 39 个，
    大典有 79 个。所以这里锁的不是数字本身，而是**两个口径必须同时出现**。
    """

    def test_summary_reports_both_denominators(self):
        s = taxonomy_cn.coverage_summary()
        self.assertEqual(s["listed_mapped"], s["listed_total"])   # 收录的都有词表
        self.assertLess(s["breadth"], 1.0)                        # 但远没覆盖全大典
        self.assertEqual(s["dictionary_total"], taxonomy_cn.MIDS_IN_DICTIONARY_2022)

    def test_every_listed_mid_has_a_pack(self):
        """「完整度 100%」必须是算出来的，不是写出来的。"""
        for row in taxonomy_cn.coverage_matrix():
            self.assertEqual(row["gaps"], [], f"大类 {row['code']} 有中类没建词表")

    def test_rendered_table_carries_the_honest_boundary(self):
        """改文案可以，但把「79 / 49% / 启发式」任何一项改没了都会被抓住。"""
        out = taxonomy_cn.render_coverage()
        self.assertIn("49%", out)
        self.assertIn("79", out)
        self.assertIn("启发式", out)
        # 单独一个 100% 而没有广度说明 = 误导，所以两者必须同屏
        self.assertTrue("100%" in out and "49%" in out)

    def test_numbers_match_readme_claim(self):
        """README 写的是「收录 39 个中类 / 大典 79 个 / 49%」，别悄悄漂移。"""
        s = taxonomy_cn.coverage_summary()
        self.assertEqual(s["listed_total"], 39)
        self.assertEqual(round(s["breadth"] * 100), 49)

    def test_cli_exposes_it(self):
        """不是死代码的第一道保险：命令表里有它。"""
        args = build_parser().parse_args(["occupations"])
        self.assertTrue(hasattr(args, "out"))


class TestStatusEnumParity(unittest.TestCase):
    """CLI 能记的状态 与 reflow 的口径枚举 必须是同一套。

    这条锁的由来：CLI `log` 曾经只认 5 个状态，而 reflow 定义了 7 个。
    后果不是"少两个选项"这么轻——terminal 口径专门把「进面试但淘汰」和
    「简历关拒绝」分开（这是它和 early 口径的唯一实质差别），而 CLI 用户
    记不了前者，只能记成 rejected，terminal 口径在纯 CLI 闭环下就是失真的。
    """

    def test_cli_accepts_every_reflow_status(self):
        reflow_all = {
            reflow.STATUS_OFFER, reflow.STATUS_INTERVIEW,
            reflow.STATUS_INTERVIEW_ELIMINATED, reflow.STATUS_REPLIED,
            reflow.STATUS_APPLIED, reflow.STATUS_REJECTED, reflow.STATUS_SILENT,
        }
        self.assertEqual(set(store.ALL_STATUSES), reflow_all)

    def test_positive_set_matches_early_mode(self):
        """DB 侧判正反馈必须与 reflow 的 early 口径同一套，否则校准数字对不上。"""
        self.assertEqual(set(store.POSITIVE_STATUSES), set(reflow.EARLY_POSITIVE))

    def test_silent_is_not_a_positive_outcome(self):
        """沉默是"结果未知"，不是负面的 HR 动作——早期版本踩过这个坑。"""
        self.assertNotIn("silent", store.POSITIVE_STATUSES)
        self.assertNotIn(reflow.STATUS_SILENT, reflow.EARLY_POSITIVE)
        self.assertNotIn(reflow.STATUS_SILENT, reflow.TERMINAL_POSITIVE)

    def test_interview_eliminated_is_not_confused_with_rejected(self):
        """两者都不是正反馈，但在 terminal 口径下是不同格子，不能合并。"""
        order = reflow.FUNNEL_ORDER["terminal"]
        self.assertIn(reflow.STATUS_INTERVIEW_ELIMINATED, order)
        self.assertIn(reflow.STATUS_REJECTED, order)
        self.assertNotEqual(order.index(reflow.STATUS_INTERVIEW_ELIMINATED),
                            order.index(reflow.STATUS_REJECTED))


class TestCorrelationCI(unittest.TestCase):
    """置信区间：把「r 是多少」升级成「这个 r 有没有把 0 排除掉」。

    只报一个 r 是没法证伪的——n=12 时能轻松跑出 0.29，也可能下一次是 -0.2。
    区间跨不跨 0 才是能不能拿它做投递优先级的判据。
    """

    _xs = [52, 61, 70, 74, 80, 88, 91, 44, 57, 66]
    _ps = [False, False, True, False, True, True, True, False, True, False]

    def test_deterministic_across_calls(self):
        """固定种子 → 同输入必同输出。否则同一份数据在报告里和看板上会不一样。"""
        a = calibrate.pearson_ci(self._xs, self._ps)
        b = calibrate.pearson_ci(self._xs, self._ps)
        self.assertEqual((a.r, a.lo, a.hi, a.valid), (b.r, b.lo, b.hi, b.valid))

    def test_too_few_samples_refuses_to_give_interval(self):
        """样本太少时宁可不给数，也不给假精度。"""
        ci = calibrate.pearson_ci([60, 70, 80], [False, True, True])
        self.assertFalse(ci.available)
        self.assertIn("不足", ci.verdict())

    def test_strong_signal_excludes_zero(self):
        xs = [20, 30, 40, 50, 60, 70, 80, 90, 95, 99]
        ps = [False, False, False, False, True, True, True, True, True, True]
        ci = calibrate.pearson_ci(xs, ps)
        self.assertTrue(ci.available)
        self.assertFalse(ci.crosses_zero)
        self.assertGreater(ci.lo, 0)

    def test_no_signal_spans_zero(self):
        """正负交替 = 没有关系，区间必须跨 0（不能拍脑袋说"有点用处"）。"""
        xs = [50, 51, 52, 53, 54, 55, 56, 57, 58, 59]
        ps = [True, False] * 5
        ci = calibrate.pearson_ci(xs, ps)
        self.assertTrue(ci.crosses_zero)

    def test_point_estimate_inside_interval(self):
        ci = calibrate.pearson_ci(self._xs, self._ps)
        self.assertTrue(ci.lo <= ci.r <= ci.hi)

    def test_text_carries_the_numbers(self):
        """图上的标题字符串必须自带样本量——截图发出去不会丢口径。"""
        ci = calibrate.pearson_ci(self._xs, self._ps)
        self.assertIn("95% CI", ci.text)
        self.assertIn("n=10", ci.text)


class TestDashboardData(unittest.TestCase):
    """看板数据层。

    这一层的 bug 有个共同特点：**图照样画得出来**。漏斗顺序错了、
    口径判错了、层级降级成一句 caption 了，屏幕上都是一张正常的图。
    所以只能靠断言把它钉住。
    """

    @classmethod
    def setUpClass(cls):
        cls.demo = dashdata.build_board("demo", mode="early")

    def test_demo_data_is_explicitly_flagged(self):
        """演示数据是编的，必须写在数据里，看板躲不掉这条标注。"""
        self.assertTrue(self.demo.is_demo)
        self.assertTrue(any("编造" in w for w in self.demo.warnings))

    def test_funnel_order_follows_mode_contract(self):
        keys = [f.key for f in self.demo.funnel]
        want = [k for k in reflow.FUNNEL_ORDER["early"] if k in keys]
        self.assertEqual(keys, want)

    def test_funnel_counts_sum_to_total(self):
        self.assertEqual(sum(f.n for f in self.demo.funnel), self.demo.total)

    def test_interview_counts_only_in_early_mode(self):
        """口径差异最大的一条：面试邀约在 early 是正反馈，在 terminal 不是。"""
        def build(mode):
            rows = [dashdata.BoardRow(id="1", title="t", company="c", score=70,
                                      status=reflow.STATUS_INTERVIEW, positive=False)]
            return dashdata._finalize(rows, "db", mode)
        self.assertTrue(build("early").rows[0].positive)
        self.assertFalse(build("terminal").rows[0].positive)

    def test_only_scored_rows_reach_the_scatter(self):
        self.assertEqual(len(self.demo.scatter), len(self.demo.scored_rows))

    def test_jitter_is_deterministic(self):
        again = dashdata.build_board("demo", mode="early")
        self.assertEqual([p.jitter for p in self.demo.scatter],
                         [p.jitter for p in again.scatter])

    def test_ci_is_wider_when_samples_are_few(self):
        """同一份演示数据 n=12，区间必须跨 0——用来防止"演示数据看起来很有效"。"""
        self.assertTrue(self.demo.ci.crosses_zero)

    def test_unknown_mode_and_source_rejected(self):
        with self.assertRaises(ValueError):
            dashdata.build_board("demo", mode="maybe")
        with self.assertRaises(ValueError):
            dashdata.build_board("nowhere")

    def test_missing_profile_warns_instead_of_crashing(self):
        board = dashdata.build_board(
            "records", records_path="examples/reflow_demo_records.csv", profile_path=""
        )
        self.assertEqual(board.rows, [])
        self.assertTrue(board.warnings)

    def test_unusable_db_degrades_to_warning(self):
        """库不存在/没建表时不能让看板白屏，要变成一条能读的提示。"""
        with tempfile.TemporaryDirectory() as td:
            board = dashdata.build_board("db", db=str(Path(td) / "nope.db"))
        self.assertEqual(board.rows, [])
        self.assertTrue(board.warnings)

    def test_svg_escapes_injected_markup(self):
        """JD 和岗位名是外部输入：转义漏了，导出的图就是一个 XSS 载体。"""
        row = dashdata.BoardRow(id="<script>x</script>", title="<b>粗体</b>",
                                company="A&B", score=50,
                                status=reflow.STATUS_APPLIED, positive=False)
        board = dashdata.BoardData(
            source="db", mode="early", rows=[row],
            funnel=[dashdata.FunnelStage("applied", "<img src=x>", 1, 1)],
            # 点的悬浮提示走 label：把带注入片段的岗位名喂进去
            scatter=[dashdata.ScatterPoint(label=row.title, score=50,
                                           positive=False, jitter=0.0)],
            gaps=[dashdata.GapItem(key="k", label="<script>y</script>",
                                   gained=1, unlocked=[])],
        )
        funnel_svg = dashdata.render_funnel_svg(board)
        scatter_svg = dashdata.render_scatter_svg(board)
        gaps_svg = dashdata.render_gaps_svg(board)
        for svg in (funnel_svg, scatter_svg, gaps_svg):
            self.assertNotIn("<script>", svg)
            self.assertNotIn("<img", svg)
        # 转义后的形态必须原样出现在对应那张图里
        self.assertIn("&lt;img src=x&gt;", funnel_svg)
        self.assertIn("&lt;b&gt;粗体&lt;/b&gt;", scatter_svg)
        self.assertIn("&lt;script&gt;", gaps_svg)

    def test_empty_board_renders_a_note_not_a_broken_svg(self):
        board = dashdata.BoardData()
        for svg in (dashdata.render_funnel_svg(board),
                    dashdata.render_scatter_svg(board),
                    dashdata.render_gaps_svg(board)):
            self.assertTrue(svg.strip())
            self.assertNotIn("<circle", svg)


if __name__ == "__main__":
    unittest.main()
