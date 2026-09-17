#!/usr/bin/env python3
"""Audit a run's source coverage against registry and policy."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

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
    parser.add_argument("--as-of", default=date.today().isoformat(), help="YYYY-MM-DD，用于注册表陈旧检查")
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
    registry_issues = validate(registry)
    for entry in registry_issues:
        if entry["severity"] == "FAIL":
            add_issue(issues, "FAIL", "REGISTRY_INVALID", entry["message"], source_id=entry.get("source_id", ""))

    sources = {s["source_id"]: s for s in registry.get("sources", []) if isinstance(s, dict) and s.get("source_id")}
    records_list = coverage.get("sources", []) if isinstance(coverage, dict) else []
    records: dict[str, dict[str, Any]] = {}
    for record in records_list if isinstance(records_list, list) else []:
        if not isinstance(record, dict) or not record.get("source_id"):
            add_issue(issues, "FAIL", "COVERAGE_RECORD_INVALID", "coverage 来源记录缺少 source_id")
            continue
        source_id = str(record["source_id"])
        if source_id in records:
            add_issue(issues, "FAIL", "COVERAGE_DUPLICATE", "coverage 中 source_id 重复", source_id=source_id)
        records[source_id] = record
        if source_id not in sources:
            add_issue(issues, "WARN", "UNREGISTERED_SOURCE", "coverage 中存在未注册来源", source_id=source_id)
        if record.get("status") not in STATUSES:
            add_issue(issues, "FAIL", "COVERAGE_STATUS_INVALID", f"非法 status: {record.get('status')!r}", source_id=source_id)
        if record.get("status") == "no_update" and not record.get("checked_at"):
            add_issue(issues, "FAIL", "NO_UPDATE_WITHOUT_CHECK", "no_update 必须记录 checked_at，证明访问成功", source_id=source_id)

    active = {sid: s for sid, s in sources.items() if s.get("status") == "active"}
    hard = {sid for sid, s in active.items() if s.get("hard_required")}
    hard_success = hard & {sid for sid, r in records.items() if r.get("status") in SUCCESS}
    for source_id in sorted(hard - records.keys()):
        add_issue(issues, "FAIL", "HARD_SOURCE_MISSING", "硬性来源未出现在 coverage", source_id=source_id)
    hard_ratio = len(hard_success) / len(hard) if hard else 1.0
    if hard_ratio < float(profile["hard_required_success_ratio"]):
        add_issue(issues, "FAIL", "HARD_SUCCESS_RATIO_LOW", "硬性来源成功率低于策略阈值", ratio=round(hard_ratio, 4))

    expected_c1 = {
        sid for sid, source in active.items()
        if source.get("priority") == "C1" and source.get("check_frequency") == "weekly"
    }
    scheduled_c1 = {sid for sid in expected_c1 if sid in records and records[sid].get("scheduled") is True}
    checked_c1 = {sid for sid in scheduled_c1 if records[sid].get("status") in SUCCESS}
    c1_ratio = len(checked_c1) / len(expected_c1) if expected_c1 else 0.0
    missing_c1 = sorted(expected_c1 - scheduled_c1)
    if missing_c1:
        add_issue(issues, "WARN", "C1_NOT_SCHEDULED", "部分 active C1 未进入本周采集计划", source_ids=missing_c1)
    if expected_c1 and c1_ratio < float(profile["scheduled_c1_checked_ratio"]):
        add_issue(issues, "WARN", "C1_CHECK_RATIO_LOW", "计划检查的 C1 来源完成率低于策略阈值", ratio=round(c1_ratio, 4))
    if not expected_c1:
        add_issue(issues, "WARN", "C1_SCHEDULE_EMPTY", "本次 coverage 没有计划检查的 active C1 来源")

    successful = {sid for sid, r in records.items() if sid in active and r.get("status") in SUCCESS}
    dimensions: dict[str, dict[str, Any]] = {}
    for dimension, rule in profile.get("dimension_requirements", {}).items():
        matched = sorted(sid for sid in successful if dimension in active[sid].get("coverage_dimensions", []))
        count, minimum = len(matched), int(rule.get("min_checked", 0))
        dim_status = "PASS" if count >= minimum else "FAIL" if rule.get("hard") else "WARN"
        dimensions[dimension] = {"status": dim_status, "checked": count, "minimum": minimum, "source_ids": matched}
        if dim_status != "PASS":
            add_issue(issues, dim_status, "DIMENSION_COVERAGE_LOW", f"{dimension} 覆盖不足: {count}/{minimum}", dimension=dimension)

    groups = Counter(active[sid]["independence_group"] for sid in successful)
    total = sum(groups.values())
    dominant_group, dominant_count = groups.most_common(1)[0] if groups else ("", 0)
    dominant_share = dominant_count / total if total else 0.0
    independence_rule = profile.get("independence", {})
    if len(groups) < int(independence_rule.get("min_checked_groups", 0)):
        add_issue(issues, "WARN", "INDEPENDENCE_GROUPS_LOW", "成功检查的独立来源组不足", count=len(groups))
    if dominant_share > float(independence_rule.get("max_checked_share_per_group", 1.0)):
        add_issue(issues, "WARN", "SOURCE_GROUP_DOMINANT", "单一来源组占比超过策略阈值", group=dominant_group, share=round(dominant_share, 4))

    max_age = profile.get("registry_max_age_days", {})
    stale_ids: list[str] = []
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
        "schema_version": "1.0", "overall_status": status, "profile": profile_name,
        "hard_required": {"successful": len(hard_success), "total": len(hard), "ratio": round(hard_ratio, 4)},
        "scheduled_c1": {"checked": len(checked_c1), "total": len(expected_c1), "ratio": round(c1_ratio, 4)},
        "dimensions": dimensions,
        "independence": {"group_count": len(groups), "dominant_group": dominant_group, "dominant_share": round(dominant_share, 4)},
        "issues": issues,
    }
    Path(args.output).expanduser().write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"来源覆盖审计: {status} -> {args.output}", file=sys.stderr)
    return 1 if status == "FAIL" or (args.strict and status == "WARN") else 0


if __name__ == "__main__":
    raise SystemExit(main())
