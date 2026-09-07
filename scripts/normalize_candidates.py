#!/usr/bin/env python3
"""Normalize heterogeneous weekly-report candidates into schema v2."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _candidate_io import (
    as_list,
    first_value,
    iso_date,
    iter_input_files,
    read_json_items,
    stable_id,
    text_value,
    wrap_items,
    write_json,
)

BOARD_ALIASES = {
    "大厂": "大厂动向", "大厂动向": "大厂动向", "bigtech": "大厂动向",
    "初创": "初创动向", "初创动向": "初创动向", "startup": "初创动向",
    "融资": "初创动向", "生态": "生态动向", "生态动向": "生态动向",
    "政策": "生态动向", "policy": "生态动向", "技术": "技术博客&论文",
    "论文": "技术博客&论文", "paper": "技术博客&论文", "research": "技术博客&论文",
    "技术博客&论文": "技术博客&论文", "海外建设者": "海外建设者",
    "builder": "海外建设者", "观点": "观点与深度", "观点与深度": "观点与深度",
    "opinion": "观点与深度", "analysis": "观点与深度",
}


def normalize_board(value: Any) -> str:
    text = text_value(value)
    return BOARD_ALIASES.get(text.lower(), BOARD_ALIASES.get(text, text))


def infer_source_type(item: dict[str, Any], discovered: list[str]) -> str:
    explicit = text_value(first_value(item, "source_type", "sourceType", "kind", "type"))
    allowed = {"official", "media", "builder", "newsletter", "aggregator", "community", "research", "unknown"}
    if explicit.lower() in allowed:
        return explicit.lower()
    clues = " ".join(discovered).lower()
    if "builder" in clues or "twitter" in clues or "x.com" in clues:
        return "builder"
    if "newsletter" in clues or "email" in clues:
        return "newsletter"
    if "official" in clues or "官网" in clues or "官方" in clues:
        return "official"
    if "paper" in clues or "arxiv" in clues:
        return "research"
    if "aggregator" in clues or "rss" in clues:
        return "aggregator"
    return "unknown"


def normalize_sources(item: dict[str, Any], source_name: str, url: str, source_type: str) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    raw_sources = item.get("sources")
    if isinstance(raw_sources, list):
        for source in raw_sources:
            if isinstance(source, dict):
                name = text_value(first_value(source, "name", "source", "publisher"))
                link = text_value(first_value(source, "url", "link", "href"))
                kind = text_value(first_value(source, "source_type", "type", default="unknown"))
                source_id = text_value(source.get("source_id"))
                provenance = text_value(source.get("source_provenance"))
                independence_group = text_value(source.get("independence_group"))
            else:
                name, link, kind = text_value(source), "", "unknown"
                source_id, provenance, independence_group = "", "", ""
            if name or link:
                result.append({
                    "source_id": source_id, "name": name, "url": link,
                    "source_type": kind or "unknown", "source_provenance": provenance,
                    "independence_group": independence_group,
                })
    if source_name or url:
        current = {
            "source_id": "", "name": source_name, "url": url,
            "source_type": source_type, "source_provenance": "",
            "independence_group": "",
        }
        if current not in result:
            result.append(current)
    return result


def normalize_item(item: dict[str, Any], origin: str, preserve_raw: bool) -> dict[str, Any]:
    title = text_value(first_value(item, "title", "headline", "name"))
    summary = text_value(first_value(item, "summary", "description", "abstract", "content", "text", "body"))
    if not title and summary:
        title = summary[:120].strip()
    url = text_value(first_value(item, "url", "link", "href", "permalink", "original_url"))
    source = text_value(first_value(item, "source", "source_name", "publisher", "author", "site"))
    discovered = as_list(first_value(item, "discovered_via", "track", "origin", "channel"))
    if origin not in discovered:
        discovered.append(origin)
    source_type = infer_source_type(item, discovered)
    published_at, inferred_event_date = iso_date(first_value(
        item, "published_at", "publishedAt", "published", "created_at", "createdAt", "pubDate", "date"
    ))
    event_date = text_value(first_value(item, "event_date", "eventDate")) or inferred_event_date
    companies = as_list(first_value(item, "companies", "company", "organizations", "organization"))
    business_signals = as_list(first_value(item, "business_signals", "relevance_dimensions", "investment_signals"))
    board = normalize_board(first_value(item, "board", "category", "section", "topic"))

    normalized: dict[str, Any] = {
        "id": text_value(item.get("id")) or stable_id(title, url),
        "event_id": text_value(item.get("event_id")),
        "title": title,
        "url": url,
        "source": source,
        "source_type": source_type,
        "published_at": published_at,
        "event_date": event_date,
        "first_seen_at": text_value(first_value(item, "first_seen_at", "firstSeenAt")),
        "last_seen_at": text_value(first_value(item, "last_seen_at", "lastSeenAt")),
        "companies": companies,
        "entity_type": text_value(first_value(item, "entity_type", default="unknown")),
        "tickers": as_list(first_value(item, "tickers", "ticker")),
        "event_type": text_value(first_value(item, "event_type", "eventType")),
        "board": board,
        "summary": summary,
        "discovered_via": discovered,
        "sources": normalize_sources(item, source, url, source_type),
        "verification_status": text_value(first_value(item, "verification_status", "fact_status", default="unverified")),
        "claim_confidence": text_value(first_value(item, "claim_confidence", default="unrated")),
        "business_signals": business_signals,
        "signal_level": text_value(first_value(item, "signal_level", "signal", default="unrated")),
        "materiality": text_value(item.get("materiality")),
        "time_horizon": text_value(item.get("time_horizon")),
        "thesis": item.get("thesis") if isinstance(item.get("thesis"), dict) else {},
        "catalyst": text_value(item.get("catalyst")),
        "downside_risk": text_value(item.get("downside_risk")),
        "claims": item.get("claims") if isinstance(item.get("claims"), list) else [],
        "editor_reviewed": bool(item.get("editor_reviewed", False)),
        "reviewed_at": text_value(item.get("reviewed_at")),
        "previous_issue_refs": as_list(item.get("previous_issue_refs")),
    }
    if preserve_raw:
        normalized["raw"] = item
    return normalized


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="JSON/JSONL 文件或目录，可指定多个")
    parser.add_argument("--output", "-o", required=True, help="标准化 JSON 输出路径")
    parser.add_argument("--preserve-raw", action="store_true", help="在 raw 字段保留原始条目")
    parser.add_argument("--drop-empty-title", action="store_true", help="丢弃没有标题且没有可用正文的条目")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        files = iter_input_files(args.inputs)
    except (OSError, ValueError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    output_resolved = Path(args.output).expanduser().resolve()
    files = [path for path in files if path.resolve() != output_resolved]
    normalized: list[dict[str, Any]] = []
    dropped = 0
    errors: list[dict[str, str]] = []
    for path in files:
        try:
            items, _ = read_json_items(path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append({"file": str(path), "error": str(exc)})
            continue
        for item in items:
            candidate = normalize_item(item, path.stem, args.preserve_raw)
            if not candidate["title"] and args.drop_empty_title:
                dropped += 1
                continue
            normalized.append(candidate)

    payload = wrap_items(
        normalized,
        generated_at=datetime.now(timezone.utc).isoformat(),
        source_files=[str(path) for path in files],
        stats={"input_items": len(normalized) + dropped, "output_items": len(normalized), "dropped": dropped, "read_errors": len(errors)},
        errors=errors,
    )
    write_json(Path(args.output).expanduser(), payload)
    print(f"已标准化 {len(normalized)} 条候选 -> {args.output}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
