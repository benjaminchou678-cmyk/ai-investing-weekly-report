"""内容层回归：保守聚类、Agent 评级、候选判断与纯渲染。"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from report_fixtures import ROOT, event, final_report, thesis
import cluster_events as CE
import rank_events as RE
import build_theses as BT
import editorial_pass as EP
from _editorial_normalize import canonicalize_article


def article(aid, title, company="X", date="2026-09-15", **extra):
    return canonicalize_article({"id": aid, "title": title, "companies": [company], "board": "产品与模型",
                                 "event_date": date, "sources": [{"url": f"https://example.com/{aid}", "source_id": aid, "independence_group": aid}], **extra})


class ClusteringTests(unittest.TestCase):
    def test_same_event_different_sources_merge(self):
        clusters = CE.cluster_articles([article("1", "DeepSeek V4.1 发布"), article("2", "DeepSeek V4.1 发布报道")])
        self.assertEqual(len(clusters), 1)
        self.assertEqual(set(clusters[0]["independence_groups"]), {"1", "2"})
        self.assertEqual(len(clusters[0]["sources"]), 2)
    def test_same_company_different_product_not_merged(self):
        self.assertEqual(len(CE.cluster_articles([article("1", "OpenAI 发布 Agents API"), article("2", "OpenAI 发布 Sora 视频模型")])), 2)
    def test_same_company_different_funding_round_not_merged(self):
        self.assertEqual(len(CE.cluster_articles([article("1", "Cognition 完成 B 轮融资"), article("2", "Cognition 完成 C 轮融资")])), 2)
    def test_same_company_different_version_not_merged(self):
        self.assertEqual(len(CE.cluster_articles([article("1", "DeepSeek V4.1 发布"), article("2", "DeepSeek V3.5 发布")])), 2)
    def test_date_drives_merge_decision(self):
        self.assertEqual(len(CE.cluster_articles([article("1", "X 发布 新模型", date="2026-09-01"), article("2", "X 发布 新模型报道", date="2026-09-15")])), 2)
    def test_cluster_has_standard_fields(self):
        cl = CE.cluster_articles([article("1", "X 发布", summary="摘要")])[0]
        for key in ("summary", "what_is_new", "why_it_matters", "sources", "related_events", "source_records"):
            self.assertIn(key, cl)
    def test_preserves_review_rating_and_provenance(self):
        a = article("1", "X 发布", signal_level="A", signal_reason="经营影响", independence_status="unknown", provenance={"endpoint_id":"ep"})
        cl = CE.cluster_articles([a])[0]
        self.assertEqual(cl["signal_level"], "A")
        self.assertEqual(cl["signal_reason"], "经营影响")
        self.assertIn("independence_unknown", cl["review_reasons"])
        self.assertEqual(cl["provenance_records"][0]["endpoint_id"], "ep")
    def test_explicit_verified_independence_is_preserved(self):
        cl = CE.cluster_articles([article("1", "X 发布", signal_level="A", signal_reason="经营影响", independence_status="verified")])[0]
        self.assertEqual(cl["independence_status"], "verified")
        self.assertNotIn("independence_unknown", cl["review_reasons"])
    def test_original_source_url_metadata_preserved(self):
        original = "https://original.example/article"
        a = canonicalize_article({"id":"1","title":"X 发布","companies":["X"],"event_date":"2026-09-15",
                                  "sources":[{"source_id":"s1","url":"https://mirror.example/item","original_url":original,
                                              "mirror_url":"https://mirror.example/item","endpoint_id":"ep1","collector_provider":"rss"}]})
        self.assertEqual(a["sources"][0]["original_url"], original)
        self.assertEqual(a["sources"][0]["endpoint_id"], "ep1")
    def test_rating_conflict_not_silently_promoted(self):
        clusters = CE.cluster_articles([article("1", "X 发布 新模型", signal_level="A"), article("2", "X 发布 新模型报道", signal_level="B")])
        self.assertEqual(clusters[0]["signal_level"], "unrated")
        self.assertIn("signal_conflict", clusters[0]["review_reasons"])


class RankingTests(unittest.TestCase):
    def test_agent_levels_stable_order(self):
        ranked = RE.rank_clusters([event("b", "B"), event("a", "A"), event("s", "S"), event("a2", "A"), event("n", "noise")])
        self.assertEqual([e["cluster_id"] for e in ranked], ["s", "a", "a2", "b", "n"])
    def test_no_numeric_conversion_or_keyword_rating(self):
        ev = event("x", "unrated", importance_score=99, signal_reason="", representative_title="重大突破 首次 颠覆")
        out = RE.rank_clusters([ev])[0]
        self.assertEqual(out["signal_level"], "unrated")
        self.assertNotIn("importance_score", out)
    def test_nested_business_score_is_preserved(self):
        ev = event("x", metrics={"benchmark_score": 91, "score": 0.82})
        out = RE.rank_clusters([ev])[0]
        self.assertEqual(out["metrics"]["score"], 0.82)
    def test_invalid_signal_rejected(self):
        with self.assertRaises(ValueError): RE.rank_clusters([event("x", "AAA")])
    def test_preserve_rating_reason(self):
        self.assertEqual(RE.rank_clusters([event("x", signal_reason="Agent明确理由")])[0]["signal_reason"], "Agent明确理由")
    def test_all_candidates_preserved(self):
        self.assertEqual(len(RE.rank_clusters([event(f"a{i}") for i in range(40)])), 40)
    def test_duplicate_id_rejected(self):
        with self.assertRaises(ValueError): RE.rank_clusters([event("x"),event("x")])
    def test_article_level_can_be_inherited(self):
        cl = event("x", "unrated", signal_reason="")
        out = RE.rank_clusters([cl], {"x": {"signal_level":"B","signal_reason":"影响有限"}})[0]
        self.assertEqual((out["signal_level"],out["signal_reason"]), ("B","影响有限"))


class ThesisTests(unittest.TestCase):
    def test_no_template_or_automatic_thesis(self):
        theses, _ = BT.build_theses([event("c0", "S"),event("c1", "A")])
        self.assertEqual(theses, [])
    def test_agent_statement_preserved(self):
        proposal = thesis()
        result, _ = BT.build_theses([event("c0")], [proposal])
        self.assertEqual(result[0], proposal)
    def test_single_material_event_not_rejected_by_count(self):
        self.assertEqual(len(BT.build_theses([event("c0", "S")], [thesis()])[0]), 1)
    def test_unknown_evidence_rejected(self):
        with self.assertRaises(ValueError): BT.build_theses([event("c0", independence_status="unknown")], [thesis()])
    def test_missing_event_rejected(self):
        with self.assertRaises(ValueError): BT.build_theses([], [thesis()])
    def test_four_theses_not_silently_truncated(self):
        with self.assertRaises(ValueError): BT.build_theses([event("c0")], [thesis(f"t{i}") for i in range(4)])


class RenderingTests(unittest.TestCase):
    def test_both_formats_keep_agent_text_and_sources(self):
        final, _ = final_report()
        for renderer in (EP.render_markdown, EP.render_html):
            text = renderer(final)
            self.assertIn(final["theses"][0]["statement"], text)
            self.assertIn("https://example.com/c0", text)
    def test_render_does_not_change_json(self):
        final, _ = final_report()
        before = json.dumps(final, sort_keys=True)
        EP.render_markdown(final); EP.render_html(final)
        self.assertEqual(before, json.dumps(final, sort_keys=True))
    def test_no_body_truncation(self):
        final, _ = final_report()
        final["core_events"][0]["what_is_new"] = "核验后的完整信息" * 80
        self.assertIn(final["core_events"][0]["what_is_new"], EP.render_html(final))
    def test_unsafe_link_not_rendered(self):
        final, _ = final_report()
        final["core_events"][0]["sources"][0]["url"] = "javascript:alert(1)"
        self.assertNotIn("javascript:", EP.render_html(final))


if __name__ == "__main__": unittest.main()
