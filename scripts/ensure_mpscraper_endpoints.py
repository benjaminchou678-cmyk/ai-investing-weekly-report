#!/usr/bin/env python3
"""Add truthful mpScraper placeholders and demote WeChat feed endpoints to fallback."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


FEED_TYPES = {"official_rss", "official_atom", "werss_api", "werss_rss", "rsshub"}


def mpscraper_endpoint(source: dict[str, Any]) -> dict[str, Any]:
    source_id = str(source.get("source_id") or "wechat")
    return {
        "endpoint_id": f"{source_id}-mpscraper-mcp-1",
        "type": "mpscraper_mcp",
        "status": "unconfigured",
        "purpose": ["discovery"],
        "officiality": "third_party",
        "provider_group": "mpscraper-local",
        "url": "http://127.0.0.1:8082/mcp",
        "account_name": str(source.get("name") or ""),
        "auth_required": False,
        "credential_ref": "",
        "browser_required": True,
        "date_filterable": True,
        "list_enumerable": True,
        "content_scope": "metadata",
        "last_verified_at": "",
        "limitations": (
            "需在本地完成微信/mpScraper鉴权并确认账号心跳可用；运行时通过MCP查询后导出JSON快照。"
            "未完成两轮时间窗完整性验证前不得改为stable。"
        ),
    }


def update(payload: dict[str, Any]) -> dict[str, Any]:
    for source in payload.get("sources", []):
        if source.get("channel") != "wechat_official_account":
            continue
        endpoints = source.get("endpoints") if isinstance(source.get("endpoints"), list) else []
        retained = []
        existing_mp = None
        for endpoint in endpoints:
            if not isinstance(endpoint, dict):
                retained.append(endpoint)
                continue
            if endpoint.get("type") == "mpscraper_mcp":
                existing_mp = endpoint
                continue
            if endpoint.get("type") == "wechat_machine":
                # v3 的泛型占位改成可执行语义明确的 mpScraper 占位。
                continue
            if endpoint.get("type") in FEED_TYPES:
                if endpoint.get("status") in {"stable", "candidate"}:
                    endpoint["status"] = "fallback"
                endpoint["purpose"] = ["fallback_discovery"]
            retained.append(endpoint)

        mp = existing_mp or mpscraper_endpoint(source)
        official_end = 0
        for index, endpoint in enumerate(retained):
            if isinstance(endpoint, dict) and endpoint.get("type") in {"official_api", "official_html_list"}:
                official_end = index + 1
        retained.insert(official_end, mp)
        source["endpoints"] = retained
    payload["endpoint_policy_version"] = "1.1"
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    result = update(payload)
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
