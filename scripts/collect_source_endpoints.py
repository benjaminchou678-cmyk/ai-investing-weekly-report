#!/usr/bin/env python3
"""Collect RSS/Atom, HTML-list and WeRSS endpoints into common candidate JSON.

This collector is intentionally conservative: it never invents account IDs,
does not bypass authentication or access controls, and records incomplete
enumeration as such in coverage output.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from source_endpoints import configured_endpoints


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_bytes(url: str, timeout: int, credential_ref: str = "") -> bytes:
    headers = {"User-Agent": "AIInvestingWeeklyReport/1.0"}
    if credential_ref:
        token = os.environ.get(credential_ref)
        if not token:
            raise RuntimeError(f"credential_missing:{credential_ref}")
        headers["X-API-Key"] = token
    with urlopen(Request(url, headers=headers), timeout=timeout) as response:
        return response.read()


def text(node: ET.Element | None, names: tuple[str, ...]) -> str:
    if node is None:
        return ""
    for child in node.iter():
        local = child.tag.rsplit("}", 1)[-1].lower()
        if local in names and child.text and child.text.strip():
            return child.text.strip()
    return ""


def parse_feed(data: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(data)
    entries = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1].lower() in {"item", "entry"}]
    result = []
    for entry in entries:
        link = text(entry, ("link",))
        if not link:
            for child in entry.iter():
                if child.tag.rsplit("}", 1)[-1].lower() == "link" and child.attrib.get("href"):
                    link = child.attrib["href"]
                    break
        result.append({
            "title": text(entry, ("title",)),
            "url": link,
            "published_at": text(entry, ("pubdate", "published", "updated", "date")),
            "summary": text(entry, ("description", "summary", "content")),
        })
    return [item for item in result if item["title"] or item["url"]]


class LinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.current_href = ""
        self.current_text: list[str] = []
        self.links: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            values = dict(attrs)
            self.current_href = urljoin(self.base_url, values.get("href") or "")
            self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.current_href:
            self.current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self.current_href:
            title = " ".join("".join(self.current_text).split())
            if title and self.current_href.startswith(("http://", "https://")):
                self.links.append({"title": title, "url": self.current_href, "published_at": "", "summary": ""})
            self.current_href = ""
            self.current_text = []


def parse_html(data: bytes, endpoint: dict[str, Any]) -> list[dict[str, str]]:
    parser = LinkParser(str(endpoint.get("url") or ""))
    parser.feed(data.decode("utf-8", errors="replace"))
    include = [re.compile(p) for p in endpoint.get("include_patterns", [])]
    exclude = [re.compile(p) for p in endpoint.get("exclude_patterns", [])]
    seen, result = set(), []
    for item in parser.links:
        basis = f"{item['title']} {item['url']}"
        if include and not any(pattern.search(basis) for pattern in include):
            continue
        if any(pattern.search(basis) for pattern in exclude):
            continue
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        result.append(item)
    return result


def parse_json_items(data: bytes) -> list[dict[str, str]]:
    payload = json.loads(data.decode("utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("x"), list):
        flattened = []
        for account in payload["x"]:
            if not isinstance(account, dict):
                continue
            for tweet in account.get("tweets", []):
                if isinstance(tweet, dict):
                    flattened.append({
                        "title": str(tweet.get("text") or ""), "url": str(tweet.get("url") or ""),
                        "published_at": str(tweet.get("createdAt") or ""),
                        "summary": f"{account.get('name', '')} (@{account.get('handle', '')})".strip(),
                    })
        return flattened
    candidates: Any = payload
    if isinstance(payload, dict):
        for key in ("items", "articles", "entries", "results", "data", "podcasts", "blogs"):
            if isinstance(payload.get(key), list):
                candidates = payload[key]
                break
            if isinstance(payload.get(key), dict):
                nested = payload[key]
                for nested_key in ("items", "articles", "list", "records"):
                    if isinstance(nested.get(nested_key), list):
                        candidates = nested[nested_key]
                        break
                if isinstance(candidates, list):
                    break
    if not isinstance(candidates, list):
        return []
    result = []
    for row in candidates:
        if not isinstance(row, dict):
            continue
        result.append({
            "title": str(row.get("title") or row.get("name") or ""),
            "url": str(row.get("url") or row.get("link") or row.get("article_url") or ""),
            "published_at": str(row.get("published_at") or row.get("publishedAt") or row.get("publish_time") or row.get("pubDate") or ""),
            "summary": str(row.get("summary") or row.get("description") or row.get("digest") or row.get("transcript") or "")[:4000],
        })
    return [item for item in result if item["title"] or item["url"]]


def parse_item_date(value: str) -> datetime | None:
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(raw)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            return None


def filter_week(items: list[dict[str, str]], week_start: str, week_end: str) -> list[dict[str, str]]:
    start = datetime.fromisoformat(week_start).date()
    end = datetime.fromisoformat(week_end).date()
    result = []
    for item in items:
        published = parse_item_date(str(item.get("published_at") or ""))
        if published is None:
            item["date_status"] = "unknown"
            result.append(item)
        elif start <= published.date() <= end:
            item["date_status"] = "in_window"
            result.append(item)
    return result


def endpoint_url(endpoint: dict[str, Any], week_start: str, week_end: str) -> str:
    endpoint_type = endpoint.get("type")
    if endpoint_type == "rsshub" and not endpoint.get("url"):
        return urljoin(str(endpoint.get("base_url") or "").rstrip("/") + "/", str(endpoint.get("route") or "").lstrip("/"))
    if endpoint_type == "werss_api":
        base = str(endpoint.get("url") or "").rstrip("/")
        path = str(endpoint.get("api_path") or "/api/v1/wx/articles")
        query = {
            "mp_id": endpoint.get("account_id"),
            "start_date": week_start,
            "end_date": week_end,
        }
        return f"{base}{path}?{urlencode({k: v for k, v in query.items() if v})}"
    return str(endpoint.get("url") or "")


def collect_endpoint(endpoint: dict[str, Any], week_start: str, week_end: str, timeout: int) -> tuple[list[dict[str, str]], bool]:
    endpoint_type = endpoint.get("type")
    url = endpoint_url(endpoint, week_start, week_end)
    data = fetch_bytes(url, timeout, str(endpoint.get("credential_ref") or ""))
    if endpoint_type in {"official_rss", "official_atom", "werss_rss", "rsshub"}:
        return parse_feed(data), bool(endpoint.get("date_filterable") and endpoint.get("list_enumerable"))
    if endpoint_type in {"official_api", "werss_api"}:
        return parse_json_items(data), bool(endpoint.get("date_filterable") and endpoint.get("list_enumerable"))
    if endpoint_type == "official_html_list":
        return parse_html(data, endpoint), bool(endpoint.get("date_filterable") and endpoint.get("list_enumerable"))
    raise RuntimeError(f"unsupported_endpoint_type:{endpoint_type}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--week-start", required=True)
    parser.add_argument("--week-end", required=True)
    parser.add_argument("--source-id", action="append", default=[])
    parser.add_argument("--plan", help="source-rollout-plan.json；与 --cohort 一起使用")
    parser.add_argument("--cohort", choices=["pilot", "c2_weekly"], help="从 plan 读取来源集合")
    parser.add_argument("--output", required=True)
    parser.add_argument("--coverage-output", required=True)
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    selected = set(args.source_id)
    if args.cohort:
        if not args.plan:
            parser.error("--cohort 需要 --plan")
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        if args.cohort == "pilot":
            selected.update(plan["pilot"]["source_ids"])
        else:
            rule = plan["c2_scan"]
            selected.update(
                source["source_id"] for source in registry.get("sources", [])
                if source.get("channel") == rule["channel"] and source.get("priority") == rule["priority"]
            )
    candidates: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    for source in registry.get("sources", []):
        if selected and source.get("source_id") not in selected:
            continue
        endpoints = configured_endpoints(source)
        attempts = []
        found = []
        complete = False
        for endpoint in endpoints:
            checked_at = now_iso()
            try:
                items, endpoint_complete = collect_endpoint(endpoint, args.week_start, args.week_end, args.timeout)
                items = filter_week(items, args.week_start, args.week_end)
                complete = complete or endpoint_complete
                found.extend(items)
                attempts.append({
                    "endpoint_id": endpoint["endpoint_id"], "provider_group": endpoint["provider_group"],
                    "checked_at": checked_at, "status": "ok", "items_found": len(items),
                    "window_complete": endpoint_complete, "failure_code": "",
                })
                for item in items:
                    candidates.append({
                        **item, "source_id": source["source_id"], "source_name": source["name"],
                        "endpoint_id": endpoint["endpoint_id"], "discovered_via": endpoint["type"],
                        "collector_provider": endpoint["provider_group"], "canonical_url": item.get("url", ""),
                        "original_url": item.get("url", ""),
                        "mirror_url": endpoint_url(endpoint, args.week_start, args.week_end)
                        if endpoint.get("officiality") in {"third_party", "official_proxy"} else "",
                    })
                if items and endpoint.get("status") != "fallback":
                    break
            except Exception as exc:
                code = str(exc).split(":", 1)[0][:80]
                attempts.append({
                    "endpoint_id": endpoint.get("endpoint_id", ""), "provider_group": endpoint.get("provider_group", "unknown"),
                    "checked_at": checked_at, "status": "blocked" if code == "credential_missing" else "failed",
                    "items_found": 0, "window_complete": False, "failure_code": code,
                })
        any_success = any(attempt.get("status") == "ok" for attempt in attempts)
        status = "ok" if found else "no_update" if attempts and complete and any_success else "stale" if any_success else "failed" if attempts else "not_scheduled"
        coverage.append({
            "source_id": source.get("source_id"), "scheduled": bool(endpoints), "checked_at": now_iso() if attempts else "",
            "status": status, "new_items": len(found), "account_window_complete": complete,
            "endpoint_attempts": attempts,
            "failure_code": "window_incomplete_no_items" if status == "stale" else "" if attempts else "no_configured_endpoint",
        })
    output_path = Path(args.output)
    coverage_path = Path(args.coverage_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({"schema_version": "2.0", "items": candidates}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    coverage_path.write_text(json.dumps({
        "schema_version": "2.0", "week_start": args.week_start, "week_end": args.week_end,
        "profile": "full_weekly", "sources": coverage,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"collected {len(candidates)} candidates from {len(coverage)} sources", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
