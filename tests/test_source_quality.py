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

    def registry(self) -> dict:
        return json.loads((ROOT / "references/source-registry.json").read_text(encoding="utf-8"))

    def test_registry_v3_is_structurally_valid(self) -> None:
        result = self.run_script("validate_source_registry.py", ROOT / "references/source-registry.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WARN", result.stderr)
        self.assertEqual(self.registry()["schema_version"], "3.0")

    def test_registry_contains_173_wechat_sources(self) -> None:
        sources = [s for s in self.registry()["sources"] if s["channel"] == "wechat_official_account"]
        self.assertEqual(len(sources), 173)
        self.assertEqual(sum(s["priority"] == "C1" for s in sources), 29)
        self.assertTrue(all(s["status"] == "unverified" and not s["hard_required"] for s in sources))

    def test_every_source_has_endpoint_array(self) -> None:
        for source in self.registry()["sources"]:
            self.assertIsInstance(source.get("endpoints"), list)
            self.assertTrue(source["endpoints"], source["source_id"])

    def test_endpoint_status_and_stable_metadata(self) -> None:
        helpers = load_module("source_endpoints_test", SCRIPTS / "source_endpoints.py")
        valid = {"stable", "candidate", "fallback", "unconfigured", "blocked", "inactive"}
        for source in self.registry()["sources"]:
            for endpoint in source["endpoints"]:
                self.assertIn(endpoint["status"], valid)
                if endpoint["status"] == "stable":
                    self.assertTrue(helpers.endpoint_address_ready(endpoint), endpoint["endpoint_id"])
                    self.assertTrue(endpoint.get("last_verified_at"), endpoint["endpoint_id"])
                if endpoint["status"] == "unconfigured":
                    self.assertNotIn(endpoint, helpers.configured_endpoints(source))

    def test_wechat_markdown_parser_is_deterministic(self) -> None:
        importer = load_module("import_wechat_sources", SCRIPTS / "import_wechat_sources.py")
        markdown = """## 创投与资本

### C1 每周必查

- 清科研究 `[C1]`
- 投资界 `[C1]`
"""
        self.assertEqual(importer.parse_markdown(markdown), importer.parse_markdown(markdown))
        self.assertEqual({s["independence_group"] for s in importer.parse_markdown(markdown)}, {"zero2ipo"})

    def test_no_update_requires_verified_complete_window(self) -> None:
        source = next(s for s in self.registry()["sources"] if s["status"] == "active")
        endpoint = source["endpoints"][0]
        coverage = {"profile": "full_weekly", "sources": [{
            "source_id": source["source_id"], "scheduled": True, "checked_at": "2026-09-17T00:00:00Z",
            "status": "no_update", "account_window_complete": False,
            "endpoint_attempts": [{"endpoint_id": endpoint["endpoint_id"], "provider_group": endpoint["provider_group"],
                                   "checked_at": "2026-09-17T00:00:00Z", "status": "ok"}],
        }]}
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            (tmp / "coverage.json").write_text(json.dumps(coverage), encoding="utf-8")
            result = self.run_script(
                "audit_source_coverage.py", "--registry", ROOT / "references/source-registry.json",
                "--policy", ROOT / "references/source-policy.json", "--coverage", tmp / "coverage.json",
                "--profile", "full_weekly", "--as-of", "2026-09-17", "--output", tmp / "qa.json",
            )
            self.assertEqual(result.returncode, 1)
            codes = {item["code"] for item in json.loads((tmp / "qa.json").read_text())["issues"]}
            self.assertIn("NO_UPDATE_WINDOW_INCOMPLETE", codes)

    def test_unknown_endpoint_attempt_fails(self) -> None:
        source = next(s for s in self.registry()["sources"] if s["status"] == "active")
        coverage = {"profile": "full_weekly", "sources": [{
            "source_id": source["source_id"], "scheduled": True, "checked_at": "2026-09-17T00:00:00Z",
            "status": "failed", "account_window_complete": False,
            "endpoint_attempts": [{"endpoint_id": "not-registered", "provider_group": "test",
                                   "checked_at": "2026-09-17T00:00:00Z", "status": "failed"}],
        }]}
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            (tmp / "coverage.json").write_text(json.dumps(coverage), encoding="utf-8")
            self.run_script(
                "audit_source_coverage.py", "--registry", ROOT / "references/source-registry.json",
                "--policy", ROOT / "references/source-policy.json", "--coverage", tmp / "coverage.json",
                "--profile", "full_weekly", "--as-of", "2026-09-17", "--output", tmp / "qa.json",
            )
            codes = {item["code"] for item in json.loads((tmp / "qa.json").read_text())["issues"]}
            self.assertIn("ENDPOINT_ATTEMPT_UNKNOWN", codes)

    def test_same_parent_accounts_share_independence_group(self) -> None:
        by_name = {s["name"]: s for s in self.registry()["sources"]}
        self.assertEqual({by_name[name]["independence_group"] for name in ["36氪", "36氪 Pro", "36氪出海", "硬氪"]}, {"36kr"})

    def test_priority_frequency_contract(self) -> None:
        for source in self.registry()["sources"]:
            expected = "weekly" if source["priority"] in {"C1", "C2"} else "event_driven"
            self.assertEqual(source["check_frequency"], expected, source["source_id"])

    def test_wechat_count_matches_source_list(self) -> None:
        registry = self.registry()
        self.assertEqual(sum(s["channel"] == "wechat_official_account" for s in registry["sources"]), 173)
        self.assertEqual(sum(s["channel"] != "wechat_official_account" for s in registry["sources"]), 15)


if __name__ == "__main__":
    unittest.main()
