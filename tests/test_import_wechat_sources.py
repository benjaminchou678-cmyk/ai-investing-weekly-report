from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/import_wechat_sources.py"


def load_importer():
    spec = importlib.util.spec_from_file_location("import_wechat_sources_safe", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ImportWechatSourcesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_importer()

    def base_registry(self) -> dict:
        return {
            "schema_version": "3.0",
            "sources": [
                {"source_id": "web-1", "name": "Web", "channel": "web"},
                {
                    "source_id": "wechat-old",
                    "name": "旧名称",
                    "aliases": ["新名称"],
                    "channel": "wechat_official_account",
                    "operator": "已核验主体",
                    "operator_verified": True,
                    "role": "industry_media",
                    "priority": "C3",
                    "hard_required": False,
                    "check_frequency": "event_driven",
                    "discovery_mode": "event_driven",
                    "coverage_dimensions": ["research"],
                    "parent_group": "verified-group",
                    "independence_group": "verified-group",
                    "access": {"mode": "rss", "paywall": False},
                    "status": "active",
                    "last_verified_at": "2026-09-18",
                    "evidence_limit": "verified",
                    "catalog_section": "科技与 AI",
                    "primary_track": "media_business_verification",
                    "secondary_tracks": [],
                    "endpoints": [{
                        "endpoint_id": "wechat-old-official-rss-1", "type": "official_rss", "status": "stable",
                        "purpose": ["discovery", "evidence"], "officiality": "official", "provider_group": "official",
                        "url": "https://example.com/feed", "last_verified_at": "2026-09-18",
                    }],
                },
                {
                    "source_id": "wechat-keep",
                    "name": "未出现在新名单",
                    "aliases": [],
                    "channel": "wechat_official_account",
                },
            ],
        }

    def test_accepts_plain_and_backtick_labels(self) -> None:
        text = """## 科技与 AI
### C1 每周必查
- 量子位 [C1]
- 新智元 `[C1]`
"""
        items = self.mod.parse_markdown(text)
        self.assertEqual([x["name"] for x in items], ["量子位", "新智元"])
        self.assertTrue(all(x["check_frequency"] == "weekly" for x in items))

    def test_c2_is_weekly_lightweight(self) -> None:
        item = self.mod.parse_markdown("## 科技与 AI\n### C2\n- 测试源 [C2]\n")[0]
        self.assertEqual(item["check_frequency"], "weekly")
        self.assertEqual(item["discovery_mode"], "lightweight")

    def test_fa_is_stakeholder_and_capital_track(self) -> None:
        item = self.mod.parse_markdown("## FA / 融资顾问\n### C2\n- 某FA `[C2]`\n")[0]
        self.assertEqual(item["role"], "investor_stakeholder")
        self.assertEqual(item["primary_track"], "capital_market")

    def test_empty_unknown_conflict_and_duplicate_fail_closed(self) -> None:
        bad = [
            "",
            "## 未知分类\n### C1\n- 某源 [C1]\n",
            "## 科技与 AI\n### C1\n- 某源 [C2]\n",
            "## 科技与 AI\n### C1\n- 某源 [C1]\n- 某 源 `[C1]`\n",
        ]
        for text in bad:
            with self.subTest(text=text):
                with self.assertRaises(self.mod.ImportValidationError):
                    self.mod.parse_markdown(text)

    def test_merge_preserves_verified_metadata_and_stable_id(self) -> None:
        fresh = self.mod.parse_markdown("## 科技与 AI\n### C1\n- 新名称 [C1]\n")
        out = self.mod.merge_wechat_sources(self.base_registry(), fresh)
        updated = next(x for x in out["sources"] if x.get("source_id") == "wechat-old")
        self.assertEqual(updated["name"], "新名称")
        self.assertEqual(updated["operator"], "已核验主体")
        self.assertEqual(updated["endpoints"][0]["url"], "https://example.com/feed")
        self.assertEqual(updated["check_frequency"], "weekly")
        self.assertIn("旧名称", updated["aliases"])

    def test_new_source_gets_truthful_unconfigured_endpoint(self) -> None:
        fresh = self.mod.parse_markdown("## 科技与 AI\n### C1\n- 新公众号 [C1]\n")
        out = self.mod.merge_wechat_sources({"schema_version": "3.0", "sources": []}, fresh)
        endpoint = out["sources"][0]["endpoints"][0]
        self.assertEqual(endpoint["type"], "mpscraper_mcp")
        self.assertEqual(endpoint["status"], "unconfigured")
        self.assertEqual(endpoint["account_name"], "新公众号")
        self.assertEqual(endpoint["url"], "http://127.0.0.1:8082/mcp")

    def test_default_keeps_unlisted_and_replace_drops_it(self) -> None:
        fresh = self.mod.parse_markdown("## 科技与 AI\n### C1\n- 新名称 [C1]\n")
        kept = self.mod.merge_wechat_sources(self.base_registry(), fresh)
        replaced = self.mod.merge_wechat_sources(self.base_registry(), fresh, replace_wechat=True)
        self.assertIn("wechat-keep", {x.get("source_id") for x in kept["sources"]})
        self.assertNotIn("wechat-keep", {x.get("source_id") for x in replaced["sources"]})
        self.assertIn("web-1", {x.get("source_id") for x in replaced["sources"]})

    def test_cli_failure_does_not_modify_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            registry = root / "registry.json"
            markdown = root / "list.md"
            output = root / "output.json"
            registry.write_text(json.dumps(self.base_registry()), encoding="utf-8")
            markdown.write_text("## 未知分类\n### C1\n- 某源 [C1]\n", encoding="utf-8")
            output.write_text("sentinel", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(markdown), "--registry", str(registry), "--output", str(output)],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "sentinel")

    def test_cli_success_writes_valid_json_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            registry = root / "registry.json"
            markdown = root / "list.md"
            output = root / "output.json"
            registry.write_text(json.dumps(self.base_registry()), encoding="utf-8")
            markdown.write_text("## 科技与 AI\n### C1\n- 新名称 [C1]\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(markdown), "--registry", str(registry), "--output", str(output)],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(list(root.glob(".output.json.*.tmp")))


if __name__ == "__main__":
    unittest.main()
