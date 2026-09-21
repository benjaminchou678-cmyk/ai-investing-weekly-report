from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WeChatDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.planner = load("build_wechat_search_plan")
        cls.verifier = load("verify_wechat_candidates")
        cls.comparer = load("compare_wechat_ground_truth")
        cls.registry = {"schema_version": "3.0", "sources": [
            {
                "source_id": "wx-a", "name": "量子位", "aliases": ["QbitAI"],
                "wechat_id": "QbitAI2014", "wechat_biz_ids": ["BIZ_A"],
                "channel": "wechat_official_account", "priority": "C1",
            },
            {
                "source_id": "wx-c3", "name": "事件源", "aliases": [],
                "wechat_id": "", "wechat_biz_ids": [],
                "channel": "wechat_official_account", "priority": "C3",
            },
        ]}

    def test_plan_uses_identity_variants_and_keeps_dates_out_of_queries(self) -> None:
        plan = self.planner.build_plan(self.registry, "2026-09-14", "2026-09-20", {"C1", "C2"})
        self.assertEqual(plan["source_count"], 1)
        queries = [row["query"] for row in plan["sources"][0]["queries"]]
        self.assertTrue(any("量子位" in value for value in queries))
        self.assertTrue(any("QbitAI" in value for value in queries))
        self.assertTrue(any("QbitAI2014" in value for value in queries))
        self.assertTrue(all("2026-09" not in value for value in queries))
        self.assertEqual(plan["query_policy"]["empty_result_means"], "discovery_miss_not_no_update")

    def test_c3_requires_explicit_event_trigger(self) -> None:
        normal = self.planner.build_plan(self.registry, "2026-09-14", "2026-09-20", {"C3"})
        explicit = self.planner.build_plan(
            self.registry, "2026-09-14", "2026-09-20", set(), {"wx-c3"}
        )
        self.assertEqual(normal["source_count"], 0)
        self.assertEqual(explicit["sources"][0]["source_id"], "wx-c3")

    def test_biz_identity_and_half_open_window(self) -> None:
        result = self.verifier.verify(self.registry, {"items": [
            {"source_id": "wx-a", "title": "in", "url": "https://mp.weixin.qq.com/s/x?__biz=BIZ_A",
             "published_at": "2026-09-20T23:59:59+08:00"},
            {"source_id": "wx-a", "title": "out", "url": "https://mp.weixin.qq.com/s/y?__biz=BIZ_A",
             "published_at": "2026-09-21T00:00:00+08:00"},
        ]}, "2026-09-14", "2026-09-21")
        self.assertEqual([item["title"] for item in result["verified_in_window"]], ["in"])
        self.assertEqual([item["title"] for item in result["out_of_window"]], ["out"])

    def test_wrong_identity_and_unknown_date_go_to_review(self) -> None:
        result = self.verifier.verify(self.registry, {"items": [
            {"source_id": "wx-a", "title": "wrong", "biz_id": "BIZ_X", "published_at": "2026-09-18"},
            {"source_id": "wx-a", "title": "unknown date", "account_name": "QbitAI", "published_at": ""},
        ]}, "2026-09-14", "2026-09-21")
        self.assertEqual(result["counts"]["identity_review_queue"], 1)
        self.assertEqual(result["counts"]["date_unknown_review_queue"], 1)
        self.assertEqual(result["semantics"]["empty_input_means"], "no_candidates_discovered_not_no_update")

    def test_ground_truth_only_calls_complete_benchmark_recall(self) -> None:
        truth = {"complete_for_window": False, "items": [
            {"source_id": "wx-a", "title": "A", "url": "https://mp.weixin.qq.com/s/a"},
        ]}
        discovered = {"verified_in_window": [
            {"source_id": "wx-a", "title": "A", "url": "https://mp.weixin.qq.com/s/a"},
        ]}
        proxy = self.comparer.compare(truth, discovered)
        self.assertEqual(proxy["metric_name"], "discovery_coverage")
        truth["complete_for_window"] = True
        self.assertEqual(self.comparer.compare(truth, discovered)["metric_name"], "recall")


if __name__ == "__main__":
    unittest.main()
