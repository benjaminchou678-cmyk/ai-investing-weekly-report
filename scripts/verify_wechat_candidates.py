#!/usr/bin/env python3
"""Verify WeChat candidate identity, then filter by the weekly time window."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")


def norm(value: Any) -> str:
    return re.sub(r"[\s`_\-·•]+", "", str(value or "").strip()).casefold()


def biz_from_url(url: str) -> str:
    try:
        return (parse_qs(urlparse(url).query).get("__biz") or [""])[0]
    except ValueError:
        return ""


def parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ)
    return parsed.astimezone(TZ)


def identity_result(source: dict[str, Any], candidate: dict[str, Any]) -> tuple[str, str]:
    expected_biz = {str(value) for value in source.get("wechat_biz_ids", []) if str(value)}
    actual_biz = str(candidate.get("biz_id") or biz_from_url(str(candidate.get("url") or candidate.get("canonical_url") or "")))
    if actual_biz and expected_biz:
        return ("verified", "biz_id") if actual_biz in expected_biz else ("mismatch", "biz_id")

    expected_wechat_id = norm(source.get("wechat_id"))
    actual_wechat_id = norm(candidate.get("wechat_id"))
    if actual_wechat_id and expected_wechat_id:
        return ("verified", "wechat_id") if actual_wechat_id == expected_wechat_id else ("mismatch", "wechat_id")

    expected_names = {norm(source.get("name")), *(norm(value) for value in source.get("aliases", []))}
    expected_names.discard("")
    actual_name = norm(candidate.get("account_name") or candidate.get("author"))
    if actual_name:
        return ("inferred", "account_name") if actual_name in expected_names else ("mismatch", "account_name")
    return "unknown", "missing_identity"


def verify(
    registry: dict[str, Any], candidates_payload: Any, week_start: str, next_week_start: str,
) -> dict[str, Any]:
    sources = {source["source_id"]: source for source in registry.get("sources", [])}
    items = candidates_payload.get("items", []) if isinstance(candidates_payload, dict) else candidates_payload
    if not isinstance(items, list):
        raise ValueError("candidates must be a list or an object with items[]")
    start = datetime.fromisoformat(week_start).replace(tzinfo=TZ)
    end = datetime.fromisoformat(next_week_start).replace(tzinfo=TZ)
    if end <= start:
        raise ValueError("next-week-start must be later than week-start")
    buckets: dict[str, list[dict[str, Any]]] = {
        "verified_in_window": [], "identity_review_queue": [],
        "date_unknown_review_queue": [], "out_of_window": [], "source_unknown_queue": [],
    }
    for original in items:
        candidate = dict(original)
        source = sources.get(str(candidate.get("source_id") or ""))
        if not source:
            candidate["verification"] = {"identity_status": "unknown", "reason": "source_id_not_registered"}
            buckets["source_unknown_queue"].append(candidate)
            continue
        status, method = identity_result(source, candidate)
        published = parse_time(candidate.get("published_at") or candidate.get("original_published_at"))
        candidate["verification"] = {
            "identity_status": status, "identity_method": method,
            "published_at_normalized": published.isoformat() if published else "",
        }
        if status not in {"verified", "inferred"}:
            buckets["identity_review_queue"].append(candidate)
        elif published is None:
            buckets["date_unknown_review_queue"].append(candidate)
        elif start <= published < end:
            buckets["verified_in_window"].append(candidate)
        else:
            buckets["out_of_window"].append(candidate)
    return {
        "schema_version": "1.0",
        "window": {"timezone": "Asia/Shanghai", "week_start": week_start,
                   "next_week_start_exclusive": next_week_start},
        "semantics": {"empty_input_means": "no_candidates_discovered_not_no_update"},
        "counts": {key: len(value) for key, value in buckets.items()},
        **buckets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--week-start", required=True)
    parser.add_argument("--next-week-start", required=True)
    parser.add_argument("--output", "-o", required=True)
    args = parser.parse_args()
    try:
        registry = json.loads(Path(args.registry).expanduser().read_text(encoding="utf-8"))
        candidates = json.loads(Path(args.candidates).expanduser().read_text(encoding="utf-8"))
        result = verify(registry, candidates, args.week_start, args.next_week_start)
        Path(args.output).expanduser().write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
