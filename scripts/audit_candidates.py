#!/usr/bin/env python3
"""Run pre-edit or release QA for an AI investing weekly report."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from _candidate_io import as_list, read_json_items, write_json
from merge_candidates import canonical_url, title_similarity

ALLOWED_BOARDS = {"大厂动向", "初创动向", "生态动向", "技术博客&论文", "海外建设者", "观点与深度"}
ALLOWED_SIGNALS = {"S", "A", "B"}
ALLOWED_THESIS_IMPACTS = {"new", "strengthen", "weaken", "invalidate", "neutral"}
REQUIRED_STEPS = {"official_and_media", "builder_feeds", "supplemental_search", "normalize", "url_audit", "dedup"}
SUCCESS_SOURCE_STATUSES = {"ok", "success", "no_update"}


def gate(status: str, summary: dict[str, Any], issues: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": status, **summary, "issues": issues}


def load_json(path: str | None) -> Any:
    if not path:
        return None
    return json.loads(Path(path).expanduser().read_text(encoding="utf-8"))


def parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        match = re.search(r"\b20\d{2}-\d{2}-\d{2}\b", text)
        return date.fromisoformat(match.group(0)) if match else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="候选或入选条目 JSON")
    parser.add_argument("--output", "-o", required=True)
    parser.add_argument("--phase", choices=("pre-edit", "release"), default="pre-edit")
    parser.add_argument("--week-start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--week-end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--timezone", default="Asia/Shanghai")
    parser.add_argument("--coverage")
    parser.add_argument("--source-registry")
    parser.add_argument("--run-manifest")
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        ZoneInfo(args.timezone)
        week_start, week_end = date.fromisoformat(args.week_start), date.fromisoformat(args.week_end)
        if week_end < week_start:
            raise ValueError("week-end 不能早于 week-start")
        items, _ = read_json_items(Path(args.input).expanduser())
        coverage = load_json(args.coverage)
        registry = load_json(args.source_registry)
        manifest = load_json(args.run_manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    gates: dict[str, Any] = {}

    execution_issues: list[dict[str, Any]] = []
    if not isinstance(manifest, dict):
        execution_issues.append({"issue": "缺少 run-manifest，无法证明必需步骤已执行"})
    else:
        steps = manifest.get("steps", {}) if isinstance(manifest.get("steps"), dict) else {}
        for step in sorted(REQUIRED_STEPS):
            if steps.get(step) != "completed":
                execution_issues.append({"step": step, "status": steps.get(step, "missing")})
        if manifest.get("week_start") != args.week_start or manifest.get("week_end") != args.week_end:
            execution_issues.append({"issue": "run-manifest 周期与命令参数不一致"})
    gates["gate0_execution"] = gate("PASS" if not execution_issues else "FAIL", {"required_steps": len(REQUIRED_STEPS)}, execution_issues)

    source_issues: list[dict[str, Any]] = []
    if not isinstance(registry, dict) or not isinstance(coverage, dict):
        source_issues.append({"issue": "必须同时提供 source-registry 与 coverage"})
        required_ids: set[str] = set()
        covered_ids: set[str] = set()
        succeeded_ids: set[str] = set()
    else:
        registered = [s for s in registry.get("sources", []) if isinstance(s, dict) and s.get("required")]
        required_ids = {str(s.get("source_id")) for s in registered if s.get("source_id")}
        covered = [s for s in coverage.get("sources", []) if isinstance(s, dict)]
        covered_ids = {str(s.get("source_id")) for s in covered if s.get("source_id")}
        succeeded_ids = {str(s.get("source_id")) for s in covered if s.get("status") in SUCCESS_SOURCE_STATUSES}
        for source_id in sorted(required_ids - covered_ids):
            source_issues.append({"source_id": source_id, "issue": "required 来源未出现在 coverage"})
        for source in covered:
            if source.get("source_id") in required_ids and source.get("status") not in SUCCESS_SOURCE_STATUSES:
                source_issues.append({"source_id": source.get("source_id"), "status": source.get("status", "missing"), "reason": source.get("reason", "")})
    ratio = len(required_ids & succeeded_ids) / len(required_ids) if required_ids else 0.0
    source_status = "PASS" if required_ids and ratio >= 0.70 and not (required_ids - covered_ids) else "FAIL"
    gates["gate1_source_health"] = gate(source_status, {"required_sources": len(required_ids), "covered_sources": len(required_ids & covered_ids), "success_ratio": round(ratio, 4)}, source_issues)

    dedup_issues: list[dict[str, Any]] = []
    seen_urls: dict[str, int] = {}
    schema_issues: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not str(item.get("title") or "").strip():
            schema_issues.append({"index": index, "field": "title", "issue": "缺少标题"})
        if not item.get("sources") and not item.get("source"):
            schema_issues.append({"index": index, "field": "sources", "issue": "缺少来源"})
        item_date = parse_date(item.get("event_date") or item.get("published_at"))
        if item_date is None:
            schema_issues.append({"index": index, "field": "event_date", "issue": "缺少可解析日期"})
        elif not week_start <= item_date <= week_end:
            schema_issues.append({"index": index, "field": "event_date", "issue": "日期超出周报窗口", "date": item_date.isoformat()})
        key = canonical_url(item.get("url"))
        if key and key in seen_urls:
            dedup_issues.append({"left_index": seen_urls[key], "right_index": index, "type": "exact_url"})
        elif key:
            seen_urls[key] = index
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            similarity = title_similarity(items[i].get("title"), items[j].get("title"))
            if similarity >= 0.90 and canonical_url(items[i].get("url")) != canonical_url(items[j].get("url")):
                dedup_issues.append({"left_index": i, "right_index": j, "type": "similar_title", "similarity": round(similarity, 4)})
    gates["gate2_time_schema_dedup"] = gate("PASS" if not schema_issues and not dedup_issues else "WARN", {"items_checked": len(items)}, schema_issues + dedup_issues)

    signal_issues: list[dict[str, Any]] = []
    evidence_issues: list[dict[str, Any]] = []
    distribution: dict[str, int] = {}
    boards: dict[str, int] = {}
    if args.phase == "release":
        for index, item in enumerate(items):
            signal = str(item.get("signal_level") or "unrated")
            distribution[signal] = distribution.get(signal, 0) + 1
            if signal not in ALLOWED_SIGNALS:
                signal_issues.append({"index": index, "field": "signal_level", "issue": "入选项必须为 S/A/B"})
            if not as_list(item.get("business_signals")):
                signal_issues.append({"index": index, "field": "business_signals", "issue": "缺少业务信号"})
            thesis = item.get("thesis") if isinstance(item.get("thesis"), dict) else {}
            if thesis.get("impact") not in ALLOWED_THESIS_IMPACTS or not thesis.get("statement"):
                signal_issues.append({"index": index, "field": "thesis", "issue": "缺少合法投资假设及影响"})
            for field in ("materiality", "time_horizon", "catalyst", "downside_risk"):
                if not item.get(field):
                    signal_issues.append({"index": index, "field": field, "issue": "发布前字段缺失"})
            claims = item.get("claims") if isinstance(item.get("claims"), list) else []
            if not claims:
                evidence_issues.append({"index": index, "field": "claims", "issue": "没有 claim 来源映射"})
            for claim_index, claim in enumerate(claims):
                if not isinstance(claim, dict) or not claim.get("claim") or not as_list(claim.get("source_ids")):
                    evidence_issues.append({"index": index, "claim_index": claim_index, "issue": "claim 缺少文本或 source_ids"})
            if not item.get("editor_reviewed"):
                evidence_issues.append({"index": index, "field": "editor_reviewed", "issue": "尚未完成人工/模型编辑核验"})
    gates["gate3_signal_thesis"] = gate("PASS" if not signal_issues else "FAIL", {"phase": args.phase, "distribution": distribution}, signal_issues)
    gates["gate4_evidence"] = gate("PASS" if not evidence_issues else "FAIL", {"phase": args.phase}, evidence_issues)

    completeness_issues: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        board = str(item.get("board") or "")
        boards[board or "未分类"] = boards.get(board or "未分类", 0) + 1
        if board and board not in ALLOWED_BOARDS:
            completeness_issues.append({"index": index, "board": board, "issue": "未知板块"})
    if args.phase == "release" and not 6 <= len(items) <= 12:
        completeness_issues.append({"issue": "核心条目不在默认 6-12 条范围；质量不足时需在正文解释", "count": len(items)})
    gates["gate5_completeness"] = gate("PASS" if not completeness_issues else "WARN", {"phase": args.phase, "board_distribution": boards}, completeness_issues)

    statuses = [entry["status"] for entry in gates.values()]
    overall = "FAIL" if "FAIL" in statuses else "WARN" if "WARN" in statuses else "PASS"
    report = {
        "schema_version": "2.0", "phase": args.phase,
        "week_start": args.week_start, "week_end": args.week_end,
        "timezone": args.timezone, "input": str(Path(args.input).expanduser()),
        "total_items": len(items), "overall_status": overall, "gates": gates,
        "limitations": ["机器 QA 不能替代网页事实核验、来源独立性判断或投资编辑判断。"],
    }
    write_json(Path(args.output).expanduser(), report)
    print(f"{args.phase} QA 完成: {overall} -> {args.output}", file=sys.stderr)
    return 1 if overall == "FAIL" or (args.strict and overall == "WARN") else 0


if __name__ == "__main__":
    raise SystemExit(main())
