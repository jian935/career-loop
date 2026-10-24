"""core 行为契约：抽取、匹配、校准、评测。"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from career_loop import calibrate, matching, store
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


if __name__ == "__main__":
    unittest.main()
