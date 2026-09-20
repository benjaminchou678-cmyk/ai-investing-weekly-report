from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class PipelineTests(unittest.TestCase):
    def run_script(self, name: str, *args: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / name), *(str(arg) for arg in args)],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )

    def test_release_example_passes(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            # This test isolates the editorial release contract. Full source coverage
            # remains intentionally blocked until every C1/C2 endpoint is configured.
            (tmp / "source-qa.json").write_text(
                json.dumps({"overall_status": "PASS", "issues": []}), encoding="utf-8",
            )
            result = self.run_script(
                "audit_candidates.py", ROOT / "examples/candidates.example.json",
                "--phase", "release", "--output", tmp / "qa.json",
                "--week-start", "2026-08-31", "--week-end", "2026-09-06",
                "--coverage", ROOT / "examples/coverage.example.json",
                "--source-registry", ROOT / "references/source-registry.json",
                "--source-qa", tmp / "source-qa.json",
                "--run-manifest", ROOT / "examples/run-manifest.example.json",
                "--strict",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((tmp / "qa.json").read_text())
            self.assertEqual(report["overall_status"], "PASS")

    def test_full_weekly_source_gate_blocks_incomplete_endpoint_registry(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            result = self.run_script(
                "audit_source_coverage.py",
                "--registry", ROOT / "references/source-registry.json",
                "--policy", ROOT / "references/source-policy.json",
                "--coverage", ROOT / "examples/coverage.example.json",
                "--profile", "full_weekly", "--as-of", "2026-09-17",
                "--output", tmp / "source-qa.json",
            )
            self.assertEqual(result.returncode, 1)
            report = json.loads((tmp / "source-qa.json").read_text(encoding="utf-8"))
            codes = {item["code"] for item in report["issues"]}
            self.assertIn("C1_ATTEMPT_RATIO_LOW", codes)
            self.assertIn("SOURCE_ENDPOINT_COVERAGE_LOW", codes)

    def test_registry_omission_fails_source_gate(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            coverage = {"sources": [{"source_id": "openai-news", "status": "ok"}]}
            (tmp / "coverage.json").write_text(json.dumps(coverage))
            result = self.run_script(
                "audit_candidates.py", ROOT / "examples/candidates.example.json",
                "--phase", "pre-edit", "--output", tmp / "qa.json",
                "--week-start", "2026-08-31", "--week-end", "2026-09-06",
                "--coverage", tmp / "coverage.json",
                "--source-registry", ROOT / "references/source-registry.json",
                "--run-manifest", ROOT / "examples/run-manifest.example.json",
            )
            self.assertEqual(result.returncode, 1)
            report = json.loads((tmp / "qa.json").read_text())
            self.assertEqual(report["gates"]["gate1_source_health"]["status"], "FAIL")

    def test_ambiguous_similar_titles_are_not_auto_merged(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            payload = {"items": [
                {"id": "1", "title": "公司发布新模型产品", "url": "https://a.example/post/one"},
                {"id": "2", "title": "公司发布新模型产品", "url": "https://b.example/post/two"},
            ]}
            (tmp / "input.json").write_text(json.dumps(payload, ensure_ascii=False))
            result = self.run_script(
                "merge_candidates.py", tmp / "input.json",
                "--output", tmp / "merged.json", "--report", tmp / "merge.json",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            merged = json.loads((tmp / "merged.json").read_text())
            self.assertEqual(len(merged["items"]), 2)
            audit = json.loads((tmp / "merge.json").read_text())
            self.assertEqual(len(audit["review_pairs"]), 1)

    def test_normalizer_infers_three_core_boards_from_event_type(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            payload = {"items": [
                {"title": "旗舰模型发布", "event_type": "模型发布"},
                {"title": "首席科学家离职", "event_type": "离职"},
                {"title": "公司完成融资", "event_type": "融资"},
            ]}
            (tmp / "input.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            result = self.run_script(
                "normalize_candidates.py", tmp / "input.json", "--output", tmp / "normalized.json",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            normalized = json.loads((tmp / "normalized.json").read_text(encoding="utf-8"))
            self.assertEqual(
                [item["board"] for item in normalized["items"]],
                ["产品与模型", "组织与人事", "投融资"],
            )

    def _valid_thesis(self, tid: str, groups=None) -> dict:
        groups = groups or ["g1"]
        ev = [{"cluster_id": f"{tid}-e{i}", "title": f"证据{i}", "score": 80,
               "independence_status": "verified", "independence_groups": [g]}
              for i, g in enumerate(groups)]
        return {
            "thesis_id": tid, "theme": "T", "statement": "一条足够长且可证伪的产业判断主张",
            "structural_change": "结构变化", "key_evidence": ev,
            "why_it_matters": "为什么重要", "investment_readthrough": "投资含义",
            "counter_evidence": "反方证据", "falsification_conditions": "推翻条件",
            "confidence": "medium", "related_boards": ["产品与模型"],
        }

    def _write_final(self, tmp: Path, theses) -> Path:
        data = {
            "schema_version": "3.0",
            "report_meta": {"week_label": "w", "week_start": "2026-09-14",
                            "week_end": "2026-09-20", "timezone": "Asia/Shanghai",
                            "generated_at": "2026-09-20T00:00:00+08:00"},
            "weekly_lead": "本周主线已形成。",
            "theses": theses,
            "core_events": [{"cluster_id": "c1", "title": "核心", "score": 85, "tier": "core"}],
            "watchlist": [], "editorial_candidate_pool": [], "human_review_queue": [],
            "appendix_events": [], "excluded_events": [], "source_audit": {},
            "quality_status": {"thesis_count": len(theses), "core_count": 1,
                               "watchlist_count": 0, "status": "PASS"},
        }
        p = tmp / "final.json"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return p

    def test_final_report_two_theses_passes(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            fj = self._write_final(tmp, [self._valid_thesis("t1", ["g1", "g2"]),
                                         self._valid_thesis("t2", ["g3", "g4"])])
            result = self.run_script("audit_report_structure.py", "--json", fj,
                                     "--output", tmp / "qa.json")
            self.assertEqual(result.returncode, 0, result.stderr)
            qa = json.loads((tmp / "qa.json").read_text(encoding="utf-8"))
            self.assertEqual(qa["overall_status"], "PASS")

    def test_zero_theses_allowed_when_evidence_insufficient(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            data = json.loads(self._write_final(tmp, []).read_text(encoding="utf-8"))
            data["weekly_lead"] = "本周未形成达到证据门槛的产业判断，信号留在观察池。"
            fj = tmp / "final.json"
            fj.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            result = self.run_script("audit_report_structure.py", "--json", fj,
                                     "--output", tmp / "qa.json")
            self.assertEqual(result.returncode, 0, result.stderr)  # WARN, not FAIL
            qa = json.loads((tmp / "qa.json").read_text(encoding="utf-8"))
            self.assertIn("ZERO_THESIS", [i["code"] for i in qa["issues"]])

    def test_too_many_theses_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            theses = [self._valid_thesis(f"t{i}", [f"g{i}a", f"g{i}b"]) for i in range(4)]
            fj = self._write_final(tmp, theses)
            result = self.run_script("audit_report_structure.py", "--json", fj,
                                     "--output", tmp / "qa.json")
            self.assertEqual(result.returncode, 1)
            qa = json.loads((tmp / "qa.json").read_text(encoding="utf-8"))
            self.assertTrue(any(i["code"] == "THESIS_COUNT_TOO_HIGH" for i in qa["issues"]))

    def test_unknown_independence_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            t = self._valid_thesis("t1", ["g1", "g2"])
            t["key_evidence"][0]["independence_status"] = "unknown"
            fj = self._write_final(tmp, [t])
            result = self.run_script("audit_report_structure.py", "--json", fj,
                                     "--output", tmp / "qa.json")
            self.assertEqual(result.returncode, 1)
            qa = json.loads((tmp / "qa.json").read_text(encoding="utf-8"))
            self.assertTrue(any(i["code"] == "THESIS_EVIDENCE_INDEPENDENCE_UNKNOWN"
                                for i in qa["issues"]))


if __name__ == "__main__":
    unittest.main()
