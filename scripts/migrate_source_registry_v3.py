#!/usr/bin/env python3
"""Migrate the v2 single-resolver registry to truthful v3 endpoint arrays."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from source_endpoints import endpoint_address_ready, valid_http_url


TYPE_MAP = {
    "rss": "official_rss",
    "rss_feed": "official_rss",
    "atom": "official_atom",
    "api": "official_api",
    "html_list": "official_html_list",
    "werss": "werss_api",
    "werss_api": "werss_api",
    "wechat": "wechat_machine",
    "wechat_machine": "wechat_machine",
    "search": "search",
    "manual_only": "manual",
    "unknown": "manual",
}


def slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return text or "endpoint"


def infer_type(raw_type: str, url: str) -> str:
    lowered = url.lower()
    if raw_type in {"rss", "rss_feed"} and lowered.split("?", 1)[0].endswith(".json"):
        return "official_api"
    if raw_type == "unknown" and valid_http_url(url):
        return "official_html_list"
    if raw_type in {"wechat", "wechat_machine"} and valid_http_url(url):
        if any(token in lowered for token in ("/rss", "/feed", ".xml")):
            return "official_rss"
        return "official_html_list"
    return TYPE_MAP.get(raw_type, "manual")


def provider_for(endpoint_type: str, officiality: str) -> str:
    if endpoint_type.startswith("werss"):
        return "werss"
    if endpoint_type == "rsshub":
        return "rsshub"
    if endpoint_type in {"search", "manual"}:
        return endpoint_type
    if officiality == "official":
        return "official"
    if endpoint_type == "wechat_machine":
        return "wechat-platform"
    return "web"


def convert_endpoint(source_id: str, raw: dict[str, Any], index: int) -> dict[str, Any]:
    raw_type = str(raw.get("type") or "manual_only")
    url = str(raw.get("url") or "").strip()
    if url.lower() == "none":
        url = ""
    endpoint_type = infer_type(raw_type, url)
    officiality = str(raw.get("officiality") or "unknown")
    if officiality not in {"official", "official_proxy", "third_party", "unknown"}:
        officiality = "unknown"
    purpose = ["discovery", "evidence"] if officiality == "official" else ["discovery"]
    if endpoint_type in {"search", "manual"}:
        purpose = ["fallback_discovery"]
    endpoint = {
        "endpoint_id": f"{source_id}-{slug(endpoint_type)}-{index}",
        "type": endpoint_type,
        "status": "unconfigured",
        "purpose": purpose,
        "officiality": officiality,
        "provider_group": provider_for(endpoint_type, officiality),
        "url": url,
        "base_url": "",
        "route": "",
        "account_id": "",
        "feed_id": "",
        "auth_required": bool(raw.get("auth_required")),
        "credential_ref": "",
        "browser_required": bool(raw.get("browser_required")),
        "date_filterable": bool(raw.get("date_filterable")),
        "list_enumerable": bool(raw.get("list_enumerable")),
        "content_scope": str(raw.get("content_scope") or "metadata"),
        "last_verified_at": str(raw.get("last_checked_at") or ""),
        "limitations": str(raw.get("limitations") or ""),
    }
    old_status = str(raw.get("status") or "")
    if endpoint_address_ready(endpoint):
        endpoint["status"] = "stable" if old_status in {"stable", "stable_fallback"} else "candidate"
    elif not endpoint["limitations"]:
        endpoint["limitations"] = "入口地址或账号标识尚未配置"
    return endpoint


def migrate(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") == "3.0":
        return payload
    if payload.get("schema_version") != "2.0":
        raise ValueError("只支持 source registry 2.0 → 3.0")
    result = dict(payload)
    result["schema_version"] = "3.0"
    result["endpoint_policy_version"] = "1.0"
    migrated_sources = []
    for original in payload.get("sources", []):
        source = dict(original)
        resolver = source.pop("resolver", {}) if isinstance(source.get("resolver"), dict) else {}
        raw_endpoints = []
        primary = resolver.get("primary")
        if isinstance(primary, dict):
            raw_endpoints.append(primary)
        raw_endpoints.extend(x for x in resolver.get("fallbacks", []) if isinstance(x, dict))
        endpoints = [convert_endpoint(str(source.get("source_id")), raw, i + 1) for i, raw in enumerate(raw_endpoints)]
        top_url = str(source.get("url") or "").strip()
        if top_url.lower() == "none":
            top_url = ""
        if valid_http_url(top_url) and all(x.get("url") != top_url for x in endpoints):
            endpoints.append(convert_endpoint(str(source.get("source_id")), {
                "type": "rss" if any(token in top_url.lower() for token in ("/rss", "/feed", ".xml")) else "html_list",
                "url": top_url,
                "officiality": "official" if source.get("operator_verified") else "unknown",
                "status": "candidate_retest",
                "limitations": "由旧版顶层 URL 迁移，需完成实际访问核验",
            }, len(endpoints) + 1))
        if not endpoints:
            endpoints.append(convert_endpoint(str(source.get("source_id")), {}, 1))
        for endpoint in endpoints:
            if endpoint["status"] == "stable" and not endpoint["last_verified_at"]:
                endpoint["last_verified_at"] = str(source.get("last_verified_at") or "")
        source["endpoints"] = endpoints
        source["channel"] = source.get("channel")  # v3 保留为发布主体的旧分类，不再用于路由。
        migrated_sources.append(source)
    result["sources"] = migrated_sources
    return result


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry")
    parser.add_argument("--output", "-o", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    migrated = migrate(payload)
    atomic_write(Path(args.output), migrated)
    print(f"source registry v3: {len(migrated.get('sources', []))} sources -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
