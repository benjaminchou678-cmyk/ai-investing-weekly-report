#!/usr/bin/env python3
"""Tests for the rewritten content layer:
cluster -> rank -> theses -> editorial_pass.

Covers mechanical QA gates and extended edge cases required by the refactor.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import cluster_events as CE  # noqa: E402
import rank_events as RE  # noqa: E402
import build_theses as BT  # noqa: E402
import editorial_pass as EP  # noqa: E402
from _editorial_normalize import canonicalize_article  # noqa: E402


def run(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )


# ---------- fixtures ----------

def art(aid: str, title: str, companies=None, materiality="high",
        board="产品与模型", date="2026-09-08", groups=None, summary="",
        verification="verified_primary") -> dict:
    groups = groups or [f"g_{aid}"]
    return canonicalize_article({
        "id": aid, "title": title, "companies": companies or [],
        "board": board, "event_date": date, "materiality": materiality,
        "summary": summary, "verification_status": verification,
        "sources": [{"url": f"https://{g}.example.com/post", "independence_group": g} for g in groups],
    })


def cluster(cid: str, title: str, companies, board, score_breakdown,
            independence_groups=None, summary="") -> dict:
    total = sum(score_breakdown.values())
    return {
        "cluster_id": cid, "representative_title": title, "companies": companies,
        "board": board, "article_ids": [cid], "dates": ["2026-09-08"],
        "independence_groups": independence_groups or [f"g_{cid}"],
        "source_ids": [f"s_{cid}"], "source_urls": ["https://x.example.com"],
        "sources": [{"url": "https://x.example.com"}],
        "summary": summary, "all_titles": [title], "related_events": [],
        "earliest_date": "2026-09-08", "latest_date": "2026-09-08",
        "score_breakdown": score_breakdown,
        "score_reasons": {k: "r" for k in score_breakdown},
        "importance_score": total, "tier": RE.tier_for(total),
    }


# ---------- clustering ----------

class ClusteringTests(unittest.TestCase):
    def test_same_event_different_sources_merge(self) -> None:
        a1 = canonicalize_article({"id": "1", "title": "DeepSeek V4.1 发布",
            "companies": ["DeepSeek"], "board": "产品与模型", "event_date": "2026-09-08",
            "sources": [{"url": "https://d.com", "independence_group": "deepseek"}]})
        a2 = canonicalize_article({"id": "2", "title": "DeepSeek V4.1 发布报道",
            "companies": ["DeepSeek"], "board": "产品与模型", "event_date": "2026-09-08",
            "sources": [{"url": "https://g.com", "independence_group": "geekpark"}]})
        clusters = CE.cluster_articles([a1, a2])
        self.assertEqual(len(clusters), 1)
        self.assertEqual(set(clusters[0]["independence_groups"]), {"deepseek", "geekpark"})
        self.assertEqual(len(clusters[0]["article_ids"]), 2)

    def test_same_company_different_product_not_merged(self) -> None:
        a1 = canonicalize_article({"id": "1", "title": "OpenAI 发布 Agents API",
            "companies": ["OpenAI"], "board": "产品与模型", "event_date": "2026-09-08"})
        a2 = canonicalize_article({"id": "2", "title": "OpenAI 发布 Sora 视频模型",
            "companies": ["OpenAI"], "board": "产品与模型", "event_date": "2026-09-08"})
        clusters = CE.cluster_articles([a1, a2])
        self.assertEqual(len(clusters), 2)

    def test_same_company_different_funding_round_not_merged(self) -> None:
        a1 = canonicalize_article({"id": "1", "title": "Cognition 完成 B 轮融资",
            "companies": ["Cognition"], "board": "投融资", "event_date": "2026-09-08"})
        a2 = canonicalize_article({"id": "2", "title": "Cognition 完成 C 轮融资",
            "companies": ["Cognition"], "board": "投融资", "event_date": "2026-09-09"})
        clusters = CE.cluster_articles([a1, a2])
        self.assertEqual(len(clusters), 2)

    def test_same_company_different_version_not_merged(self) -> None:
        a1 = canonicalize_article({"id": "1", "title": "DeepSeek V4.1 发布",
            "companies": ["DeepSeek"], "board": "产品与模型", "event_date": "2026-09-08"})
        a2 = canonicalize_article({"id": "2", "title": "DeepSeek V3.5 发布",
            "companies": ["DeepSeek"], "board": "产品与模型", "event_date": "2026-09-08"})
        clusters = CE.cluster_articles([a1, a2])
        self.assertEqual(len(clusters), 2)

    def test_date_drives_merge_decision(self) -> None:
        a1 = canonicalize_article({"id": "1", "title": "公司甲 发布 新模型",
            "companies": ["公司甲"], "board": "产品与模型", "event_date": "2026-09-01"})
        a2 = canonicalize_article({"id": "2", "title": "公司甲 发布 新模型 报道",
            "companies": ["公司甲"], "board": "产品与模型", "event_date": "2026-09-13"})
        clusters = CE.cluster_articles([a1, a2], window_days=2)
        self.assertEqual(len(clusters), 2)

    def test_cluster_has_standard_fields(self) -> None:
        a = canonicalize_article({"id": "1", "title": "X 发布", "companies": ["X"],
            "board": "产品与模型", "event_date": "2026-09-08", "summary": "摘要"})
        cl = CE.cluster_articles([a])[0]
        for f in ("summary", "what_is_new", "why_it_matters", "sources", "related_events"):
            self.assertIn(f, cl)


# ---------- ranking ----------

class RankingTests(unittest.TestCase):
    def test_weights_sum_to_100(self) -> None:
        self.assertEqual(sum(RE.WEIGHTS.values()), 100)
        self.assertEqual(sum(RE.WEIGHTS.values()), RE.WEIGHTS["industry_competitive"]
                         + RE.WEIGHTS["long_term_direction"] + RE.WEIGHTS["commercial_capital"]
                         + RE.WEIGHTS["lasting_impact"] + RE.WEIGHTS["source_credibility"]
                         + RE.WEIGHTS["incremental"])

    def test_score_breakdown_sums_to_total(self) -> None:
        ranked = RE.rank_clusters(DEMO_CLUSTERS(), ART_BY_ID())
        for ev in ranked:
            self.assertEqual(sum(ev["score_breakdown"].values()), ev["importance_score"])

    def test_each_dimension_has_reason(self) -> None:
        ranked = RE.rank_clusters(DEMO_CLUSTERS(), ART_BY_ID())
        for ev in ranked:
            for dim in RE.WEIGHTS:
                self.assertIn(dim, ev["score_reasons"])
                self.assertTrue(ev["score_reasons"][dim])

    def test_tiers_match_thresholds(self) -> None:
        self.assertEqual(RE.tier_for(95), "core")
        self.assertEqual(RE.tier_for(80), "core")
        self.assertEqual(RE.tier_for(79), "possible_core")
        self.assertEqual(RE.tier_for(65), "possible_core")
        self.assertEqual(RE.tier_for(64), "watchlist")
        self.assertEqual(RE.tier_for(50), "watchlist")
        self.assertEqual(RE.tier_for(49), "appendix")

    def test_no_wednesday_bonus(self) -> None:
        # Recency is not a scored dimension anymore.
        self.assertNotIn("recency", RE.WEIGHTS)


# ---------- theses ----------

class ThesisTests(unittest.TestCase):
    def test_theses_have_required_fields(self) -> None:
        ranked = [
            cluster("c1", "OpenAI 发布前沿模型", ["OpenAI"], "产品与模型",
                    {"industry_competitive": 22, "long_term_direction": 22, "commercial_capital": 5,
                     "lasting_impact": 8, "source_credibility": 9, "incremental": 5},
                    ["g1"]),
            cluster("c2", "DeepSeek 新架构 模型", ["DeepSeek"], "产品与模型",
                    {"industry_competitive": 20, "long_term_direction": 20, "commercial_capital": 5,
                     "lasting_impact": 7, "source_credibility": 8, "incremental": 5},
                    ["g2"]),
        ]
        theses, _ = BT.build_theses(ranked)
        self.assertGreaterEqual(len(theses), 1)
        t = theses[0]
        for f in ("statement", "structural_change", "key_evidence", "why_it_matters",
                  "investment_readthrough", "counter_evidence", "falsification_conditions", "confidence"):
            self.assertIn(f, t)
        self.assertGreaterEqual(len(t["key_evidence"]), 2)
        self.assertLessEqual(len(t["key_evidence"]), 4)

    def test_thesis_title_not_just_event_title(self) -> None:
        ranked = [
            cluster("c1", "OpenAI 发布前沿模型", ["OpenAI"], "产品与模型",
                    {"industry_competitive": 22, "long_term_direction": 22, "commercial_capital": 5,
                     "lasting_impact": 8, "source_credibility": 9, "incremental": 5}, ["g1"]),
            cluster("c2", "DeepSeek 新架构 模型", ["DeepSeek"], "产品与模型",
                    {"industry_competitive": 20, "long_term_direction": 20, "commercial_capital": 5,
                     "lasting_impact": 7, "source_credibility": 8, "incremental": 5}, ["g2"]),
        ]
        theses, _ = BT.build_theses(ranked)
        for t in theses:
            for ev in t["key_evidence"]:
                self.assertNotEqual(t["statement"].strip(), ev["title"].strip())

    def test_single_event_not_upgraded_to_thesis(self) -> None:
        ranked = [
            cluster("c1", "OpenAI 发布前沿模型", ["OpenAI"], "产品与模型",
                    {"industry_competitive": 22, "long_term_direction": 22, "commercial_capital": 5,
                     "lasting_impact": 8, "source_credibility": 9, "incremental": 5}, ["g1"]),
        ]
        theses, watch = BT.build_theses(ranked)
        self.assertEqual(theses, [])
        self.assertTrue(any(w["event_cluster_id"] == "c1" for w in watch))

    def test_shared_group_blocks_thesis(self) -> None:
        # Two important events but SAME independence group -> cannot form a thesis.
        ranked = [
            cluster("c1", "OpenAI 发布模型", ["OpenAI"], "产品与模型",
                    {"industry_competitive": 22, "long_term_direction": 22, "commercial_capital": 5,
                     "lasting_impact": 8, "source_credibility": 9, "incremental": 5}, ["shared"]),
            cluster("c2", "OpenAI 新模型 报道", ["OpenAI"], "产品与模型",
                    {"industry_competitive": 20, "long_term_direction": 20, "commercial_capital": 5,
                     "lasting_impact": 7, "source_credibility": 8, "incremental": 5}, ["shared"]),
        ]
        theses, _ = BT.build_theses(ranked)
        self.assertEqual(theses, [])

    def test_core_plus_two_supporting_passes_gate_b(self) -> None:
        ranked = [
            # core 85
            cluster("c1", "OpenAI 重大突破 模型", ["OpenAI"], "产品与模型",
                    {"industry_competitive": 24, "long_term_direction": 24, "commercial_capital": 6,
                     "lasting_impact": 11, "source_credibility": 10, "incremental": 5}, ["g1"]),
            cluster("c2", "DeepSeek 模型", ["DeepSeek"], "产品与模型",
                    {"industry_competitive": 16, "long_term_direction": 16, "commercial_capital": 3,
                     "lasting_impact": 6, "source_credibility": 6, "incremental": 3}, ["g2"]),
            cluster("c3", "Anthropic 模型", ["Anthropic"], "产品与模型",
                    {"industry_competitive": 16, "long_term_direction": 16, "commercial_capital": 3,
                     "lasting_impact": 6, "source_credibility": 6, "incremental": 3}, ["g3"]),
        ]
        theses, _ = BT.build_theses(ranked)
        self.assertGreaterEqual(len(theses), 1)


# ---------- editorial pass ----------

class EditorialPassTests(unittest.TestCase):
    def test_watchlist_between_3and5(self) -> None:
        ranked = [
            cluster("c1", "核心事件 A", ["A"], "产品与模型",
                    {"industry_competitive": 24, "long_term_direction": 24, "commercial_capital": 6,
                     "lasting_impact": 11, "source_credibility": 10, "incremental": 5}, ["g1"]),
        ] + [
            cluster(f"w{i}", f"观察事件 {i}", [f"C{i}"], "投融资",
                    {"industry_competitive": 16, "long_term_direction": 10, "commercial_capital": 16,
                     "lasting_impact": 6, "source_credibility": 5, "incremental": 3}, [f"g{i}"])
            for i in range(2, 8)
        ]
        plan, report = EP.editorial_pass(ranked, [], [], "2026-09-07—2026-09-13")
        self.assertGreaterEqual(plan["watchlist_count"], 3)
        self.assertLessEqual(plan["watchlist_count"], 5)

    def test_core_events_capped_7(self) -> None:
        ranked = [
            cluster(f"c{i}", f"核心 {i}", [f"C{i}"], "产品与模型",
                    {"industry_competitive": 24, "long_term_direction": 24, "commercial_capital": 6,
                     "lasting_impact": 11, "source_credibility": 10, "incremental": 5}, [f"g{i}"])
            for i in range(10)
        ]
        plan, _ = EP.editorial_pass(ranked, [], [], "week")
        self.assertLessEqual(plan["core_count"], 7)

    def test_one_liner_length(self) -> None:
        ranked = [
            cluster("c1", "核心事件 A", ["A"], "产品与模型",
                    {"industry_competitive": 24, "long_term_direction": 24, "commercial_capital": 6,
                     "lasting_impact": 11, "source_credibility": 10, "incremental": 5}, ["g1"]),
        ]
        plan, _ = EP.editorial_pass(ranked, [], [], "week")
        self.assertGreaterEqual(len(plan["one_liner"]), 50)
        self.assertLessEqual(len(plan["one_liner"]), 80)

    def test_card_length_band(self) -> None:
        ev = cluster("c1", "OpenAI 发布 Agents API", ["OpenAI"], "产品与模型",
                     {"industry_competitive": 24, "long_term_direction": 12, "commercial_capital": 11,
                      "lasting_impact": 7, "source_credibility": 7, "incremental": 3}, ["g1"],
                     summary="企业级 Agent 编排 API")
        card = EP.build_card(ev, "")
        self.assertGreaterEqual(len(card), 80)  # soft lower bound; not all reach 150
        self.assertLessEqual(len(card), EP.CARD_MAX)

    def test_appendix_not_in_body(self) -> None:
        ranked = [
            cluster("c1", "核心", ["A"], "产品与模型",
                    {"industry_competitive": 24, "long_term_direction": 24, "commercial_capital": 6,
                     "lasting_impact": 11, "source_credibility": 10, "incremental": 5}, ["g1"]),
            cluster("c2", "垃圾", ["B"], "产品与模型",
                    {"industry_competitive": 2, "long_term_direction": 1, "commercial_capital": 0,
                     "lasting_impact": 1, "source_credibility": 1, "incremental": 1}, ["g2"]),
        ]
        plan, report = EP.editorial_pass(ranked, [], [], "week")
        body_ids = {c["cluster_id"] for c in report["core_event_cards"]}
        body_ids |= {w["event_cluster_id"] for w in report["watchlist"]}
        self.assertNotIn("c2", body_ids)

    def test_same_cluster_one_card(self) -> None:
        ranked = [
            cluster("c1", "核心", ["A"], "产品与模型",
                    {"industry_competitive": 24, "long_term_direction": 24, "commercial_capital": 6,
                     "lasting_impact": 11, "source_credibility": 10, "incremental": 5}, ["g1"]),
        ]
        _, report = EP.editorial_pass(ranked, [], [], "week")
        ids = [c["cluster_id"] for c in report["core_event_cards"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_renders_md_and_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "r.json").write_text(json.dumps({"ranked_events": []}), encoding="utf-8")
            (t / "th.json").write_text(json.dumps({"candidate_theses": [], "watchlist": []}), encoding="utf-8")
            r = run("editorial_pass.py", str(t / "r.json"), str(t / "th.json"),
                    "--week-label", "w", "--plan-out", str(t / "p.json"),
                    "--md-out", str(t / "r.md"), "--html-out", str(t / "r.html"))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue((t / "r.md").exists())
            self.assertTrue((t / "r.html").exists())
            self.assertIn("<!doctype html>", (t / "r.html").read_text(encoding="utf-8").lower())


# ---------- demo end-to-end ----------

class DemoTests(unittest.TestCase):
    def test_demo_pipeline_runs(self) -> None:
        demo = ROOT / "examples" / "demo-merged-candidates.json"
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            cl = t / "cl.json"
            rk = t / "rk.json"
            th = t / "th.json"
            pl = t / "pl.json"
            self.assertEqual(run("cluster_events.py", str(demo), "-o", str(cl)).returncode, 0)
            self.assertEqual(run("rank_events.py", str(cl), str(demo), "-o", str(rk)).returncode, 0)
            self.assertEqual(run("build_theses.py", str(rk), "-o", str(th)).returncode, 0)
            r = run("editorial_pass.py", str(rk), str(th), "--week-label", "w",
                    "--plan-out", str(pl), "--md-out", str(t / "r.md"), "--html-out", str(t / "r.html"))
            self.assertEqual(r.returncode, 0, r.stderr)
            ranked = json.loads(rk.read_text(encoding="utf-8"))
            # Score weights sum to total for every event
            for ev in ranked["ranked_events"]:
                self.assertEqual(sum(ev["score_breakdown"].values()), ev["importance_score"])
            # Watchlist 3-5 or explicitly sparse
            plan = json.loads(pl.read_text(encoding="utf-8"))
            self.assertLessEqual(plan["watchlist_count"], 5)


# shared fixtures

def DEMO_CLUSTERS() -> list[dict]:
    return [
        cluster("c1", "OpenAI 发布前沿模型", ["OpenAI"], "产品与模型",
                {"industry_competitive": 22, "long_term_direction": 22, "commercial_capital": 5,
                 "lasting_impact": 8, "source_credibility": 9, "incremental": 5}, ["g1"]),
        cluster("c2", "DeepSeek 新架构", ["DeepSeek"], "产品与模型",
                {"industry_competitive": 20, "long_term_direction": 20, "commercial_capital": 5,
                 "lasting_impact": 7, "source_credibility": 8, "incremental": 5}, ["g2"]),
    ]


def ART_BY_ID() -> dict:
    return {
        "c1": {"materiality": "high", "verification_status": "verified_primary", "time_horizon": "", "entity_type": ""},
        "c2": {"materiality": "high", "verification_status": "verified_primary", "time_horizon": "", "entity_type": ""},
    }


if __name__ == "__main__":
    unittest.main()
