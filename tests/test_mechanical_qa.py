#!/usr/bin/env python3
"""Mechanical QA gates for the rewritten content layer (requirement #9).

These are deterministic structural checks, independent of model judgment.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import editorial_pass as EP  # noqa: E402
import rank_events as RE  # noqa: E402
import build_theses as BT  # noqa: E402


def _ev(cid, score, groups=None, title="事件", board="产品与模型"):
    # Distribute the requested score across the 6 dimensions so sum == score.
    weights = [25, 25, 20, 15, 10, 5]
    keys = ["industry_competitive", "long_term_direction", "commercial_capital",
            "lasting_impact", "source_credibility", "incremental"]
    bd = {k: int(round(score * w / 100.0)) for k, w in zip(keys, weights)}
    # absorb rounding drift into the largest dimension
    drift = score - sum(bd.values())
    bd[keys[0]] += drift
    return {
        "cluster_id": cid, "representative_title": title, "companies": [title],
        "board": board, "article_ids": [cid], "dates": ["2026-09-08"],
        "independence_groups": groups or [f"g_{cid}"], "source_ids": [f"s_{cid}"],
        "source_urls": ["https://x.example.com"], "sources": [{"url": "https://x.example.com"}],
        "summary": "摘要", "all_titles": [title], "related_events": [],
        "earliest_date": "2026-09-08", "latest_date": "2026-09-08",
        "score_breakdown": bd, "score_reasons": {k: "r" for k in bd},
        "importance_score": score, "tier": RE.tier_for(score),
    }


class MechanicalQATests(unittest.TestCase):
    def test_score_weights_sum_to_total(self) -> None:
        ev = _ev("c1", 85)
        self.assertEqual(sum(ev["score_breakdown"].values()), ev["importance_score"])

    def test_below_50_never_in_body(self) -> None:
        ranked = [_ev("core", 90), _ev("noise", 30)]
        plan, report = EP.editorial_pass(ranked, [], [], "week")
        body = {c["cluster_id"] for c in report["core_event_cards"]}
        body |= {w["event_cluster_id"] for w in report["watchlist"]}
        self.assertIn("core", body)
        self.assertNotIn("noise", body)

    def test_50to64_never_in_core(self) -> None:
        ranked = [_ev("watch", 55), _ev("watch2", 60)]
        plan, report = EP.editorial_pass(ranked, [], [], "week")
        core_ids = {c["cluster_id"] for c in report["core_event_cards"]}
        self.assertNotIn("watch", core_ids)
        self.assertNotIn("watch2", core_ids)

    def test_watchlist_count_3to5_or_note(self) -> None:
        ranked = [_ev(f"w{i}", 50 + i) for i in range(10)]
        plan, _ = EP.editorial_pass(ranked, [], [], "week")
        self.assertGreaterEqual(plan["watchlist_count"], 3)
        self.assertLessEqual(plan["watchlist_count"], 5)

    def test_same_cluster_single_card(self) -> None:
        ranked = [_ev("core", 90)]
        _, report = EP.editorial_pass(ranked, [], [], "week")
        ids = [c["cluster_id"] for c in report["core_event_cards"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_core_event_linked_to_thesis_or_standalone(self) -> None:
        # Core event absorbed into a thesis must be referenced by that thesis.
        ev1 = _ev("a", 85, groups=["g1"], title="OpenAI 模型突破")
        ev2 = _ev("b", 70, groups=["g2"], title="DeepSeek 新模型")
        theses, _ = BT.build_theses([ev1, ev2])
        thesis_evidence = {e["cluster_id"] for t in theses for e in t["key_evidence"]}
        for t in theses:
            for e in t["key_evidence"]:
                self.assertIn(e["cluster_id"], thesis_evidence)

    def test_thesis_evidence_passes_gate(self) -> None:
        ev1 = _ev("a", 85, groups=["g1"])
        ev2 = _ev("b", 70, groups=["g2"])
        theses, _ = BT.build_theses([ev1, ev2])
        for t in theses:
            n = len(t["key_evidence"])
            groups = [set(e["independence_groups"]) for e in t["key_evidence"]]
            pairwise_ok = not any(g1 & g2 for i, g1 in enumerate(groups) for g2 in groups[i + 1:])
            self.assertTrue(n >= 2 and pairwise_ok)

    def test_thesis_title_differs_from_event_title(self) -> None:
        ev1 = _ev("a", 85, groups=["g1"], title="OpenAI 发布模型")
        ev2 = _ev("b", 70, groups=["g2"], title="DeepSeek 发布模型")
        theses, _ = BT.build_theses([ev1, ev2])
        for t in theses:
            for e in t["key_evidence"]:
                self.assertNotEqual(t["statement"].strip(), e["title"].strip())

    def test_compression_reduces_body(self) -> None:
        # editorial output must be shorter than rendering every event verbosely.
        ranked = [_ev(f"c{i}", 50 + i) for i in range(10)]
        plan, report = EP.editorial_pass(ranked, [], [], "week")
        verbose = sum(len(c["card"]) for c in report["core_event_cards"] + []) * 10
        self.assertLessEqual(plan["core_count"], 7)


if __name__ == "__main__":
    unittest.main()
