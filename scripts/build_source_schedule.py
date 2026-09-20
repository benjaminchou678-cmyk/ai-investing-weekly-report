#!/usr/bin/env python3
"""Materialize pilot, weekly C2 and event-driven C3 schedules from registry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from source_endpoints import configured_endpoints


def row(source: dict) -> dict:
    return {
        "source_id": source["source_id"], "name": source["name"], "priority": source["priority"],
        "mode": "event_driven" if source["priority"] == "C3" else "weekly_lightweight",
        "configured_endpoint_ids": [e["endpoint_id"] for e in configured_endpoints(source)],
        "runnable": bool(configured_endpoints(source)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    sources = registry["sources"]
    by_id = {s["source_id"]: s for s in sources}
    pilot = [row(by_id[sid]) for sid in plan["pilot"]["source_ids"]]
    c2 = [row(s) for s in sources if s.get("channel") == "wechat_official_account" and s.get("priority") == "C2"]
    c3 = [row(s) for s in sources if s.get("channel") == "wechat_official_account" and s.get("priority") == "C3"]
    if len(c2) != plan["c2_scan"]["expected_count"] or len(c3) != plan["c3"]["expected_count"]:
        raise SystemExit(f"cohort count mismatch: C2={len(c2)}, C3={len(c3)}")
    payload = {
        "schema_version": "1.0", "as_of": plan["as_of"],
        "pilot": pilot, "c2_weekly": c2, "c3_event_driven": c3,
        "summary": {
            "pilot": len(pilot), "pilot_runnable": sum(x["runnable"] for x in pilot),
            "c2": len(c2), "c2_runnable": sum(x["runnable"] for x in c2),
            "c3": len(c3), "c3_runnable": sum(x["runnable"] for x in c3),
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
