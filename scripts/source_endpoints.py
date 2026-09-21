#!/usr/bin/env python3
"""Shared endpoint helpers for source registry v3."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


ENDPOINT_TYPES = {
    "official_rss", "official_atom", "official_api", "official_html_list",
    "werss_api", "werss_rss", "rsshub",
    "wechat_article", "wechat_machine",
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


def endpoint_priority(endpoint: dict[str, Any], channel: str = "") -> int:
    """Return resolver order; lower values run first.

    微信来源优先官网，其次是多查询搜索。RSS/WeRSS/RSSHub 仅作备用。
    wechat_article 属于拿到 URL 后的正文增强步骤，不参与列表发现排序。
    非微信来源仍优先官方结构化入口，不受微信反爬策略影响。
    """
    endpoint_type = str(endpoint.get("type") or "")
    if channel == "wechat_official_account":
        order = {
            "official_api": 10,
            "official_html_list": 20,
            "search": 30,
            "official_rss": 50,
            "official_atom": 50,
            "werss_api": 60,
            "werss_rss": 60,
            "rsshub": 70,
            "manual": 90,
            "wechat_article": 95,
            "wechat_machine": 95,
        }
    else:
        order = {
            "official_api": 10,
            "official_rss": 20,
            "official_atom": 20,
            "official_html_list": 30,
            "werss_api": 50,
            "werss_rss": 50,
            "rsshub": 60,
            "search": 70,
            "manual": 80,
            "wechat_article": 90,
            "wechat_machine": 95,
        }
    return order.get(endpoint_type, 999)


def configured_endpoints(source: dict[str, Any]) -> list[dict[str, Any]]:
    endpoints = source.get("endpoints")
    if not isinstance(endpoints, list):
        return []
    configured = [
        endpoint for endpoint in endpoints
        if isinstance(endpoint, dict) and is_configured_endpoint(endpoint)
    ]
    return sorted(configured, key=lambda endpoint: endpoint_priority(endpoint, str(source.get("channel") or "")))


def provider_group(endpoint: dict[str, Any]) -> str:
    return str(endpoint.get("provider_group") or endpoint.get("type") or "unknown")
