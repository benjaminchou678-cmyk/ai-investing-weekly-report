"""S/A/B/noise 与候选去向的机械回归。"""
import json
import unittest
from report_fixtures import event, final_report, thesis
import rank_events as RE
import build_theses as BT
import editorial_pass as EP
import audit_report_structure as AR
from _report_contract import LAYERS, event_id, week_meta


class MechanicalQATests(unittest.TestCase):
    def test_no_percent_score_fields(self):
        ranked=RE.rank_clusters([event("c")])
        self.assertFalse(any(k in ranked[0] for k in RE.LEGACY_FIELDS))
    def test_noise_never_body(self):
        final=EP.prepare_report([event("s","S"),event("n","noise")],week_meta("2026-09-14","2026-09-20"))
        self.assertEqual([e["cluster_id"] for e in final["core_events"]],["s"])
        self.assertEqual([e["cluster_id"] for e in final["appendix_events"]],["n"])
    def test_b_watch_not_core(self):
        final=EP.prepare_report([event("b","B")],week_meta("2026-09-14","2026-09-20"))
        self.assertEqual(final["core_events"],[])
        self.assertEqual(final["watchlist"][0]["cluster_id"],"b")
    def test_watch_overflow_retained(self):
        final=EP.prepare_report([event(f"b{i}","B") for i in range(10)],week_meta("2026-09-14","2026-09-20"))
        self.assertEqual(len(final["watchlist"]),5)
        self.assertEqual(len(final["editorial_candidate_pool"]),5)
    def test_core_overflow_retained(self):
        final=EP.prepare_report([event(f"s{i}","S") for i in range(10)],week_meta("2026-09-14","2026-09-20"))
        self.assertEqual(len(final["core_events"]),7)
        self.assertEqual(len(final["editorial_candidate_pool"]),3)
    def test_every_candidate_one_destination(self):
        events=[event(f"x{i}", level) for i,level in enumerate(["S","A","B","noise","unrated"])]
        final=EP.prepare_report(events,week_meta("2026-09-14","2026-09-20"))
        ids=[event_id(e) for layer in LAYERS for e in final[layer]]
        self.assertEqual(len(ids),len(events)); self.assertEqual(len(set(ids)),len(events))
    def test_thesis_requires_agent_proposal(self):
        self.assertEqual(BT.build_theses([event("c")])[0],[])
    def test_thesis_can_use_one_reviewed_event(self):
        self.assertEqual(len(BT.build_theses([event("c0","S")],[thesis()])[0]),1)
    def test_renderer_keeps_sources_in_both_formats(self):
        final,_=final_report()
        for text in [EP.render_markdown(final),EP.render_html(final)]: self.assertIn("https://example.com/c0",text)
    def test_display_audit_matches_same_json(self):
        final,events=final_report()
        self.assertEqual(AR.audit_report(final,events,EP.render_markdown(final),EP.render_html(final))["overall_status"],"PASS")
    def test_json_hash_changes_with_agent_edit(self):
        final,events=final_report(); first=AR.audit_report(final,events)["json_sha256"]
        final["weekly_lead"] += "修改"
        self.assertNotEqual(first,AR.audit_report(final,events)["json_sha256"])
    def test_original_event_ids_are_not_invented(self):
        final,events=final_report(); final["input_event_ids"].append("invented")
        self.assertIn("INPUT_BASELINE_CHANGED",{i["code"] for i in AR.audit_report(final,events)["issues"]})


if __name__=="__main__": unittest.main()
