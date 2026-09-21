#!/usr/bin/env python3
"""Compare verified WeChat discoveries with a manually completed C1 benchmark."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def norm_title(value: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").casefold())


def key(item: dict[str, Any]) -> tuple[str, str]:
    url = str(item.get("canonical_url") or item.get("url") or "").split("#", 1)[0]
    return url, norm_title(item.get("title"))


def compare(truth: dict[str, Any], discovered: dict[str, Any]) -> dict[str, Any]:
    expected = truth.get("items", [])
    found = discovered.get("verified_in_window", discovered.get("items", []))
    if not isinstance(expected, list) or not isinstance(found, list):
        raise ValueError("ground truth and discovery items must be arrays")
    rows: list[dict[str, Any]] = []
    source_ids = sorted({str(item.get("source_id") or "") for item in expected})
    matched_total = 0
    for source_id in source_ids:
        source_expected = [item for item in expected if str(item.get("source_id") or "") == source_id]
        source_found = [item for item in found if str(item.get("source_id") or "") == source_id]
        found_urls = {key(item)[0] for item in source_found if key(item)[0]}
        found_titles = {key(item)[1] for item in source_found if key(item)[1]}
        matched = sum(1 for item in source_expected if key(item)[0] in found_urls or key(item)[1] in found_titles)
        matched_total += matched
        rows.append({"source_id": source_id, "ground_truth_items": len(source_expected),
                     "matched_items": matched, "recall": matched / len(source_expected) if source_expected else None})
    complete = bool(truth.get("complete_for_window"))
    return {
        "schema_version": "1.0",
        "metric_name": "recall" if complete else "discovery_coverage",
        "ground_truth_complete_for_window": complete,
        "ground_truth_items": len(expected),
        "matched_items": matched_total,
        "value": matched_total / len(expected) if expected else None,
        "per_source": rows,
        "warning": "" if complete else "基准集未声明完整，不得把该指标称为真实召回率",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ground-truth", required=True)
    parser.add_argument("--discovered", required=True)
    parser.add_argument("--output", "-o", required=True)
    args = parser.parse_args()
    try:
        truth = json.loads(Path(args.ground_truth).expanduser().read_text(encoding="utf-8"))
        discovered = json.loads(Path(args.discovered).expanduser().read_text(encoding="utf-8"))
        result = compare(truth, discovered)
        Path(args.output).expanduser().write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
