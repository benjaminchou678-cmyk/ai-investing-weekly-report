#!/usr/bin/env python3
"""Validate source-registry v3 without accessing the network."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from source_endpoints import (
    ENDPOINT_STATUSES, ENDPOINT_TYPES, OFFICIALITY, PURPOSES,
    configured_endpoints, endpoint_address_ready,
)

CHANNELS = {"web", "feed", "wechat_official_account", "social", "database"}
PRIORITIES = {"C1", "C2", "C3"}
FREQUENCIES = {"weekly", "event_driven"}
STATUSES = {"active", "unverified", "inactive", "blocked"}
ROLES = {
    "primary_company", "primary_regulatory", "investor_stakeholder",
    "independent_media", "industry_media", "research_primary", "market_context",
    "builder", "aggregator", "customer_proxy", "counter_evidence", "talent_signal",
}
DIMENSIONS = {
    "company_primary", "capital", "policy", "infrastructure", "customer_demand",
    "counter_evidence", "product_distribution", "research", "talent", "global_context",
}
REQUIRED_FIELDS = {
    "source_id", "name", "channel", "operator", "operator_verified", "role", "priority",
    "hard_required", "check_frequency", "coverage_dimensions", "parent_group",
    "independence_group", "access", "status", "last_verified_at", "evidence_limit", "endpoints",
}
ENDPOINT_REQUIRED = {
    "endpoint_id", "type", "status", "purpose", "officiality", "provider_group",
    "auth_required", "credential_ref", "browser_required", "date_filterable",
    "list_enumerable", "content_scope", "last_verified_at", "limitations",
}
WECHAT_IDENTITY_STATUSES = {"verified", "inferred", "unverified", "conflict"}
WECHAT_IDENTITY_FIELDS = {
    "aliases", "wechat_id", "wechat_biz_ids", "official_domains",
    "identity_status", "identity_last_verified_at", "discovery_state",
}


def issue(severity: str, code: str, message: str, source_id: str = "", endpoint_id: str = "") -> dict[str, str]:
    result = {"severity": severity, "code": code, "message": message}
    if source_id:
        result["source_id"] = source_id
    if endpoint_id:
        result["endpoint_id"] = endpoint_id
    return result


def validate(payload: Any) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if not isinstance(payload, dict) or payload.get("schema_version") != "3.0":
        return [issue("FAIL", "SCHEMA_VERSION", "source registry 必须使用 schema_version 3.0")]
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        return [issue("FAIL", "SOURCES_EMPTY", "sources 必须是非空数组")]

    seen_sources: set[str] = set()
    seen_endpoints: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            issues.append(issue("FAIL", "SOURCE_TYPE", f"sources[{index}] 不是对象"))
            continue
        source_id = str(source.get("source_id") or "")
        missing = sorted(REQUIRED_FIELDS - source.keys())
        if missing:
            issues.append(issue("FAIL", "MISSING_FIELDS", f"缺少字段: {', '.join(missing)}", source_id))
        if not source_id:
            issues.append(issue("FAIL", "SOURCE_ID_EMPTY", "source_id 不能为空"))
        elif source_id in seen_sources:
            issues.append(issue("FAIL", "SOURCE_ID_DUPLICATE", "source_id 重复", source_id))
        seen_sources.add(source_id)
        for field, allowed in (("channel", CHANNELS), ("priority", PRIORITIES),
                               ("check_frequency", FREQUENCIES), ("status", STATUSES), ("role", ROLES)):
            if source.get(field) not in allowed:
                issues.append(issue("FAIL", f"INVALID_{field.upper()}", f"{field} 值不合法: {source.get(field)!r}", source_id))
        if source.get("priority") in {"C1", "C2"} and source.get("check_frequency") != "weekly":
            issues.append(issue("FAIL", "FREQ_MISMATCH", "C1/C2 必须 weekly", source_id))
        if source.get("priority") == "C3" and source.get("check_frequency") != "event_driven":
            issues.append(issue("FAIL", "FREQ_MISMATCH", "C3 必须 event_driven", source_id))
        dimensions = source.get("coverage_dimensions")
        if not isinstance(dimensions, list) or not dimensions:
            issues.append(issue("FAIL", "DIMENSIONS_EMPTY", "coverage_dimensions 必须是非空数组", source_id))
        else:
            unknown = sorted(set(map(str, dimensions)) - DIMENSIONS)
            if unknown:
                issues.append(issue("FAIL", "DIMENSIONS_UNKNOWN", f"未知维度: {', '.join(unknown)}", source_id))
        if not source.get("parent_group") or not source.get("independence_group"):
            issues.append(issue("FAIL", "GROUP_EMPTY", "parent_group 与 independence_group 不能为空", source_id))
        access = source.get("access")
        if not isinstance(access, dict) or not access.get("mode") or not isinstance(access.get("paywall"), bool):
            issues.append(issue("FAIL", "ACCESS_INVALID", "access 必须包含 mode 和布尔型 paywall", source_id))
        value = str(source.get("last_verified_at") or "")
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                issues.append(issue("FAIL", "VERIFIED_DATE_INVALID", "last_verified_at 必须为 YYYY-MM-DD 或空字符串", source_id))

        if source.get("channel") == "wechat_official_account":
            missing_identity = sorted(WECHAT_IDENTITY_FIELDS - source.keys())
            if missing_identity:
                issues.append(issue("FAIL", "WECHAT_IDENTITY_FIELDS_MISSING",
                                    f"微信来源缺少身份字段: {', '.join(missing_identity)}", source_id))
            if not isinstance(source.get("aliases"), list) or not isinstance(source.get("wechat_biz_ids"), list):
                issues.append(issue("FAIL", "WECHAT_IDENTITY_ARRAY_INVALID",
                                    "aliases 与 wechat_biz_ids 必须是数组", source_id))
            if not isinstance(source.get("official_domains"), list):
                issues.append(issue("FAIL", "WECHAT_DOMAINS_INVALID", "official_domains 必须是数组", source_id))
            if source.get("identity_status") not in WECHAT_IDENTITY_STATUSES:
                issues.append(issue("FAIL", "WECHAT_IDENTITY_STATUS_INVALID", "identity_status 不合法", source_id))
            identity_date = str(source.get("identity_last_verified_at") or "")
            if identity_date:
                try:
                    date.fromisoformat(identity_date)
                except ValueError:
                    issues.append(issue("FAIL", "WECHAT_IDENTITY_DATE_INVALID",
                                        "identity_last_verified_at 必须为 YYYY-MM-DD 或空字符串", source_id))
            state = source.get("discovery_state")
            state_fields = {"last_seen_published_at", "last_seen_title", "last_seen_url"}
            if not isinstance(state, dict) or not state_fields.issubset(state):
                issues.append(issue("FAIL", "WECHAT_DISCOVERY_STATE_INVALID",
                                    "discovery_state 缺少 last_seen_* 字段", source_id))

        endpoints = source.get("endpoints")
        if not isinstance(endpoints, list) or not endpoints:
            issues.append(issue("FAIL", "ENDPOINTS_EMPTY", "endpoints 必须是非空数组", source_id))
            endpoints = []
        for endpoint in endpoints:
            if not isinstance(endpoint, dict):
                issues.append(issue("FAIL", "ENDPOINT_OBJECT_INVALID", "endpoint 必须是对象", source_id))
                continue
            endpoint_id = str(endpoint.get("endpoint_id") or "")
            missing_endpoint = sorted(ENDPOINT_REQUIRED - endpoint.keys())
            if missing_endpoint:
                issues.append(issue("FAIL", "ENDPOINT_FIELDS_MISSING", f"endpoint 缺少字段: {', '.join(missing_endpoint)}", source_id, endpoint_id))
            if not endpoint_id or endpoint_id in seen_endpoints:
                issues.append(issue("FAIL", "ENDPOINT_ID_INVALID", "endpoint_id 为空或全局重复", source_id, endpoint_id))
            seen_endpoints.add(endpoint_id)
            if endpoint.get("type") not in ENDPOINT_TYPES:
                issues.append(issue("FAIL", "ENDPOINT_TYPE_INVALID", f"非法 endpoint type: {endpoint.get('type')}", source_id, endpoint_id))
            if endpoint.get("status") not in ENDPOINT_STATUSES:
                issues.append(issue("FAIL", "ENDPOINT_STATUS_INVALID", f"非法 endpoint status: {endpoint.get('status')}", source_id, endpoint_id))
            purpose = endpoint.get("purpose")
            if not isinstance(purpose, list) or not purpose or set(purpose) - PURPOSES:
                issues.append(issue("FAIL", "ENDPOINT_PURPOSE_INVALID", "purpose 必须是合法的非空数组", source_id, endpoint_id))
            if endpoint.get("officiality") not in OFFICIALITY:
                issues.append(issue("FAIL", "ENDPOINT_OFFICIALITY_INVALID", "officiality 不合法", source_id, endpoint_id))
            if not endpoint.get("provider_group"):
                issues.append(issue("FAIL", "ENDPOINT_PROVIDER_EMPTY", "provider_group 不能为空", source_id, endpoint_id))
            if endpoint.get("status") in {"stable", "candidate", "fallback"} and not endpoint_address_ready(endpoint):
                issues.append(issue("FAIL", "ENDPOINT_ADDRESS_MISSING", "可用 endpoint 缺少 URL、route 或账号标识", source_id, endpoint_id))
            if endpoint.get("status") == "stable" and not endpoint.get("last_verified_at"):
                issues.append(issue("FAIL", "STABLE_ENDPOINT_UNVERIFIED", "stable endpoint 必须填写 last_verified_at", source_id, endpoint_id))
            if endpoint.get("auth_required") and not endpoint.get("credential_ref"):
                issues.append(issue("FAIL", "ENDPOINT_CREDENTIAL_REF_MISSING", "需要认证的 endpoint 必须使用 credential_ref", source_id, endpoint_id))
        if source.get("hard_required") and not configured_endpoints(source):
            issues.append(issue("FAIL", "HARD_SOURCE_NO_ENDPOINT", "硬性来源至少需要一个可用 endpoint", source_id))
        if source.get("hard_required") and (source.get("status") != "active" or not source.get("operator_verified")):
            issues.append(issue("FAIL", "HARD_SOURCE_UNVERIFIED", "硬性来源必须 active 且运营主体已核验", source_id))
        if source.get("status") == "unverified":
            issues.append(issue("WARN", "SOURCE_UNVERIFIED", "来源主体尚未完成核验，不可作为独立确认", source_id))
        if source.get("priority") == "C1" and not configured_endpoints(source):
            issues.append(issue("WARN", "C1_ENDPOINT_UNCONFIGURED", "C1 来源尚无可执行 endpoint", source_id))
        valid_tracks = {"company_regulatory", "media_business_verification", "builder_technical", "capital_market"}
        if source.get("primary_track") is not None and source.get("primary_track") not in valid_tracks:
            issues.append(issue("FAIL", "TRACK_INVALID", f"primary_track 不合法: {source.get('primary_track')}", source_id))
    if not isinstance(payload.get("aliases", {}), dict):
        issues.append(issue("FAIL", "ALIASES_TYPE", "aliases 必须为对象"))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry")
    parser.add_argument("--output", "-o")
    parser.add_argument("--strict", action="store_true", help="WARN 也返回非零")
    args = parser.parse_args()
    try:
        payload = json.loads(Path(args.registry).expanduser().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    issues = validate(payload)
    status = "FAIL" if any(x["severity"] == "FAIL" for x in issues) else "WARN" if issues else "PASS"
    report = {"schema_version": "2.0", "status": status, "source_count": len(payload.get("sources", [])), "issues": issues}
    if args.output:
        Path(args.output).expanduser().write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"来源注册表校验: {status} ({len(issues)} issues)", file=sys.stderr)
    return 1 if status == "FAIL" or (args.strict and status == "WARN") else 0


if __name__ == "__main__":
    raise SystemExit(main())
