#!/usr/bin/env python3
"""审核权威 JSON 的发布契约，并按需核对实际交付的 Markdown/HTML。"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

try:
    import jsonschema
except ImportError:
    jsonschema = None

from _report_contract import (LAYERS, THESIS_FIELDS, EVENT_FIELDS, event_id, review_reasons, fingerprint,
                              source_links, safe_url, all_events, public_events, week_meta)
from rank_events import LEGACY_FIELDS

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas/final_weekly_report.schema.json"


def issue(issues, code, message, severity="FAIL", **details):
    issues.append({"severity": severity, "code": code, "message": message, **details})


def load_validator():
    if jsonschema is None:
        raise ValueError("缺少 jsonschema；请按 requirements.txt 安装，禁止降级为不完整校验")
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())


def audit_json(data: dict, ranked: list[dict] | None = None) -> dict:
    issues = []
    counts = {}
    try:
        validator = load_validator()
        errors = sorted(validator.iter_errors(data), key=lambda e: str(list(e.absolute_path)))
    except (OSError, ValueError) as exc:
        issue(issues, "SCHEMA_UNAVAILABLE", str(exc))
        return {"issues": issues, "counts": counts}
    for error in errors:
        issue(issues, "SCHEMA_VIOLATION", error.message, json_path="/".join(map(str, error.absolute_path)))
    if errors:
        return {"issues": issues, "counts": counts}
    meta = data["report_meta"]
    try:
        expected = week_meta(meta["week_start"], meta["week_end"])
        if meta["week_label"] != expected["week_label"]:
            issue(issues, "WEEK_LABEL_MISMATCH", "周报标题日期与结构化日期不一致")
    except ValueError as exc:
        issue(issues, "WEEK_RANGE_INVALID", str(exc))
        return {"issues": issues, "counts": counts}

    def legacy(value, path=""):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in LEGACY_FIELDS:
                    issue(issues, "LEGACY_SCORE_FIELD", f"新契约不接受百分制字段：{path}/{key}")
                legacy(child, f"{path}/{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                legacy(child, f"{path}/{index}")
    legacy(data)

    ids = []
    locations = {}
    for layer in LAYERS:
        counts[layer] = len(data[layer])
        for event in data[layer]:
            cid = event_id(event)
            ids.append(cid)
            locations[cid] = layer
            reasons = review_reasons(event, meta)
            if layer not in {"human_review_queue", "excluded_events"} and reasons:
                issue(issues, "UNREVIEWED_EVENT_OUTSIDE_QUEUE", f"事件 {cid} 应先进入复核队列", reasons=reasons)
            if layer == "core_events" and event["signal_level"] not in {"S", "A"}:
                if not (event.get("editorial_override") is True and event.get("override_reason") and event["signal_level"] == "B"):
                    issue(issues, "CORE_LEVEL_INVALID", f"事件 {cid} 核心选择需 S/A，B 级须显式编辑理由")
            if layer == "watchlist" and event["signal_level"] not in {"S", "A", "B"}:
                issue(issues, "WATCH_LEVEL_INVALID", f"事件 {cid} 非有效观察项")
            if layer == "editorial_candidate_pool" and event["signal_level"] not in {"S", "A", "B"}:
                issue(issues, "CANDIDATE_LEVEL_INVALID", f"事件 {cid} 应进入来源池或复核队列")
            if layer == "appendix_events" and event["signal_level"] != "noise":
                issue(issues, "APPENDIX_LEVEL_INVALID", f"事件 {cid} 有效候选应留备选池")
    duplicate = [cid for cid, count in Counter(ids).items() if count > 1]
    if duplicate:
        issue(issues, "DUPLICATE_EVENT", "每个事件只能归入一个去向", event_ids=duplicate)
    declared = set(data["input_event_ids"])
    if set(ids) != declared:
        issue(issues, "EVENT_RETENTION_MISMATCH", "候选去向与输入清单不一致", missing=sorted(declared-set(ids)), unexpected=sorted(set(ids)-declared))
    if ranked is None:
        issue(issues, "INPUT_BASELINE_MISSING", "缺少 --ranked，无法证明原始候选全部保留")
    else:
        original = [event_id(e) for e in ranked]
        if len(set(original)) != len(original) or "" in original:
            issue(issues, "INPUT_BASELINE_INVALID", "原始事件标识缺失或重复")
        if set(original) != declared:
            issue(issues, "INPUT_BASELINE_CHANGED", "权威 JSON 的输入事件清单与 ranked_events 不一致")

    events = all_events(data)
    thesis_ids = []
    for thesis in data["theses"]:
        thesis_ids.append(thesis["thesis_id"])
        evidence_ids = [e["cluster_id"] for e in thesis["key_evidence"]]
        if len(set(evidence_ids)) != len(evidence_ids):
            issue(issues, "DUPLICATE_THESIS_EVIDENCE", "同一判断重复引用同一事件")
        for cid in evidence_ids:
            if cid not in events or locations.get(cid) not in {"core_events", "watchlist", "editorial_candidate_pool"}:
                issue(issues, "THESIS_EVENT_INVALID", f"判断引用了缺失、待复核、noise 或排除事件 {cid}")
    if len(thesis_ids) != len(set(thesis_ids)):
        issue(issues, "DUPLICATE_THESIS", "判断标识重复")
    counts["theses"] = len(data["theses"])
    public = list(data["core_events"] + data["watchlist"])
    public_ids = {event_id(e) for e in public}
    for thesis in data["theses"]:
        for evidence in thesis["key_evidence"]:
            cid = evidence["cluster_id"]
            if cid in events and cid not in public_ids:
                public.append(events[cid])
                public_ids.add(cid)
    for event in public:
        cid = event_id(event)
        # 判断引用的候选也须通过与正文相同的事实审核。
        sub_schema = {"$ref": "#/$defs/published_event", "$defs": validator.schema["$defs"]}
        for error in jsonschema.Draft202012Validator(sub_schema).iter_errors(event):
            issue(issues, "PUBLISHED_EVENT_INVALID", f"{cid}: {error.message}")
        source_ids = [s.get("source_id") for s in event.get("sources", [])]
        if len(source_ids) != len(set(source_ids)):
            issue(issues, "SOURCE_ID_DUPLICATED", f"事件 {cid} 来源 ID 重复，claim 映射不明确")
        if not source_links(event) or any(not safe_url(url) for _, url in source_links(event)):
            issue(issues, "SOURCE_URL_INVALID", f"事件 {cid} 缺少合法原文链接")
        for claim in event.get("claims", []):
            if not set(claim.get("source_ids", [])).issubset(set(source_ids)):
                issue(issues, "CLAIM_SOURCE_UNRESOLVED", f"事件 {cid} claim 引用不存在的来源")
    qs = data["quality_status"]
    if not data["theses"]:
        if not re.search(r"未形成|不足|暂不", qs["zero_thesis_reason"]):
            issue(issues, "ZERO_THESIS_UNDISCLOSED", "零判断必须明确披露未形成判断或证据不足")
        else:
            issue(issues, "ZERO_THESIS", "本期无可发布产业判断，已披露", "WARN")
        if re.search(r"趋势|判断|主线已形成", data["weekly_lead"]) and not re.search(r"未形成|不足|暂不|不构成", data["weekly_lead"]):
            issue(issues, "ZERO_THESIS_BUT_CLAIMS_TREND", "零判断时导语不得宣称形成明确产业趋势")
    if len(data["core_events"]) < 5 or len(data["watchlist"]) < 3:
        if not qs["sparse_note"].strip():
            issue(issues, "SPARSE_UNDISCLOSED", "正文低于建议数量，需解释证据或编辑原因，不得凑数")
        else:
            issue(issues, "SPARSE_WEEK", "正文数量低于建议范围，已披露", "WARN")
    source_status = data["source_audit"]["overall_status"]
    if source_status == "FAIL":
        issue(issues, "SOURCE_AUDIT_FAILED", "来源审核失败，不得发布")
    elif source_status == "WARN":
        if not qs["disclosures"] or not data["source_audit"]["limitations"]:
            issue(issues, "SOURCE_WARN_UNDISCLOSED", "来源 WARN 必须记录限制并在展示中披露")
        else:
            issue(issues, "SOURCE_AUDIT_WARN", "来源覆盖有限，已披露", "WARN")
    return {"issues": issues, "counts": counts}


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.links, self.headings = [], [], []
        self.hidden = 0
        self.heading = None
    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "head"}:
            self.hidden += 1
        if tag == "a" and not self.hidden:
            self.links.append(dict(attrs).get("href", ""))
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and not self.hidden:
            self.heading = []
    def handle_endtag(self, tag):
        if tag in {"script", "style", "head"}:
            self.hidden = max(0, self.hidden-1)
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self.heading is not None:
            self.headings.append("".join(self.heading))
            self.heading = None
    def handle_data(self, text):
        if not self.hidden:
            self.parts.append(text)
            if self.heading is not None:
                self.heading.append(text)


def normalized(text):
    return re.sub(r"\s+", "", html.unescape(str(text)))


def audit_display(final, text: str, kind: str) -> list[dict]:
    issues = []
    if kind == "HTML":
        parser = VisibleHTML()
        parser.feed(text)
        visible, links, headings = " ".join(parser.parts), parser.links, parser.headings
    else:
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        text = re.sub(r"\\([\\`*_\[\]<>#|])", r"\1", text)
        links = re.findall(r"\]\(<?(https?://[^\s>]+)>?\)", text)
        visible = text
        headings = re.findall(r"^#{1,6}\s+(.+)$", text, re.M)
    expected = [final["report_meta"]["week_label"], final["weekly_lead"]]
    titles = [t["theme"] for t in final["theses"]] + [e["title"] for e in final["core_events"]+final["watchlist"]]
    if len(headings) != 5 + len(titles):
        issue(issues, f"{kind}_COUNT_MISMATCH", "展示的标题/条目数量与 JSON 不一致")
    for title in titles:
        if sum(normalized(title) in normalized(h) for h in headings) != 1:
            issue(issues, f"{kind}_TITLE_MISMATCH", f"标题缺失或重复：{title}")
    for thesis in final["theses"]:
        expected += [thesis[k] for _, k in THESIS_FIELDS]
        expected += [thesis["confidence"], "、".join(thesis["related_boards"])]
    for event in public_events(final):
        expected += [event["title"], event["signal_level"]]
        for _, url in source_links(event):
            if url not in links:
                issue(issues, f"{kind}_SOURCE_MISSING", f"缺少来源链接：{url}")
    for event in final["core_events"]+final["watchlist"]:
        expected += [event[k] for _, k in EVENT_FIELDS] + [event["signal_reason"], event["verification_status"]]
    qs = final["quality_status"]
    expected += [qs["sparse_note"], *qs["disclosures"]]
    if not final["theses"]:
        expected.append(qs["zero_thesis_reason"])
    for value in expected:
        if value and normalized(value) not in normalized(visible):
            issue(issues, f"{kind}_CONTENT_MISSING", f"缺少或改写了 JSON 内容：{str(value)[:100]}")
    return issues


def audit_report(data, ranked=None, md=None, html_text=None):
    result = audit_json(data, ranked)
    issues = result["issues"]
    if not any(i["severity"] == "FAIL" for i in issues):
        if md is not None:
            issues.extend(audit_display(data, md, "MD"))
        if html_text is not None:
            issues.extend(audit_display(data, html_text, "HTML"))
    status = "FAIL" if any(i["severity"] == "FAIL" for i in issues) else "WARN" if issues else "PASS"
    return {"schema_version": "4.0", "overall_status": status, "json_sha256": fingerprint(data),
            "checked_formats": [k for k, v in (("md", md), ("html", html_text)) if v is not None],
            "counts": result["counts"], "issues": issues,
            "limitations": ["机械检查不替代 Agent 对事实、来源独立性与推理的核验。"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", required=True)
    parser.add_argument("--ranked", required=True)
    parser.add_argument("--md")
    parser.add_argument("--html")
    parser.add_argument("--output", "-o", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    try:
        paths = [Path(p).resolve() for p in (args.json, args.ranked, args.md, args.html, args.output) if p]
        if len(paths) != len(set(paths)):
            raise ValueError("输入与输出路径不得重合")
        data = json.loads(Path(args.json).read_text(encoding="utf-8"))
        ranked = json.loads(Path(args.ranked).read_text(encoding="utf-8"))["ranked_events"]
        md = Path(args.md).read_text(encoding="utf-8") if args.md else None
        html_text = Path(args.html).read_text(encoding="utf-8") if args.html else None
        report = audit_report(data, ranked, md, html_text)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report = {"overall_status": "FAIL", "issues": [{"severity": "FAIL", "code": "INPUT_ERROR", "message": str(exc)}]}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"权威 JSON 审核：{report['overall_status']}", file=sys.stderr)
    return 1 if report["overall_status"] == "FAIL" or (args.strict and report["overall_status"] == "WARN") else 0


if __name__ == "__main__":
    raise SystemExit(main())
