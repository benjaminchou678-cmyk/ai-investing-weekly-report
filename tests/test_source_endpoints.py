from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EndpointCollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.collector = load("collect_source_endpoints")
        cls.migrator = load("migrate_source_registry_v3")
        cls.endpoint_helpers = load("source_endpoints")

    def test_parse_rss_and_atom(self) -> None:
        rss = b"<rss><channel><item><title>A</title><link>https://e.test/a</link><pubDate>Fri, 18 Sep 2026 10:00:00 GMT</pubDate></item></channel></rss>"
        atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>B</title><link href="https://e.test/b"/><updated>2026-09-18T10:00:00Z</updated></entry></feed>'
        self.assertEqual(self.collector.parse_feed(rss)[0]["url"], "https://e.test/a")
        self.assertEqual(self.collector.parse_feed(atom)[0]["url"], "https://e.test/b")

    def test_parse_nested_werss_json(self) -> None:
        data = json.dumps({"data": {"list": [{"title": "A", "article_url": "https://mp.weixin.qq.com/s/a"}]}}).encode()
        self.assertEqual(self.collector.parse_json_items(data)[0]["url"], "https://mp.weixin.qq.com/s/a")

    def test_wechat_resolver_prefers_web_then_search_then_rss(self) -> None:
        common = {"status": "candidate", "purpose": ["discovery"], "officiality": "third_party"}
        source = {"channel": "wechat_official_account", "endpoints": [
            {**common, "endpoint_id": "rss", "type": "official_rss", "url": "https://e.test/rss"},
            {**common, "endpoint_id": "search", "type": "search", "query_template": "账号"},
            {**common, "endpoint_id": "web", "type": "official_html_list", "url": "https://e.test/news"},
        ]}
        ordered = self.endpoint_helpers.configured_endpoints(source)
        self.assertEqual([endpoint["endpoint_id"] for endpoint in ordered], ["web", "search", "rss"])

    def test_non_wechat_keeps_official_rss_ahead_of_web(self) -> None:
        source = {"channel": "feed", "endpoints": [
            {"endpoint_id": "web", "type": "official_html_list", "status": "candidate", "url": "https://e.test/news"},
            {"endpoint_id": "rss", "type": "official_rss", "status": "candidate", "url": "https://e.test/rss"},
        ]}
        ordered = self.endpoint_helpers.configured_endpoints(source)
        self.assertEqual([endpoint["endpoint_id"] for endpoint in ordered], ["rss", "web"])

    def test_parse_builder_x_and_podcast_json(self) -> None:
        x_data = json.dumps({"x": [{"name": "A", "handle": "a", "tweets": [
            {"text": "launch", "url": "https://x.com/a/1", "createdAt": "2026-09-18T00:00:00Z"}
        ]}]}).encode()
        podcast_data = json.dumps({"podcasts": [
            {"title": "episode", "url": "https://e.test/p", "publishedAt": "2026-09-18T00:00:00Z"}
        ]}).encode()
        self.assertEqual(self.collector.parse_json_items(x_data)[0]["title"], "launch")
        self.assertEqual(self.collector.parse_json_items(podcast_data)[0]["published_at"], "2026-09-18T00:00:00Z")

    def test_html_include_and_exclude_patterns(self) -> None:
        data = b'<a href="/news/1">AI launch</a><a href="/about">About</a><a href="/news/ad">AI ad</a>'
        endpoint = {"url": "https://e.test", "include_patterns": ["news"], "exclude_patterns": ["/ad"]}
        self.assertEqual([x["url"] for x in self.collector.parse_html(data, endpoint)], ["https://e.test/news/1"])

    def test_week_filter_keeps_unknown_and_in_range_only(self) -> None:
        items = [
            {"title": "in", "published_at": "2026-09-18T00:00:00Z"},
            {"title": "out", "published_at": "2026-09-01"},
            {"title": "unknown", "published_at": ""},
        ]
        self.assertEqual([x["title"] for x in self.collector.filter_week(items, "2026-09-14", "2026-09-20")], ["in", "unknown"])
        self.assertEqual(items[0]["date_status"], "in_window")
        self.assertEqual(items[2]["date_status"], "unknown")

    def test_rollout_artifacts_have_expected_cohorts(self) -> None:
        audit = json.loads((ROOT / "audits/source-endpoint-audit.json").read_text(encoding="utf-8"))
        schedule = json.loads((ROOT / "audits/source-rollout-schedule.json").read_text(encoding="utf-8"))
        self.assertEqual(audit["summary"]["source_counts"], {"base_15": 15, "wechat_c1_29": 29})
        self.assertEqual(schedule["summary"]["pilot"], 20)
        self.assertEqual(schedule["summary"]["c2"], 50)
        self.assertEqual(schedule["summary"]["c3"], 94)

    def test_wechat_registry_only_uses_current_endpoint_types(self) -> None:
        registry = json.loads((ROOT / "references/source-registry.json").read_text(encoding="utf-8"))
        wechat = [source for source in registry["sources"] if source.get("channel") == "wechat_official_account"]
        self.assertEqual(len(wechat), 173)
        allowed = {"official_html_list", "official_api", "official_rss", "official_atom",
                   "werss_api", "werss_rss", "rsshub", "wechat_article",
                   "wechat_machine", "search", "manual"}
        for source in wechat:
            self.assertTrue(all(endpoint.get("type") in allowed for endpoint in source["endpoints"]))

    def test_migration_json_feed_is_api_and_empty_is_unconfigured(self) -> None:
        payload = {"schema_version": "2.0", "sources": [
            {"source_id": "a", "resolver": {"primary": {"type": "rss_feed", "url": "https://e.test/feed.json", "status": "stable", "officiality": "official", "last_checked_at": "2026-09-18"}, "fallbacks": []}},
            {"source_id": "b", "resolver": {"primary": {"type": "werss", "url": "", "status": "candidate_retest"}, "fallbacks": []}},
        ]}
        result = self.migrator.migrate(payload)
        self.assertEqual(result["sources"][0]["endpoints"][0]["type"], "official_api")
        self.assertEqual(result["sources"][1]["endpoints"][0]["status"], "unconfigured")


if __name__ == "__main__":
    unittest.main()
