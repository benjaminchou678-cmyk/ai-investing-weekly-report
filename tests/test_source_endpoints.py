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

    def test_parse_rss_and_atom(self) -> None:
        rss = b"<rss><channel><item><title>A</title><link>https://e.test/a</link><pubDate>Fri, 18 Sep 2026 10:00:00 GMT</pubDate></item></channel></rss>"
        atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>B</title><link href="https://e.test/b"/><updated>2026-09-18T10:00:00Z</updated></entry></feed>'
        self.assertEqual(self.collector.parse_feed(rss)[0]["url"], "https://e.test/a")
        self.assertEqual(self.collector.parse_feed(atom)[0]["url"], "https://e.test/b")

    def test_parse_nested_werss_json(self) -> None:
        data = json.dumps({"data": {"list": [{"title": "A", "article_url": "https://mp.weixin.qq.com/s/a"}]}}).encode()
        self.assertEqual(self.collector.parse_json_items(data)[0]["url"], "https://mp.weixin.qq.com/s/a")

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
