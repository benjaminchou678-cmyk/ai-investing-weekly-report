#!/usr/bin/env python3
"""Shared endpoint helpers for source registry v3."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


ENDPOINT_TYPES = {
    "official_rss", "official_atom", "official_api", "official_html_list",
    "werss_api", "werss_rss", "rsshub", "wechat_article", "wechat_machine",
    "search", "manual",
}
ENDPOINT_STATUSES = {"stable", "candidate", "fallback", "unconfigured", "blocked", "inactive"}
PURPOSES = {"discovery", "evidence", "fallback_discovery"}
OFFICIALITY = {"official", "official_proxy", "third_party", "unknown"}


def valid_http_url(value: Any) -> bool:
    try:
        parsed = urlparse(str(value or ""))
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def endpoint_address_ready(endpoint: dict[str, Any]) -> bool:
    endpoint_type = endpoint.get("type")
    if endpoint_type == "manual":
        return bool(endpoint.get("instructions"))
    if endpoint_type == "search":
        return bool(endpoint.get("query_template"))
    if endpoint_type == "rsshub":
        return valid_http_url(endpoint.get("url")) or (
            valid_http_url(endpoint.get("base_url")) and bool(endpoint.get("route"))
        )
    if endpoint_type in {"werss_api", "werss_rss"}:
        return valid_http_url(endpoint.get("url")) and bool(
            endpoint.get("account_id") or endpoint.get("feed_id")
        )
    return valid_http_url(endpoint.get("url"))


def is_configured_endpoint(endpoint: dict[str, Any]) -> bool:
    return endpoint.get("status") in {"stable", "candidate", "fallback"} and endpoint_address_ready(endpoint)


def configured_endpoints(source: dict[str, Any]) -> list[dict[str, Any]]:
    endpoints = source.get("endpoints")
    if not isinstance(endpoints, list):
        return []
    return [endpoint for endpoint in endpoints if isinstance(endpoint, dict) and is_configured_endpoint(endpoint)]


def provider_group(endpoint: dict[str, Any]) -> str:
    return str(endpoint.get("provider_group") or endpoint.get("type") or "unknown")
