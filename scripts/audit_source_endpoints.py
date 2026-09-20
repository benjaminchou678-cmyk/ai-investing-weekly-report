#!/usr/bin/env python3
"""Create JSON/CSV endpoint audit for the 15 base sources and WeChat C1 cohort."""

from __future__ import annotations

import argparse
import csv
import json
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from source_endpoints import configured_endpoints, endpoint_address_ready


def probe(url: str, timeout: int) -> dict[str, Any]:
    if not url:
        return {"result": "unconfigured", "http_status": None, "final_url": "", "content_type": "", "error": ""}
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 AIInvestingWeeklyReport/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            response.read(2048)
            return {
                "result": "reachable", "http_status": response.status,
                "final_url": response.geturl(), "content_type": response.headers.get_content_type(), "error": "",
            }
    except HTTPError as exc:
        return {"result": "http_error", "http_status": exc.code, "final_url": exc.geturl(), "content_type": "", "error": str(exc.reason)}
    except (URLError, TimeoutError, socket.timeout, ValueError) as exc:
        return {"result": "network_error", "http_status": None, "final_url": "", "content_type": "", "error": str(exc)[:240]}


def cohort(source: dict[str, Any]) -> str:
    if source.get("channel") != "wechat_official_account":
        return "base_15"
    if source.get("priority") == "C1":
        return "wechat_c1_29"
    return "out_of_scope"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--csv-output", required=True)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--timeout", type=int, default=15)
    args = parser.parse_args()
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    pilot_ids = set(plan["pilot"]["source_ids"])
    checked_at = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    for source in registry.get("sources", []):
        group = cohort(source)
        if group == "out_of_scope":
            continue
        endpoints = source.get("endpoints", [])
        for endpoint in endpoints:
            address_ready = endpoint_address_ready(endpoint)
            result = probe(str(endpoint.get("url") or ""), args.timeout) if args.probe and address_ready else {
                "result": "not_probed" if address_ready else "unconfigured", "http_status": None,
                "final_url": "", "content_type": "", "error": "",
            }
            rows.append({
                "source_id": source.get("source_id"), "source_name": source.get("name"), "cohort": group,
                "priority": source.get("priority"), "source_status": source.get("status"),
                "operator_verified": bool(source.get("operator_verified")),
                "endpoint_id": endpoint.get("endpoint_id"), "endpoint_type": endpoint.get("type"),
                "endpoint_status": endpoint.get("status"), "officiality": endpoint.get("officiality"),
                "provider_group": endpoint.get("provider_group"), "url": endpoint.get("url", ""),
                "address_ready": address_ready, "selected_for_pilot": source.get("source_id") in pilot_ids,
                "date_filterable": bool(endpoint.get("date_filterable")),
                "list_enumerable": bool(endpoint.get("list_enumerable")),
                "limitations": endpoint.get("limitations", ""), "checked_at": checked_at if args.probe else "",
                **result,
            })
    expected = {"base_15": 15, "wechat_c1_29": 29}
    source_counts = {key: len({r["source_id"] for r in rows if r["cohort"] == key}) for key in expected}
    summary = {
        "source_counts": source_counts,
        "expected_source_counts": expected,
        "endpoint_rows": len(rows),
        "configured_sources": len({r["source_id"] for r in rows if r["address_ready"] and r["endpoint_status"] in {"stable", "candidate", "fallback"}}),
        "reachable_sources": len({r["source_id"] for r in rows if r["result"] == "reachable"}),
        "operator_verified_sources": len({r["source_id"] for r in rows if r["operator_verified"]}),
        "pilot_sources": len(pilot_ids),
    }
    payload = {"schema_version": "1.0", "generated_at": checked_at, "probe_enabled": args.probe, "summary": summary, "rows": rows}
    json_path, csv_path = Path(args.json_output), Path(args.csv_output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        writer.writeheader()
        writer.writerows(rows)
    if source_counts != expected:
        raise SystemExit(f"audit cohort mismatch: {source_counts} != {expected}")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
