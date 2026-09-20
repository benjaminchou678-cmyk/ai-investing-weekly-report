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

    def test_example_report_has_three_dimension_aligned_judgments(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            result = self.run_script(
                "audit_report_structure.py", ROOT / "examples/report.example.md",
                "--output", tmp / "report-qa.json", "--strict",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((tmp / "report-qa.json").read_text(encoding="utf-8"))
            self.assertEqual(report["overall_status"], "PASS")
            self.assertEqual([x["dimension"] for x in report["judgments"]], ["产品与模型", "组织与人事", "投融资"])

    def test_report_judgment_dimension_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            malformed = (ROOT / "examples/report.example.md").read_text(encoding="utf-8").replace(
                "判断 2｜组织与人事", "判断 2｜产品与模型", 1,
            )
            (tmp / "report.md").write_text(malformed, encoding="utf-8")
            result = self.run_script(
                "audit_report_structure.py", tmp / "report.md", "--output", tmp / "report-qa.json",
            )
            self.assertEqual(result.returncode, 1)
            report = json.loads((tmp / "report-qa.json").read_text(encoding="utf-8"))
            self.assertTrue(any(x["code"] == "JUDGMENT_DIMENSIONS_MISMATCH" for x in report["issues"]))

    def test_high_confidence_judgment_requires_two_source_links(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            malformed = (ROOT / "examples/report.example.md").read_text(encoding="utf-8").replace(
                "[示例产品公告](https://example.com/company/agent-workflow) / [示例模型卡](https://example.com/model/agent-governance)",
                "[示例产品公告](https://example.com/company/agent-workflow)",
                1,
            )
            (tmp / "report.md").write_text(malformed, encoding="utf-8")
            result = self.run_script(
                "audit_report_structure.py", tmp / "report.md", "--output", tmp / "report-qa.json",
            )
            self.assertEqual(result.returncode, 1)
            report = json.loads((tmp / "report-qa.json").read_text(encoding="utf-8"))
            self.assertTrue(any(x["code"] == "HIGH_CONFIDENCE_SOURCES_LOW" for x in report["issues"]))


if __name__ == "__main__":
    unittest.main()
