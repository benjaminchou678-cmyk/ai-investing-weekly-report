#!/usr/bin/env python3
"""Merge weekly-report candidates without collapsing ambiguous events."""

from __future__ import annotations

import argparse
import re
import sys
from copy import deepcopy
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from _candidate_io import as_list, iter_input_files, read_json_items, stable_id, wrap_items, write_json

TRACKING_PARAMS = {"fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "ref", "ref_src", "source"}
VERIFICATION_RANK = {"independently_verified": 5, "verified_primary": 4, "company_disclosure": 3, "single_source": 2, "unverified": 1, "conflicting": 0, "": 0}
CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1, "unrated": 0, "": 0}
SOURCE_RANK = {"official": 6, "research": 5, "media": 4, "builder": 3, "newsletter": 2, "community": 1, "aggregator": 0, "unknown": 0}


def canonical_url(url: Any) -> str:
    text = str(url or "").strip()
    if not text.startswith(("http://", "https://")):
        return ""
    try:
        parts = urlsplit(text)
    except ValueError:
        return text.rstrip("/")
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS]
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def normalized_title(title: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(title or "").lower())


def title_similarity(left: Any, right: Any) -> float:
    a, b = normalized_title(left), normalized_title(right)
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def event_dates_compatible(left: dict[str, Any], right: dict[str, Any]) -> bool:
    a, b = str(left.get("event_date") or ""), str(right.get("event_date") or "")
    return bool(a and b and a == b)


def companies_compatible(left: dict[str, Any], right: dict[str, Any]) -> bool:
    a = {v.lower() for v in as_list(left.get("companies"))}
    b = {v.lower() for v in as_list(right.get("companies"))}
    return bool(a and b and a & b)


def event_types_compatible(left: dict[str, Any], right: dict[str, Any]) -> bool:
    a = str(left.get("event_type") or "").strip().lower()
    b = str(right.get("event_type") or "").strip().lower()
    return bool(a and b and a == b)


def item_score(item: dict[str, Any]) -> tuple[int, int, int, int]:
    sources = item.get("sources") if isinstance(item.get("sources"), list) else []
    return (
        VERIFICATION_RANK.get(str(item.get("verification_status", "")).lower(), 0),
        CONFIDENCE_RANK.get(str(item.get("claim_confidence", "")).lower(), 0),
        SOURCE_RANK.get(str(item.get("source_type", "")).lower(), 0),
        len(sources),
    )


def unique_list(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        key = repr(sorted(value.items())) if isinstance(value, dict) else str(value).lower()
        if key not in seen and value not in (None, ""):
            seen.add(key)
            result.append(value)
    return result


def merge_pair(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    preferred, other = (left, right) if item_score(left) >= item_score(right) else (right, left)
    merged = deepcopy(preferred)
    for field in ("companies", "discovered_via", "business_signals"):
        merged[field] = unique_list(as_list(preferred.get(field)) + as_list(other.get(field)))
    merged["sources"] = unique_list(
        (preferred.get("sources") if isinstance(preferred.get("sources"), list) else [])
        + (other.get("sources") if isinstance(other.get("sources"), list) else [])
    )
    # Keep the summary from the better-evidenced item. Claims from the other
    # item remain attributable through its source rather than being spliced in.
    merged.setdefault("merged_ids", [])
    merged["merged_ids"] = unique_list(as_list(merged["merged_ids"]) + [str(left.get("id", "")), str(right.get("id", ""))])
    source_names = {str(source.get("name") or source.get("url") or "").strip().lower() for source in merged["sources"] if isinstance(source, dict)}
    source_names.discard("")
    merged["source_count"] = len(source_names)
    if len(source_names) >= 2 and merged.get("verification_status") in {"", "unverified", "single_source"}:
        merged["verification_status"] = "multi_source_candidate"
    merged["id"] = stable_id(str(merged.get("title") or ""), canonical_url(merged.get("url")))
    return merged


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="一个或多个标准化候选文件/目录")
    parser.add_argument("--output", "-o", required=True, help="合并后的候选 JSON")
    parser.add_argument("--report", required=True, help="去重审计报告")
    parser.add_argument("--title-threshold", type=float, default=0.86, help="自动标题去重阈值")
    parser.add_argument("--review-threshold", type=float, default=0.72, help="疑似重复候选阈值")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        files = iter_input_files(args.inputs)
    except OSError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    excluded = {Path(args.output).expanduser().resolve(), Path(args.report).expanduser().resolve()}
    files = [path for path in files if path.resolve() not in excluded]
    items: list[dict[str, Any]] = []
    read_errors: list[dict[str, str]] = []
    for path in files:
        try:
            rows, _ = read_json_items(path)
            items.extend(deepcopy(rows))
        except (OSError, ValueError) as exc:
            read_errors.append({"file": str(path), "error": str(exc)})

    exact_merges = 0
    by_url: dict[str, dict[str, Any]] = {}
    no_url: list[dict[str, Any]] = []
    for item in items:
        key = canonical_url(item.get("url"))
        if not key:
            no_url.append(item)
        elif key in by_url and event_dates_compatible(by_url[key], item) and companies_compatible(by_url[key], item) and event_types_compatible(by_url[key], item):
            by_url[key] = merge_pair(by_url[key], item)
            exact_merges += 1
        elif key in by_url:
            no_url.append(item)
        else:
            by_url[key] = item
    working = list(by_url.values()) + no_url

    consumed: set[int] = set()
    merged_items: list[dict[str, Any]] = []
    fuzzy_merges: list[dict[str, Any]] = []
    review_pairs: list[dict[str, Any]] = []
    for i, item in enumerate(working):
        if i in consumed:
            continue
        current = item
        for j in range(i + 1, len(working)):
            if j in consumed:
                continue
            other = working[j]
            similarity = title_similarity(current.get("title"), other.get("title"))
            compatible = event_dates_compatible(current, other) and companies_compatible(current, other) and event_types_compatible(current, other)
            pair = {"left_id": current.get("id", ""), "right_id": other.get("id", ""), "left_title": current.get("title", ""), "right_title": other.get("title", ""), "similarity": round(similarity, 4)}
            if similarity >= args.title_threshold and compatible:
                current = merge_pair(current, other)
                consumed.add(j)
                fuzzy_merges.append(pair)
            elif similarity >= args.review_threshold:
                pair["compatible"] = compatible
                review_pairs.append(pair)
        merged_items.append(current)
    merged_items.sort(key=lambda item: (str(item.get("event_date") or ""), str(item.get("published_at") or ""), str(item.get("title") or "")), reverse=True)

    report = {
        "input_files": [str(path) for path in files], "input_items": len(items),
        "output_items": len(merged_items), "exact_url_merges": exact_merges,
        "fuzzy_title_merges": fuzzy_merges, "review_pairs": review_pairs,
        "read_errors": read_errors, "title_threshold": args.title_threshold,
        "review_threshold": args.review_threshold,
    }
    write_json(Path(args.output).expanduser(), wrap_items(merged_items, merge_report=args.report))
    write_json(Path(args.report).expanduser(), report)
    print(f"合并完成: {len(items)} -> {len(merged_items)}，疑似重复 {len(review_pairs)} 组", file=sys.stderr)
    return 1 if read_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
