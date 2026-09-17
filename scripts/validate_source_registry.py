#!/usr/bin/env python3
"""Validate source-registry.json without accessing the network."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

CHANNELS = {"web", "feed", "wechat_official_account", "social", "database"}
PRIORITIES = {"C1", "C2", "C3"}
FREQUENCIES = {"weekly", "biweekly", "monthly", "event_driven"}
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
    "independence_group", "access", "status", "last_verified_at", "evidence_limit",
}


def issue(severity: str, code: str, message: str, source_id: str = "") -> dict[str, str]:
    result = {"severity": severity, "code": code, "message": message}
    if source_id:
        result["source_id"] = source_id
    return result


def validate(payload: Any) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if not isinstance(payload, dict) or payload.get("schema_version") != "2.0":
        return [issue("FAIL", "SCHEMA_VERSION", "source registry 必须使用 schema_version 2.0")]
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        return [issue("FAIL", "SOURCES_EMPTY", "sources 必须是非空数组")]

    seen: set[str] = set()
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
        elif source_id in seen:
            issues.append(issue("FAIL", "SOURCE_ID_DUPLICATE", "source_id 重复", source_id))
        seen.add(source_id)

        for field, allowed in (("channel", CHANNELS), ("priority", PRIORITIES),
                               ("check_frequency", FREQUENCIES), ("status", STATUSES),
                               ("role", ROLES)):
            if source.get(field) not in allowed:
                issues.append(issue("FAIL", f"INVALID_{field.upper()}", f"{field} 值不合法: {source.get(field)!r}", source_id))
        dimensions = source.get("coverage_dimensions")
        if not isinstance(dimensions, list) or not dimensions:
            issues.append(issue("FAIL", "DIMENSIONS_EMPTY", "coverage_dimensions 必须是非空数组", source_id))
        else:
            unknown = sorted(set(map(str, dimensions)) - DIMENSIONS)
            if unknown:
                issues.append(issue("FAIL", "DIMENSIONS_UNKNOWN", f"未知维度: {', '.join(unknown)}", source_id))
        access = source.get("access")
        if not isinstance(access, dict) or not access.get("mode") or not isinstance(access.get("paywall"), bool):
            issues.append(issue("FAIL", "ACCESS_INVALID", "access 必须包含 mode 和布尔型 paywall", source_id))
        if not source.get("parent_group") or not source.get("independence_group"):
            issues.append(issue("FAIL", "GROUP_EMPTY", "parent_group 与 independence_group 不能为空", source_id))
        verified_at = str(source.get("last_verified_at") or "")
        if verified_at:
            try:
                date.fromisoformat(verified_at)
            except ValueError:
                issues.append(issue("FAIL", "VERIFIED_DATE_INVALID", "last_verified_at 必须为 YYYY-MM-DD 或空字符串", source_id))
        if source.get("hard_required"):
            if source.get("status") != "active" or not source.get("operator_verified"):
                issues.append(issue("FAIL", "HARD_SOURCE_UNVERIFIED", "硬性来源必须 active 且运营主体已核验", source_id))
            if source.get("channel") == "wechat_official_account":
                if not source.get("wechat_id"):
                    issues.append(issue("FAIL", "HARD_WECHAT_ID_EMPTY", "微信硬性来源必须填写 wechat_id", source_id))
                if not source.get("fallback_url"):
                    issues.append(issue("FAIL", "HARD_WECHAT_FALLBACK_EMPTY", "微信硬性来源必须配置 fallback_url", source_id))
        if source.get("status") == "unverified":
            issues.append(issue("WARN", "SOURCE_UNVERIFIED", "来源尚未完成人工核验，不可作为硬门或独立确认", source_id))
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
    report = {"schema_version": "1.0", "status": status, "source_count": len(payload.get("sources", [])), "issues": issues}
    if args.output:
        Path(args.output).expanduser().write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"来源注册表校验: {status} ({len(issues)} issues)", file=sys.stderr)
    return 1 if status == "FAIL" or (args.strict and status == "WARN") else 0


if __name__ == "__main__":
    raise SystemExit(main())
