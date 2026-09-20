#!/usr/bin/env python3
"""Audit source and endpoint coverage against registry v3 and policy."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from source_endpoints import configured_endpoints
from validate_source_registry import validate

SUCCESS = {"ok", "no_update"}
STATUSES = SUCCESS | {"failed", "blocked", "stale", "not_scheduled"}


def load(path: str) -> Any:
    return json.loads(Path(path).expanduser().read_text(encoding="utf-8"))


def add_issue(issues: list[dict[str, Any]], severity: str, code: str, message: str, **details: Any) -> None:
    issues.append({"severity": severity, "code": code, "message": message, **details})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--coverage", required=True)
    parser.add_argument("--profile", default="")
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--output", "-o", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    try:
        registry, policy, coverage = load(args.registry), load(args.policy), load(args.coverage)
        as_of = date.fromisoformat(args.as_of)
        profile_name = args.profile or coverage.get("profile") or policy.get("default_profile")
        profile = policy["profiles"][profile_name]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    issues: list[dict[str, Any]] = []
    for entry in validate(registry):
        if entry["severity"] == "FAIL":
            add_issue(issues, "FAIL", "REGISTRY_INVALID", entry["message"], source_id=entry.get("source_id", ""))
    sources = {s["source_id"]: s for s in registry.get("sources", []) if isinstance(s, dict) and s.get("source_id")}
    records: dict[str, dict[str, Any]] = {}
    provider_success = Counter()
    for record in coverage.get("sources", []) if isinstance(coverage, dict) else []:
        if not isinstance(record, dict) or not record.get("source_id"):
            add_issue(issues, "FAIL", "COVERAGE_RECORD_INVALID", "coverage 来源记录缺少 source_id")
            continue
        source_id = str(record["source_id"])
        if source_id in records:
            add_issue(issues, "FAIL", "COVERAGE_DUPLICATE", "coverage 中 source_id 重复", source_id=source_id)
        records[source_id] = record
        source = sources.get(source_id, {})
        if not source:
            add_issue(issues, "WARN", "UNREGISTERED_SOURCE", "coverage 中存在未注册来源", source_id=source_id)
        if record.get("status") not in STATUSES:
            add_issue(issues, "FAIL", "COVERAGE_STATUS_INVALID", f"非法 status: {record.get('status')!r}", source_id=source_id)
        attempts = record.get("endpoint_attempts")
        registered_endpoint_ids = {
            endpoint.get("endpoint_id") for endpoint in source.get("endpoints", [])
            if isinstance(endpoint, dict) and endpoint.get("endpoint_id")
        }
        registered_endpoints = {
            endpoint.get("endpoint_id"): endpoint for endpoint in source.get("endpoints", [])
            if isinstance(endpoint, dict) and endpoint.get("endpoint_id")
        }
        if record.get("scheduled") and (not isinstance(attempts, list) or not attempts):
            add_issue(issues, "FAIL", "ENDPOINT_ATTEMPT_MISSING", "已调度来源必须记录 endpoint_attempts", source_id=source_id)
        for attempt in attempts if isinstance(attempts, list) else []:
            if not attempt.get("endpoint_id") or not attempt.get("checked_at"):
                add_issue(issues, "FAIL", "ENDPOINT_ATTEMPT_INVALID", "endpoint attempt 缺少 endpoint_id 或 checked_at", source_id=source_id)
            elif source and attempt.get("endpoint_id") not in registered_endpoint_ids:
                add_issue(issues, "FAIL", "ENDPOINT_ATTEMPT_UNKNOWN", "endpoint attempt 不属于该来源", source_id=source_id, endpoint_id=attempt.get("endpoint_id"))
            elif source and attempt.get("provider_group") != registered_endpoints[attempt.get("endpoint_id")].get("provider_group"):
                add_issue(issues, "FAIL", "ENDPOINT_PROVIDER_MISMATCH", "attempt provider_group 与注册表不一致", source_id=source_id, endpoint_id=attempt.get("endpoint_id"))
            if attempt.get("status") not in {"ok", "failed", "blocked"}:
                add_issue(issues, "FAIL", "ENDPOINT_ATTEMPT_STATUS_INVALID", "非法 endpoint attempt status", source_id=source_id)
            if attempt.get("status") == "ok":
                provider_success[str(attempt.get("provider_group") or "unknown")] += 1
        if record.get("status") == "no_update":
            if not record.get("checked_at"):
                add_issue(issues, "FAIL", "NO_UPDATE_WITHOUT_CHECK", "no_update 必须记录 checked_at", source_id=source_id)
            if not source.get("operator_verified"):
                add_issue(issues, "FAIL", "NO_UPDATE_SOURCE_UNVERIFIED", "未核验来源不能断言 no_update", source_id=source_id)
            if record.get("account_window_complete") is not True:
                add_issue(issues, "FAIL", "NO_UPDATE_WINDOW_INCOMPLETE", "no_update 必须确认完整枚举时间窗", source_id=source_id)
            if not any(attempt.get("status") == "ok" for attempt in (attempts if isinstance(attempts, list) else [])):
                add_issue(issues, "FAIL", "NO_UPDATE_WITHOUT_SUCCESSFUL_ENDPOINT", "no_update 至少需要一个成功的 endpoint attempt", source_id=source_id)

    scheduled_statuses = set(profile.get("scheduled_source_statuses", ["active", "unverified"]))
    schedulable = {sid: s for sid, s in sources.items() if s.get("status") in scheduled_statuses}
    active = {sid: s for sid, s in sources.items() if s.get("status") == "active"}
    endpoint_rules = profile.get("endpoint_requirements", {})
    for sid, source in schedulable.items():
        rule = endpoint_rules.get(source.get("priority"), {})
        minimum = int(rule.get("min_configured", 0))
        count = len(configured_endpoints(source))
        if count < minimum:
            severity = "FAIL" if rule.get("hard") else "WARN"
            add_issue(issues, severity, "SOURCE_ENDPOINT_COVERAGE_LOW", f"可用 endpoint 不足: {count}/{minimum}", source_id=sid)

    schedule_summary: dict[str, Any] = {}
    for priority in ("C1", "C2"):
        expected = {sid for sid, source in schedulable.items() if source.get("priority") == priority}
        # A source is "configured" only if it actually has a usable endpoint;
        # hard_required sources are pulled into scheduling automatically rather
        # than relying on a hand-curated pilot list.
        configured = {sid for sid in expected if configured_endpoints(schedulable[sid])}
        scheduled = {sid for sid in expected if sid in records and records[sid].get("scheduled") is True}
        attempted = {
            sid for sid in configured
            if sid in records and isinstance(records[sid].get("endpoint_attempts"), list)
            and records[sid]["endpoint_attempts"]
        }
        configured_ratio = len(configured) / len(expected) if expected else 1.0
        attempted_ratio = len(attempted) / len(configured) if configured else 1.0
        rule = profile.get("attempt_requirements", {}).get(priority, {})
        minimum = float(rule.get("ratio", 0))
        if attempted_ratio < minimum:
            severity = "FAIL" if rule.get("hard") else "WARN"
            add_issue(issues, severity, f"{priority}_ATTEMPT_RATIO_LOW",
                      f"{priority} endpoint attempt 覆盖不足（在已配置来源中）",
                      attempted_ratio=round(attempted_ratio, 4))
        schedule_summary[priority] = {
            "expected": len(expected), "configured": len(configured), "scheduled": len(scheduled),
            "attempted": len(attempted),
            "registry_configured_ratio": round(configured_ratio, 4),
            "attempted_ratio_among_configured": round(attempted_ratio, 4),
        }

    hard = {sid for sid, source in active.items() if source.get("hard_required")}
    hard_success = hard & {sid for sid, record in records.items() if record.get("status") in SUCCESS}
    for source_id in sorted(hard - records.keys()):
        add_issue(issues, "FAIL", "HARD_SOURCE_MISSING", "硬性来源未出现在 coverage", source_id=source_id)
    hard_ratio = len(hard_success) / len(hard) if hard else 1.0
    if hard_ratio < float(profile["hard_required_success_ratio"]):
        add_issue(issues, "FAIL", "HARD_SUCCESS_RATIO_LOW", "硬性来源成功率低于策略阈值", ratio=round(hard_ratio, 4))

    successful = {sid for sid, record in records.items() if sid in active and record.get("status") in SUCCESS}
    dimensions: dict[str, Any] = {}
    for dimension, rule in profile.get("dimension_requirements", {}).items():
        matched = sorted(sid for sid in successful if dimension in active[sid].get("coverage_dimensions", []))
        minimum = int(rule.get("min_checked", 0))
        dim_status = "PASS" if len(matched) >= minimum else "FAIL" if rule.get("hard") else "WARN"
        dimensions[dimension] = {"status": dim_status, "checked": len(matched), "minimum": minimum, "source_ids": matched}
        if dim_status != "PASS":
            add_issue(issues, dim_status, "DIMENSION_COVERAGE_LOW", f"{dimension} 覆盖不足: {len(matched)}/{minimum}", dimension=dimension)

    groups = Counter(active[sid]["independence_group"] for sid in successful)
    total_groups = sum(groups.values())
    dominant_group, dominant_count = groups.most_common(1)[0] if groups else ("", 0)
    dominant_share = dominant_count / total_groups if total_groups else 0.0
    independence_rule = profile.get("independence", {})
    if len(groups) < int(independence_rule.get("min_checked_groups", 0)):
        add_issue(issues, "WARN", "INDEPENDENCE_GROUPS_LOW", "成功检查的独立来源组不足", count=len(groups))
    if dominant_share > float(independence_rule.get("max_checked_share_per_group", 1.0)):
        add_issue(issues, "WARN", "SOURCE_GROUP_DOMINANT", "单一内容来源组占比过高", group=dominant_group, share=round(dominant_share, 4))

    provider_total = sum(provider_success.values())
    provider_name, provider_count = provider_success.most_common(1)[0] if provider_success else ("", 0)
    provider_share = provider_count / provider_total if provider_total else 0.0
    max_provider_share = float(profile.get("provider_concentration", {}).get("max_success_share", 1.0))
    if provider_share > max_provider_share:
        add_issue(issues, "WARN", "COLLECTOR_PROVIDER_DOMINANT", "单一采集基础设施占比过高", provider_group=provider_name, share=round(provider_share, 4))

    stale_ids = []
    max_age = profile.get("registry_max_age_days", {})
    for sid, source in active.items():
        verified = source.get("last_verified_at")
        if not verified:
            stale_ids.append(sid)
            continue
        try:
            age = (as_of - date.fromisoformat(verified)).days
        except ValueError:
            continue
        if age > int(max_age.get(source.get("priority"), 10**9)):
            stale_ids.append(sid)
    if stale_ids:
        add_issue(issues, "WARN", "REGISTRY_ENTRIES_STALE", "部分 active 来源超过核验周期", source_ids=sorted(stale_ids))

    status = "FAIL" if any(x["severity"] == "FAIL" for x in issues) else "WARN" if issues else "PASS"
    report = {
        "schema_version": "2.0", "overall_status": status, "profile": profile_name,
        "hard_required": {"successful": len(hard_success), "total": len(hard), "ratio": round(hard_ratio, 4)},
        "schedule": schedule_summary, "dimensions": dimensions,
        "independence": {"group_count": len(groups), "dominant_group": dominant_group, "dominant_share": round(dominant_share, 4)},
        "provider_concentration": {"provider_group": provider_name, "dominant_share": round(provider_share, 4)},
        "issues": issues,
    }
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"来源覆盖审计: {status} -> {args.output}", file=sys.stderr)
    return 1 if status == "FAIL" or (args.strict and status == "WARN") else 0


if __name__ == "__main__":
    raise SystemExit(main())
