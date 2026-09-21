"""四场景及候选完整性回归；使用合成数据，不做事实正确性的自证。"""
import unittest
from report_fixtures import event, final_report, thesis
import editorial_pass as EP
import audit_report_structure as AR
import collect_source_endpoints as CS
from _report_contract import LAYERS, event_id, week_meta


class RefactorScenarios(unittest.TestCase):
    def test_sparse_zero_theses_is_warn_not_fail(self):
        final, events = final_report([event("c0")], [])
        qa = AR.audit_report(final, events, EP.render_markdown(final), EP.render_html(final))
        self.assertEqual(qa["overall_status"], "WARN")
    def test_normal_two_cross_board_theses(self):
        final, events = final_report(theses=[thesis("t1",["c0","c1"]),thesis("t2",["c2","c3"])])
        qa = AR.audit_report(final, events)
        self.assertEqual(qa["overall_status"], "PASS")
        self.assertEqual(len(final["theses"]),2)
    def test_major_week_three_theses(self):
        final, events = final_report(theses=[thesis("t1",["c0"]),thesis("t2",["c1","c2"]),thesis("t3",["c3","c4"])])
        self.assertEqual(AR.audit_report(final,events)["overall_status"],"PASS")
    def test_all_overflow_preserved(self):
        events = [event(f"c{i}","S") for i in range(8)] + [event(f"w{i}","B") for i in range(6)]
        final = EP.prepare_report(events,week_meta("2026-09-14","2026-09-20"))
        ids = [event_id(e) for layer in LAYERS for e in final[layer]]
        self.assertEqual(len(ids),14)
        self.assertEqual(len(set(ids)),14)
        self.assertEqual(len(final["editorial_candidate_pool"]),2)
    def test_date_unknown_before_body_selection(self):
        events = [event("unknown","S",dates=[],earliest_date="",event_date="",date_status="unknown")]
        final = EP.prepare_report(events,week_meta("2026-09-14","2026-09-20"))
        self.assertEqual(final["core_events"],[])
        self.assertEqual(len(final["human_review_queue"]),1)
    def test_unknown_independence_and_unrated_not_noise(self):
        events = [event("u","S",independence_status="unknown"),event("r","unrated"),event("n","noise")]
        final = EP.prepare_report(events,week_meta("2026-09-14","2026-09-20"))
        self.assertEqual({e["cluster_id"] for e in final["human_review_queue"]},{"u","r"})
        self.assertEqual([e["cluster_id"] for e in final["appendix_events"]],["n"])
    def test_thesis_evidence_candidate_not_removed(self):
        events = [event(f"c{i}") for i in range(8)]
        final, events = final_report(events,[thesis("t1",["c7"])])
        self.assertEqual(final["editorial_candidate_pool"][0]["cluster_id"],"c7")
        self.assertNotEqual(AR.audit_report(final,events)["overall_status"],"FAIL")
    def test_review_reason_recomputed_after_agent_fix(self):
        fixed = event("fixed", "A", review_reasons=["signal_unrated", "date_unknown"])
        final = EP.prepare_report([fixed], week_meta("2026-09-14", "2026-09-20"))
        self.assertEqual([e["cluster_id"] for e in final["core_events"]], ["fixed"])
        self.assertEqual(final["human_review_queue"], [])
    def test_shanghai_half_open_window(self):
        items=[{"title":"in","published_at":"2026-09-13T23:30:00+00:00"},
               {"title":"out","published_at":"2026-09-20T17:00:00+00:00"},
               {"title":"unknown","published_at":""}]
        out=CS.filter_week(items,"2026-09-14","2026-09-20")
        self.assertEqual({e["title"] for e in out},{"in","unknown"})
    def test_out_of_window_reviewed_before_body(self):
        f=EP.prepare_report([event("old",dates=["2026-08-01"])],week_meta("2026-09-14","2026-09-20"))
        self.assertEqual(f["core_events"],[])
        self.assertIn("out_of_window",f["human_review_queue"][0]["review_reasons"])
    def test_missing_reason_review_not_auto_filled(self):
        f=EP.prepare_report([event("x",signal_reason="")],week_meta("2026-09-14","2026-09-20"))
        self.assertIn("signal_reason_missing",f["human_review_queue"][0]["review_reasons"])


if __name__=="__main__": unittest.main()
