"""权威 JSON、发布门与展示一致性回归。"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from report_fixtures import ROOT, final_report
import audit_report_structure as AR
import editorial_pass as EP

SCRIPTS=ROOT/"scripts"


class PipelineTests(unittest.TestCase):
    def test_valid_final_passes(self):
        final,events=final_report()
        self.assertEqual(AR.audit_report(final,events,EP.render_markdown(final),EP.render_html(final))["overall_status"],"PASS")
    def test_candidate_loss_fails(self):
        final,events=final_report()
        final["input_event_ids"].append("missing")
        self.assertIn("EVENT_RETENTION_MISMATCH",{i["code"] for i in AR.audit_report(final,events)["issues"]})
    def test_missing_ranked_baseline_fails(self):
        final,_=final_report()
        self.assertIn("INPUT_BASELINE_MISSING",{i["code"] for i in AR.audit_report(final)["issues"]})
    def test_unreviewed_json_fails_before_render(self):
        final,events=final_report()
        final["quality_status"]["editor_reviewed"]=False
        self.assertEqual(AR.audit_report(final,events)["overall_status"],"FAIL")
    def test_source_audit_fail_blocks(self):
        final,events=final_report()
        final["source_audit"]["overall_status"]="FAIL"
        self.assertIn("SOURCE_AUDIT_FAILED",{i["code"] for i in AR.audit_report(final,events)["issues"]})
    def test_source_warn_requires_disclosure(self):
        final,events=final_report()
        final["source_audit"]={"overall_status":"WARN","scope":"测试","limitations":["缺来源"]}
        self.assertIn("SOURCE_WARN_UNDISCLOSED",{i["code"] for i in AR.audit_report(final,events)["issues"]})
        final["quality_status"]["disclosures"]=["来源覆盖有限：缺来源"]
        self.assertEqual(AR.audit_report(final,events)["overall_status"],"WARN")
    def test_unknown_event_outside_review_fails(self):
        final,events=final_report()
        final["core_events"][0]["independence_status"]="unknown"
        self.assertIn("UNREVIEWED_EVENT_OUTSIDE_QUEUE",{i["code"] for i in AR.audit_report(final,events)["issues"]})
    def test_noise_in_core_fails(self):
        final,events=final_report()
        final["core_events"][0]["signal_level"]="noise"
        issues=AR.audit_report(final,events)["issues"]
        self.assertTrue(any(i["code"] in {"CORE_LEVEL_INVALID","SCHEMA_VIOLATION"} for i in issues))
    def test_claim_source_mapping_fails(self):
        final,events=final_report()
        final["core_events"][0]["claims"][0]["source_ids"]=["ghost"]
        self.assertIn("CLAIM_SOURCE_UNRESOLVED",{i["code"] for i in AR.audit_report(final,events)["issues"]})
    def test_html_source_missing_detected(self):
        final,events=final_report()
        broken=EP.render_html(final).replace("https://example.com/c0","https://example.com/changed")
        self.assertIn("HTML_SOURCE_MISSING",{i["code"] for i in AR.audit_report(final,events,html_text=broken)["issues"]})
    def test_md_content_changed_detected(self):
        final,events=final_report()
        broken=EP.render_markdown(final).replace(final["theses"][0]["statement"],"另一段话")
        self.assertIn("MD_CONTENT_MISSING",{i["code"] for i in AR.audit_report(final,events,md=broken)["issues"]})
    def test_missing_requested_file_returns_input_error(self):
        final,events=final_report()
        with tempfile.TemporaryDirectory() as raw:
            d=Path(raw); (d/"f.json").write_text(json.dumps(final,ensure_ascii=False)); (d/"r.json").write_text(json.dumps({"ranked_events":events},ensure_ascii=False))
            run=subprocess.run([sys.executable,str(SCRIPTS/"audit_report_structure.py"),"--json",str(d/"f.json"),"--ranked",str(d/"r.json"),"--html",str(d/"missing.html"),"--output",str(d/"q.json")],capture_output=True,text=True)
            self.assertEqual(run.returncode,1)
            self.assertEqual(json.loads((d/"q.json").read_text())["overall_status"],"FAIL")
    def test_prepare_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as raw:
            d=Path(raw); _,events=final_report(); (d/"r.json").write_text(json.dumps({"ranked_events":events})); out=d/"final.json"; out.write_text("keep")
            run=subprocess.run([sys.executable,str(SCRIPTS/"editorial_pass.py"),"prepare",str(d/"r.json"),"--week-start","2026-09-14","--week-end","2026-09-20","--json-out",str(out)],capture_output=True,text=True)
            self.assertEqual(run.returncode,2); self.assertEqual(out.read_text(),"keep")
    def test_render_choice_md_only(self):
        final,events=final_report()
        with tempfile.TemporaryDirectory() as raw:
            d=Path(raw); (d/"f.json").write_text(json.dumps(final,ensure_ascii=False)); (d/"r.json").write_text(json.dumps({"ranked_events":events},ensure_ascii=False))
            run=subprocess.run([sys.executable,str(SCRIPTS/"editorial_pass.py"),"render","--json",str(d/"f.json"),"--ranked",str(d/"r.json"),"--md-out",str(d/"f.md"),"--audit-out",str(d/"q.json")],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr); self.assertTrue((d/"f.md").exists()); self.assertFalse((d/"f.html").exists())
    def test_legacy_score_field_fails(self):
        final,events=final_report(); final["core_events"][0]["importance_score"]=99
        self.assertIn("LEGACY_SCORE_FIELD",{i["code"] for i in AR.audit_report(final,events)["issues"]})


if __name__=="__main__": unittest.main()
