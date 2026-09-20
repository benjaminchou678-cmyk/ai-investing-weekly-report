#!/usr/bin/env python3
"""Apply reviewed endpoint candidates to source-registry v3 without duplicating URLs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from migrate_source_registry_v3 import atomic_write


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--overrides", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    overrides = json.loads(Path(args.overrides).read_text(encoding="utf-8")).get("sources", {})
    changed = 0
    for source in registry.get("sources", []):
        source_id = source.get("source_id")
        override = overrides.get(source_id)
        if not isinstance(override, dict):
            continue
        endpoints = source.setdefault("endpoints", [])
        if any(endpoint.get("url") == override.get("url") for endpoint in endpoints):
            continue
        managed = next((endpoint for endpoint in endpoints
                        if endpoint.get("provider_group") == override.get("provider_group")
                        and endpoint.get("status") == "candidate"
                        and not endpoint.get("last_verified_at")), None)
        if managed:
            managed.update({
                "type": override["type"], "url": override.get("url", ""),
                "officiality": override.get("officiality", "unknown"),
                "provider_group": override.get("provider_group", "web"),
                "purpose": ["discovery", "evidence"] if override.get("officiality") == "official" else ["discovery"],
                "limitations": override.get("limitations", "候选入口，待连续运行核验"),
            })
            changed += 1
            continue
        endpoint_type = override["type"]
        endpoints.append({
            "endpoint_id": f"{source_id}-{endpoint_type.replace('_', '-')}-{len(endpoints) + 1}",
            "type": endpoint_type,
            "status": "candidate",
            "purpose": ["discovery", "evidence"] if override.get("officiality") == "official" else ["discovery"],
            "officiality": override.get("officiality", "unknown"),
            "provider_group": override.get("provider_group", "web"),
            "url": override.get("url", ""),
            "base_url": "", "route": "", "account_id": "", "feed_id": "",
            "auth_required": False, "credential_ref": "", "browser_required": False,
            "date_filterable": False, "list_enumerable": False,
            "content_scope": "metadata", "last_verified_at": "",
            "limitations": override.get("limitations", "候选入口，待连续运行核验"),
        })
        changed += 1
    atomic_write(Path(args.output), registry)
    print(f"applied endpoint overrides: {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
