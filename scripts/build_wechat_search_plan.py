#!/usr/bin/env python3
"""Build date-free, identity-aware search queries for WeChat discovery."""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any


def load_registry(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "3.0" or not isinstance(payload.get("sources"), list):
        raise ValueError("registry must be source-registry 3.0")
    return payload


def identities(source: dict[str, Any]) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = [("canonical_name", str(source.get("name") or "").strip())]
    values.extend(("alias", str(value).strip()) for value in source.get("aliases", []) if str(value).strip())
    if str(source.get("wechat_id") or "").strip():
        values.append(("wechat_id", str(source["wechat_id"]).strip()))
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for kind, value in values:
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append((kind, value))
    return result


def build_plan(
    registry: dict[str, Any], week_start: str, week_end: str,
    priorities: set[str], explicit_source_ids: set[str] | None = None,
) -> dict[str, Any]:
    start = date.fromisoformat(week_start)
    end = date.fromisoformat(week_end)
    if end < start:
        raise ValueError("week-end must not be earlier than week-start")
    next_day = end + timedelta(days=1)
    explicit_source_ids = explicit_source_ids or set()
    sources: list[dict[str, Any]] = []
    for source in registry["sources"]:
        if source.get("channel") != "wechat_official_account":
            continue
        source_id = str(source.get("source_id") or "")
        selected = source_id in explicit_source_ids or source.get("priority") in priorities
        if not selected:
            continue
        if source.get("priority") == "C3" and source_id not in explicit_source_ids:
            continue
        query_rows: list[dict[str, str]] = []
        for kind, value in identities(source):
            query_rows.append({"provider_scope": "general_web", "identity_kind": kind,
                               "query": f'site:mp.weixin.qq.com/s "{value}"'})
            query_rows.append({"provider_scope": "wechat_search", "identity_kind": kind,
                               "query": value})
        sources.append({
            "source_id": source_id,
            "name": source.get("name", ""),
            "priority": source.get("priority", ""),
            "expected_identity": {
                "account_names": [value for kind, value in identities(source) if kind != "wechat_id"],
                "wechat_id": source.get("wechat_id", ""),
                "wechat_biz_ids": source.get("wechat_biz_ids", []),
            },
            "queries": query_rows,
            "result_contract": "discovery_only_never_no_update",
        })
    return {
        "schema_version": "1.0",
        "window": {
            "timezone": "Asia/Shanghai",
            "week_start": start.isoformat(),
            "week_end_inclusive": end.isoformat(),
            "next_week_start_exclusive": next_day.isoformat(),
        },
        "query_policy": {
            "date_terms_in_query": False,
            "combine_results_by_union": True,
            "empty_result_means": "discovery_miss_not_no_update",
        },
        "source_count": len(sources),
        "sources": sources,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--week-start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--week-end", required=True, help="inclusive YYYY-MM-DD")
    parser.add_argument("--priorities", default="C1,C2")
    parser.add_argument("--source-id", action="append", default=[])
    parser.add_argument("--output", "-o", required=True)
    args = parser.parse_args()
    try:
        registry = load_registry(Path(args.registry).expanduser())
        priorities = {value.strip() for value in args.priorities.split(",") if value.strip()}
        payload = build_plan(registry, args.week_start, args.week_end, priorities, set(args.source_id))
        Path(args.output).expanduser().write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
