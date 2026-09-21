#!/usr/bin/env python3
"""Add identity and discovery-state fields to every WeChat source."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def enrich(payload: dict[str, Any]) -> dict[str, Any]:
    for source in payload.get("sources", []):
        if source.get("channel") != "wechat_official_account":
            continue
        source.setdefault("aliases", [])
        source.setdefault("wechat_id", "")
        source.setdefault("wechat_biz_ids", [])
        domains: list[str] = list(source.get("official_domains") or [])
        for endpoint in source.get("endpoints", []):
            if endpoint.get("officiality") not in {"official", "official_proxy"}:
                continue
            try:
                hostname = urlparse(str(endpoint.get("url") or "")).hostname or ""
            except ValueError:
                hostname = ""
            if hostname and hostname not in domains:
                domains.append(hostname)
        source["official_domains"] = domains
        source.setdefault("identity_status", "unverified")
        source.setdefault("identity_last_verified_at", "")
        source.setdefault("discovery_state", {
            "last_seen_published_at": "", "last_seen_title": "", "last_seen_url": "",
        })
    payload["wechat_identity_policy_version"] = "1.0"
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry")
    parser.add_argument("--output", "-o", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.registry).expanduser().read_text(encoding="utf-8"))
    Path(args.output).expanduser().write_text(
        json.dumps(enrich(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
