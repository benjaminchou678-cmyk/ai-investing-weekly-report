#!/usr/bin/env python3
"""Compare two endpoint collection runs and compute coverage plus recall when ground truth exists."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def item_key(item: dict[str, Any]) -> str:
    return str(item.get("canonical_url") or item.get("original_url") or item.get("url") or item.get("id") or "").strip()


def summarize(candidates: dict[str, Any], coverage: dict[str, Any]) -> dict[str, Any]:
    records = coverage.get("sources", [])
    scheduled = [row for row in records if row.get("scheduled")]
    attempts = [a for row in scheduled for a in row.get("endpoint_attempts", [])]
    items = [item for item in candidates.get("items", []) if isinstance(item, dict)]
    return {
        "scheduled_sources": len(scheduled),
        "attempted_sources": sum(bool(row.get("endpoint_attempts")) for row in scheduled),
        "successful_sources": sum(row.get("status") in {"ok", "no_update"} for row in scheduled),
        "sources_with_items": len({item.get("source_id") for item in items}),
        "candidate_items": len(items),
        "dated_candidate_items": sum(item.get("date_status") == "in_window" for item in items),
        "undated_candidate_items": sum(item.get("date_status") == "unknown" for item in items),
        "successful_attempts": sum(a.get("status") == "ok" for a in attempts),
        "total_attempts": len(attempts),
    }


def recall(candidates: dict[str, Any], truth: dict[str, Any], window: str) -> dict[str, Any]:
    expected = {item_key(item) for item in truth.get("items", []) if item.get("window") == window and item_key(item)}
    found = {item_key(item) for item in candidates.get("items", []) if item_key(item)}
    matched = expected & found
    return {
        "ground_truth_items": len(expected), "matched_items": len(matched),
        "recall": round(len(matched) / len(expected), 4) if expected else None,
        "status": "measured" if expected else "not_measurable_without_ground_truth",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--week-a-candidates", required=True)
    parser.add_argument("--week-a-coverage", required=True)
    parser.add_argument("--week-b-candidates", required=True)
    parser.add_argument("--week-b-coverage", required=True)
    parser.add_argument("--ground-truth")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    a_candidates, b_candidates = load(args.week_a_candidates), load(args.week_b_candidates)
    a_coverage, b_coverage = load(args.week_a_coverage), load(args.week_b_coverage)
    truth = load(args.ground_truth) if args.ground_truth else {"items": []}
    label_a = f"{a_coverage.get('week_start')}_to_{a_coverage.get('week_end')}"
    label_b = f"{b_coverage.get('week_start')}_to_{b_coverage.get('week_end')}"
    result = {
        "schema_version": "1.0",
        "metric_note": "无人工基准集时只报告发现覆盖率，不将候选数量或来源命中率冒充召回率。",
        "week_a": {"window": label_a, **summarize(a_candidates, a_coverage), "recall": recall(a_candidates, truth, label_a)},
        "week_b": {"window": label_b, **summarize(b_candidates, b_coverage), "recall": recall(b_candidates, truth, label_b)},
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
