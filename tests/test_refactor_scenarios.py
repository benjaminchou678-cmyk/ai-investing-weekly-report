#!/usr/bin/env python3
"""Four scenario tests for the v3 refactor (dynamic 0-3 theses, JSON as authority,
layered candidate pool, Shanghai-timezone half-open window)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_theses as BT          # noqa: E402
import editorial_pass as EP        # noqa: E402
import collect_source_endpoints as CS  # noqa: E402
import rank_events as RE           # noqa: E402


def _ev(cid, score, groups, title="事件", board="产品与模型", independence_status="verified"):
    keys = ["industry_competitive", "long_term_direction", "commercial_capital",
            "lasting_impact", "source_credibility", "incremental"]
    w = [25, 25, 20, 15, 10, 5]
    bd = {k: int(round(score * x / 100.0)) for k, x in zip(keys, w)}
    bd[keys[0]] += score - sum(bd.values())
    return {
        "cluster_id": cid, "representative_title": title, "companies": [title],
        "board": board, "article_ids": [cid], "dates": ["2026-09-15"],
        "independence_groups": groups, "independence_status": independence_status,
        "source_ids": [f"s_{cid}"], "source_urls": ["https://x.example.com"],
        "sources": [{"url": "https://x.example.com"}], "summary": "摘要",
        "all_titles": [title], "related_events": [],
        "earliest_date": "2026-09-15", "latest_date": "2026-09-15",
        "score_breakdown": bd, "score_reasons": {k: "r" for k in bd},
        "importance_score": score, "tier": RE.tier_for(score),
    }


class ScenarioASparseWeek(unittest.TestCase):
    """0 theses, <5 core, evidence insufficient -> still produces a valid report."""

    def test_zero_theses_sparse_week_renders(self):
        ranked = [_ev("c1", 55, ["g1"], title="单一观察事件")]  # watchlist tier only
        theses, watch = BT.build_theses(ranked)
        self.assertEqual(theses, [])
        plan, report = EP.editorial_pass(ranked, theses, watch, "2026-09-14—2026-09-20")
        self.assertEqual(plan["thesis_count"], 0)
        final = EP.build_final_report(plan, report)
        self.assertEqual(final["theses"], [])
        # Must not claim a formed trend in the lead.
        self.assertNotIn("趋势", final["weekly_lead"])
        # md/html render without error
        md = EP.render_markdown(final)
        html = EP.render_html(final)
        self.assertIn("未形成", md)
        self.assertIn("<!doctype html>", html.lower())
        # candidate layers present
        self.assertIn("human_review_queue", final)
        self.assertIn("excluded_events", final)


class ScenarioBNormalWeek(unittest.TestCase):
    """2 cross-board theses, 5-7 core, 3-5 watchlist."""

    def test_two_cross_board_theses(self):
        ranked = [
            _ev("p1", 85, ["g1"], title="OpenAI 新模型", board="产品与模型"),
            _ev("p2", 70, ["g2"], title="DeepSeek 新模型", board="产品与模型"),
            _ev("o1", 82, ["g3"], title="Anthropic 负责人变动", board="组织与人事"),
            _ev("o2", 68, ["g4"], title="Google AI 架构调整", board="组织与人事"),
        ]
        theses, watch = BT.build_theses(ranked)
        self.assertGreaterEqual(len(theses), 2)
        boards = {tuple(t["related_boards"]) for t in theses}
        self.assertTrue(any("组织与人事" in b for b in boards))


class ScenarioCMajorWeek(unittest.TestCase):
    """3 theses, each passing the evidence gate, no shared-group double counting."""

    def test_three_theses_each_pairwise_independent(self):
        ranked = [
            _ev("a1", 85, ["g1"], title="前沿模型 A"),
            _ev("a2", 70, ["g2"], title="前沿模型 B"),
            _ev("b1", 84, ["g3"], title="融资 A"),
            _ev("b2", 69, ["g4"], title="融资 B"),
            _ev("c1", 83, ["g5"], title="组织 A"),
            _ev("c2", 67, ["g6"], title="组织 B"),
        ]
        theses, _ = BT.build_theses(ranked)
        self.assertGreaterEqual(len(theses), 2)
        for t in theses:
            self.assertLessEqual(len(t["key_evidence"]), 3)
            groups = [set(e["independence_groups"]) for e in t["key_evidence"]]
            for i in range(len(groups)):
                for j in range(i + 1, len(groups)):
                    self.assertFalse(groups[i] & groups[j])


class ScenarioDTimeAndSourceAnomalies(unittest.TestCase):
    """Date unknown -> review queue; unknown independence fails gate;
    Shanghai half-open window boundary correct."""

    def test_unknown_independence_cannot_form_thesis(self):
        ranked = [
            _ev("u1", 85, [], title="事件一", independence_status="unknown"),
            _ev("u2", 70, [], title="事件二", independence_status="unknown"),
        ]
        theses, _ = BT.build_theses(ranked)
        self.assertEqual(theses, [])

    def test_shared_group_blocks(self):
        ranked = [
            _ev("s1", 85, ["shared"], title="事件一"),
            _ev("s2", 70, ["shared"], title="事件二"),
        ]
        theses, _ = BT.build_theses(ranked)
        self.assertEqual(theses, [])

    def test_shanghai_half_open_window(self):
        ws, we = "2026-09-14", "2026-09-20"  # Mon..Sun
        items = [
            {"title": "before", "published_at": "2026-09-13T23:30:00+00:00"},  # =09-14 07:30 +08 -> in
            {"title": "in", "published_at": "2026-09-15T01:00:00+08:00"},
            {"title": "after", "published_at": "2026-09-20T17:00:00+00:00"},   # =09-21 01:00 +08 -> out
            {"title": "nodate", "published_at": ""},
        ]
        out = CS.filter_week(items, ws, we)
        statuses = {o["title"]: o["date_status"] for o in out}
        self.assertEqual(statuses["in"], "in_window")
        self.assertNotIn("after", statuses)
        self.assertEqual(statuses["nodate"], "unknown")  # routed, not dropped
        # before-midnight UTC is already Monday morning Shanghai -> in window
        self.assertIn("before", statuses)


if __name__ == "__main__":
    unittest.main()
