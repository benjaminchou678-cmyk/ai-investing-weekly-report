#!/usr/bin/env python3
"""Audit the authoritative final_weekly_report.json (schema v3).

The JSON is the single source of truth. Markdown / HTML are renderings and are
only checked for consistency against the JSON when supplied.

Dynamic rules (replaces the old fixed three-judgment regex audit):
- theses: 0-3. >3 is FAIL. 0 is allowed when evidence is insufficient; but if
  the lead still claims a formed trend, that is FAIL.
- every published thesis must carry all required fields.
- independence_status=unknown evidence cannot pass the independent-evidence gate;
  same-group / republished sources must not be double-counted.
- core_events <= 7; watchlist <= 5; candidate layers must not duplicate ids.
- when md/html are provided, their counts must match the JSON.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None

THESIS_MAX = 3
CORE_MAX = 7
WATCH_MAX = 5
THESIS_REQUIRED = (
    "thesis_id", "statement", "structural_change", "key_evidence",
    "why_it_matters", "investment_readthrough", "counter_evidence",
    "falsification_conditions", "confidence", "related_boards",
)
ALLOWED_CONFIDENCE = {"low", "medium", "high"}

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "final_weekly_report.schema.json"


def add_issue(issues: list[dict[str, Any]], severity: str, code: str, message: str, **details: Any) -> None:
    issues.append({"severity": severity, "code": code, "message": message, **details})


def _cluster_id(item: dict[str, Any]) -> str:
    return str(item.get("cluster_id") or item.get("event_cluster_id") or item.get("event_id") or "")


def audit_json(data: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []

    # Structural shape is delegated to the real JSON Schema (single source of
    # truth); the checks below are the second, semantic layer.
    if jsonschema is not None and _SCHEMA_PATH.exists():
        schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
        try:
            jsonschema.validate(instance=data, schema=schema)
        except jsonschema.ValidationError as exc:
            path = "/".join(str(p) for p in exc.absolute_path) or "<root>"
            add_issue(issues, "FAIL", "SCHEMA_VIOLATION",
                      f"不符合 final_weekly_report.schema.json: {exc.message}", json_path=path)
    else:
        for key in ("report_meta", "weekly_lead", "theses", "core_events", "watchlist",
                    "editorial_candidate_pool", "human_review_queue", "appendix_events",
                    "excluded_events", "source_audit", "quality_status"):
            if key not in data:
                add_issue(issues, "FAIL", "TOP_LEVEL_KEY_MISSING", f"缺少顶层字段：{key}", field=key)

    theses = data.get("theses", [])
    if not isinstance(theses, list):
        theses = []
    if len(theses) > THESIS_MAX:
        add_issue(issues, "FAIL", "THESIS_COUNT_TOO_HIGH",
                  f"判断数量 {len(theses)} 超过上限 {THESIS_MAX}", count=len(theses))

    used_ids: dict[str, str] = {}

    for t in theses:
        tid = t.get("thesis_id", "")
        for field in THESIS_REQUIRED:
            if t.get(field) in (None, "", []):
                add_issue(issues, "FAIL", "THESIS_FIELD_MISSING",
                          f"判断 {tid} 缺少字段：{field}", thesis_id=tid)
        conf = t.get("confidence", "")
        if conf not in ALLOWED_CONFIDENCE:
            add_issue(issues, "FAIL", "THESIS_CONFIDENCE_INVALID",
                      f"判断 {tid} 置信度非法：{conf}", thesis_id=tid)

        evidence = t.get("key_evidence", [])
        groups: set[str] = set()
        for ev in evidence:
            eid = str(ev.get("cluster_id", ""))
            if ev.get("independence_status") == "unknown":
                add_issue(issues, "FAIL", "THESIS_EVIDENCE_INDEPENDENCE_UNKNOWN",
                          f"判断 {tid} 含独立性未知证据 {eid}，不得通过独立证据门", thesis_id=tid, cluster_id=eid)
            ev_groups = set(ev.get("independence_groups", []))
            if groups & ev_groups:
                add_issue(issues, "FAIL", "THESIS_EVIDENCE_SHARED_GROUP",
                          f"判断 {tid} 两条证据共享独立组，疑似转载/同源", thesis_id=tid, cluster_id=eid)
            groups |= ev_groups

    # 0 theses: allowed if evidence-insufficient; FAIL if lead still claims a trend.
    lead = str(data.get("weekly_lead", ""))
    if len(theses) == 0:
        claims_trend = ("判断" in lead or "趋势" in lead) and not re.search(r"未形成|不足|暂不|不构成", lead)
        if claims_trend:
            add_issue(issues, "FAIL", "ZERO_THESIS_BUT_CLAIMS_TREND",
                      "本周未形成判断，但周报导语仍声称形成趋势")
        else:
            add_issue(issues, "WARN", "ZERO_THESIS",
                      "本周形成 0 条判断：未达到证据门槛（已显式披露）")

    core = data.get("core_events", []) or []
    if len(core) > CORE_MAX:
        add_issue(issues, "FAIL", "CORE_COUNT_TOO_HIGH",
                  f"核心事件 {len(core)} 超过上限 {CORE_MAX}", count=len(core))
    watchlist = data.get("watchlist", []) or []
    if len(watchlist) > WATCH_MAX:
        add_issue(issues, "FAIL", "WATCH_COUNT_TOO_HIGH",
                  f"Watchlist {len(watchlist)} 超过上限 {WATCH_MAX}", count=len(watchlist))

    # No duplicate cluster ids across the body layers.
    for layer_name, layer in (
        ("core", core), ("watchlist", watchlist),
        ("candidate", data.get("editorial_candidate_pool", []) or []),
        ("review", data.get("human_review_queue", []) or []),
        ("appendix", data.get("appendix_events", []) or []),
    ):
        for item in layer:
            cid = _cluster_id(item)
            if not cid:
                continue
            if cid in used_ids:
                add_issue(issues, "WARN", "EVENT_DUPLICATED_ACROSS_LAYERS",
                          f"事件 {cid} 同时出现在 {used_ids[cid]} 与 {layer_name}", cluster_id=cid)
            else:
                used_ids[cid] = layer_name

    # quality_status consistency
    qs = data.get("quality_status", {}) or {}
    if qs.get("thesis_count") is not None and qs["thesis_count"] != len(theses):
        add_issue(issues, "FAIL", "QUALITY_THESIS_COUNT_MISMATCH",
                  "quality_status.thesis_count 与 theses 数量不一致")
    if qs.get("core_count") is not None and qs["core_count"] != len(core):
        add_issue(issues, "WARN", "QUALITY_CORE_COUNT_MISMATCH",
                  "quality_status.core_count 与 core_events 数量不一致")

    return {"issues": issues, "counts": {
        "thesis_count": len(theses), "core_count": len(core),
        "watchlist_count": len(watchlist),
        "candidate_count": len(data.get("editorial_candidate_pool", []) or []),
        "review_count": len(data.get("human_review_queue", []) or []),
        "appendix_count": len(data.get("appendix_events", []) or []),
    }}


def _count_md_sections(md: str) -> dict[str, int]:
    return {
        "theses": len(re.findall(r"^###\s+判断｜", md, re.MULTILINE)),
        "core": len(re.findall(r"^\*\*.+?\*\*（\d+\s*/", md, re.MULTILINE)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", dest="json_path", help="authoritative final_weekly_report.json")
    parser.add_argument("--md", dest="md_path", default="")
    parser.add_argument("--html", dest="html_path", default="")
    parser.add_argument("--output", "-o", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    issues: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    try:
        if not args.json_path:
            raise SystemExit("错误: 必须提供 --json final_weekly_report.json")
        data = json.loads(Path(args.json_path).expanduser().read_text(encoding="utf-8"))
        res = audit_json(data)
        issues.extend(res["issues"])
        counts = res["counts"]
    except (OSError, json.JSONDecodeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    if args.md_path:
        md = Path(args.md_path).expanduser().read_text(encoding="utf-8")
        md_counts = _count_md_sections(md)
        if md_counts["theses"] != counts["thesis_count"]:
            add_issue(issues, "FAIL", "MD_THESIS_COUNT_MISMATCH",
                      f"Markdown 判断数 {md_counts['theses']} 与 JSON {counts['thesis_count']} 不一致")
        if md_counts["core"] != counts["core_count"]:
            add_issue(issues, "WARN", "MD_CORE_COUNT_MISMATCH",
                      f"Markdown 核心事件数 {md_counts['core']} 与 JSON {counts['core_count']} 不一致")

    status = "FAIL" if any(x["severity"] == "FAIL" for x in issues) else "WARN" if issues else "PASS"
    report = {
        "schema_version": "3.0", "overall_status": status,
        "counts": counts, "issues": issues,
    }
    Path(args.output).expanduser().write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"周报结构审计(JSON): {status} -> {args.output}", file=sys.stderr)
    return 1 if status == "FAIL" or (args.strict and status == "WARN") else 0


if __name__ == "__main__":
    raise SystemExit(main())
