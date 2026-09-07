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
            result = self.run_script(
                "audit_candidates.py", ROOT / "examples/candidates.example.json",
                "--phase", "release", "--output", tmp / "qa.json",
                "--week-start", "2026-08-31", "--week-end", "2026-09-06",
                "--coverage", ROOT / "examples/coverage.example.json",
                "--source-registry", ROOT / "references/source-registry.json",
                "--run-manifest", ROOT / "examples/run-manifest.example.json",
                "--strict",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((tmp / "qa.json").read_text())
            self.assertEqual(report["overall_status"], "PASS")

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


if __name__ == "__main__":
    unittest.main()
