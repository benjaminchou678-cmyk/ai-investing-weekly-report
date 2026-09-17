from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SourceQualityTests(unittest.TestCase):
    def run_script(self, name: str, *args: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / name), *(str(arg) for arg in args)],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )

    def test_registry_v2_is_structurally_valid(self) -> None:
        result = self.run_script(
            "validate_source_registry.py", ROOT / "references/source-registry.json",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WARN", result.stderr)  # imported WeChat accounts still need operator verification

    def test_registry_contains_157_unverified_non_hard_wechat_sources(self) -> None:
        registry = json.loads((ROOT / "references/source-registry.json").read_text(encoding="utf-8"))
        sources = [s for s in registry["sources"] if s["channel"] == "wechat_official_account"]
        self.assertEqual(len(sources), 157)
        self.assertEqual(sum(s["priority"] == "C1" for s in sources), 26)
        self.assertTrue(all(s["status"] == "unverified" and not s["hard_required"] for s in sources))

    def test_wechat_markdown_parser_is_deterministic(self) -> None:
        importer = load_module("import_wechat_sources", SCRIPTS / "import_wechat_sources.py")
        markdown = """## 创投与资本\n\n### C1 每周必查\n\n- 清科研究 `[C1]`\n- 投资界 `[C1]`\n"""
        first = importer.parse_markdown(markdown)
        second = importer.parse_markdown(markdown)
        self.assertEqual(first, second)
        self.assertEqual({s["independence_group"] for s in first}, {"zero2ipo"})

    def test_no_update_without_checked_at_fails(self) -> None:
        registry = json.loads((ROOT / "references/source-registry.json").read_text(encoding="utf-8"))
        active = [s for s in registry["sources"] if s["status"] == "active"]
        coverage = {"profile": "full_weekly", "sources": [
            {"source_id": s["source_id"], "scheduled": s["priority"] == "C1", "status": "no_update"}
            for s in active
        ]}
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            (tmp / "coverage.json").write_text(json.dumps(coverage), encoding="utf-8")
            result = self.run_script(
                "audit_source_coverage.py",
                "--registry", ROOT / "references/source-registry.json",
                "--policy", ROOT / "references/source-policy.json",
                "--coverage", tmp / "coverage.json", "--profile", "full_weekly",
                "--as-of", "2026-09-17", "--output", tmp / "qa.json",
            )
            self.assertEqual(result.returncode, 1)
            report = json.loads((tmp / "qa.json").read_text(encoding="utf-8"))
            self.assertTrue(any(x["code"] == "NO_UPDATE_WITHOUT_CHECK" for x in report["issues"]))

    def test_same_parent_accounts_share_independence_group(self) -> None:
        registry = json.loads((ROOT / "references/source-registry.json").read_text(encoding="utf-8"))
        by_name = {s["name"]: s for s in registry["sources"]}
        names = ["36氪", "36氪 Pro", "36氪出海", "硬氪"]
        self.assertEqual({by_name[name]["independence_group"] for name in names}, {"36kr"})


if __name__ == "__main__":
    unittest.main()
