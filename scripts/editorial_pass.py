#!/usr/bin/env python3
"""prepare：完整分流待编辑 JSON；render：审计同一 JSON 后纯渲染，不重写 Agent 内容。"""
from __future__ import annotations

import argparse
import copy
import html
import json
import sys
from pathlib import Path

from _report_contract import (LAYERS, THESIS_FIELDS, EVENT_FIELDS, event_id, week_meta, review_reasons,
                              fingerprint, source_links, safe_url, evidence_events, public_events)
from rank_events import clean_legacy, rank_clusters

MAX_CORE = 7
MAX_WATCH = 5


def prepare_report(ranked: list[dict], meta: dict, theses: list[dict] | None = None) -> dict:
    """只准备草稿。先复核分流，再选择正文；溢出和判断证据均保留完整事件。"""
    events = rank_clusters(ranked)
    final = {"schema_version": "4.0", "report_meta": meta, "weekly_lead": "",
             "theses": clean_legacy(theses or []), "input_event_ids": [e["cluster_id"] for e in events],
             **{layer: [] for layer in LAYERS}, "source_audit": {},
             "quality_status": {"editor_reviewed": False, "reviewed_at": "", "sparse_note": "",
                                "zero_thesis_reason": "", "disclosures": []}}
    for event in events:
        ev = copy.deepcopy(event)
        ev["title"] = ev.get("title") or ev.get("representative_title", "")
        reasons = review_reasons(ev, meta)
        if reasons:
            ev["review_reasons"] = reasons
            final["human_review_queue"].append(ev)
        elif ev["signal_level"] == "noise":
            ev["disposition_reason"] = "noise，不进入正文；保留来源池"
            final["appendix_events"].append(ev)
        elif ev["signal_level"] in {"S", "A"} and len(final["core_events"]) < MAX_CORE:
            final["core_events"].append(ev)
        elif ev["signal_level"] == "B" and len(final["watchlist"]) < MAX_WATCH:
            final["watchlist"].append(ev)
        else:
            ev["disposition_reason"] = "未进入正文额度，完整保留供 Agent/人工复选"
            final["editorial_candidate_pool"].append(ev)
    return final


def _md(text) -> str:
    value = str(text)
    for token in ("\\", "`", "*", "_", "[", "]", "<", ">", "#", "|"):
        value = value.replace(token, "\\" + token)
    return value


def render_markdown(final: dict) -> str:
    """只读权威 JSON；不截断、补写或生成任何业务主张。"""
    lines = [f"# AI 投资周报 · {_md(final['report_meta']['week_label'])}", "", _md(final["weekly_lead"]), ""]
    qs = final["quality_status"]
    for note in [qs.get("sparse_note"), *qs.get("disclosures", [])]:
        if note:
            lines += [f"> {_md(note)}", ""]
    lines += ["## 本周产业判断", ""]
    if not final["theses"]:
        lines += [_md(qs["zero_thesis_reason"]), ""]
    for thesis in final["theses"]:
        lines += [f"### 判断｜{_md(thesis['theme'])}", ""]
        for label, key in THESIS_FIELDS:
            lines.append(f"- {label}：{_md(thesis[key])}")
        lines += [f"- 置信度：{thesis['confidence']}", f"- 关联板块：{_md('、'.join(thesis['related_boards']))}"]
        for event in evidence_events(final, thesis):
            lines.append(f"- 关键证据：{_md(event['title'])}（{event['signal_level']}）")
            lines += [f"  - [{_md(name)}](<{url}>)" for name, url in source_links(event) if safe_url(url)]
        lines.append("")
    for heading, layer in (("本周最重要的事件", "core_events"), ("Watchlist", "watchlist")):
        lines += [f"## {heading}", ""]
        if not final[layer]:
            lines += ["无。", ""]
        for event in final[layer]:
            lines += [f"### {_md(event['title'])}（{event['signal_level']}）", ""]
            for label, key in EVENT_FIELDS:
                lines.append(f"- {label}：{_md(event[key])}")
            lines += [f"- 评级理由：{_md(event['signal_reason'])}", f"- 证据状态：{_md(event['verification_status'])}"]
            lines += [f"- 来源：[{_md(name)}](<{url}>)" for name, url in source_links(event) if safe_url(url)]
            lines.append("")
    lines += ["## 编辑候选与来源池", ""]
    for layer in ("editorial_candidate_pool", "human_review_queue", "appendix_events", "excluded_events"):
        lines.append(f"- {layer}：{len(final[layer])} 条，完整记录见权威 JSON。")
    return "\n".join(lines) + "\n"


def render_html(final: dict) -> str:
    esc = lambda value: html.escape(str(value), quote=True)
    def links(event):
        return " / ".join(f'<a href="{esc(url)}">{esc(name)}</a>' for name, url in source_links(event) if safe_url(url))
    parts = ["<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>",
             "<meta name='viewport' content='width=device-width, initial-scale=1'>",
             f"<title>AI 投资周报 · {esc(final['report_meta']['week_label'])}</title>",
             "<style>body{font:16px/1.7 system-ui,sans-serif;max-width:800px;margin:32px auto;padding:0 20px;color:#253244}h2{margin-top:32px;border-bottom:1px solid #ddd}a{color:#167080;overflow-wrap:anywhere}p,li{white-space:pre-wrap;overflow-wrap:anywhere}blockquote{border-left:3px solid #167080;padding-left:12px}</style></head><body>",
             f"<h1>AI 投资周报 · {esc(final['report_meta']['week_label'])}</h1><p>{esc(final['weekly_lead'])}</p>"]
    qs = final["quality_status"]
    for note in [qs.get("sparse_note"), *qs.get("disclosures", [])]:
        if note:
            parts.append(f"<blockquote>{esc(note)}</blockquote>")
    parts.append("<h2>本周产业判断</h2>")
    if not final["theses"]:
        parts.append(f"<p>{esc(qs['zero_thesis_reason'])}</p>")
    for thesis in final["theses"]:
        parts.append(f"<section><h3>{esc(thesis['theme'])}</h3><ul>")
        for label, key in THESIS_FIELDS:
            parts.append(f"<li>{label}：{esc(thesis[key])}</li>")
        parts += [f"<li>置信度：{esc(thesis['confidence'])}</li>", f"<li>关联板块：{esc('、'.join(thesis['related_boards']))}</li>"]
        for event in evidence_events(final, thesis):
            parts.append(f"<li>关键证据：{esc(event['title'])}（{esc(event['signal_level'])}） {links(event)}</li>")
        parts.append("</ul></section>")
    for heading, layer in (("本周最重要的事件", "core_events"), ("Watchlist", "watchlist")):
        parts.append(f"<h2>{heading}</h2>")
        if not final[layer]:
            parts.append("<p>无。</p>")
        for event in final[layer]:
            parts.append(f"<section><h3>{esc(event['title'])}（{esc(event['signal_level'])}）</h3><ul>")
            for label, key in EVENT_FIELDS:
                parts.append(f"<li>{label}：{esc(event[key])}</li>")
            parts += [f"<li>评级理由：{esc(event['signal_reason'])}</li>", f"<li>证据状态：{esc(event['verification_status'])}</li>",
                      f"<li>来源：{links(event)}</li></ul></section>"]
    parts.append("<h2>编辑候选与来源池</h2><ul>")
    for layer in ("editorial_candidate_pool", "human_review_queue", "appendix_events", "excluded_events"):
        parts.append(f"<li>{layer}：{len(final[layer])} 条，完整记录见权威 JSON。</li>")
    parts.append("</ul></body></html>")
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="新建待 Agent 编辑的 JSON；不输出展示文件，不覆盖已有 JSON")
    prepare.add_argument("ranked")
    prepare.add_argument("--theses")
    prepare.add_argument("--week-start", required=True)
    prepare.add_argument("--week-end", required=True)
    prepare.add_argument("--json-out", required=True)
    render = sub.add_parser("render", help="审核已定稿 JSON 后纯渲染，可只输出一种格式")
    render.add_argument("--json", required=True)
    render.add_argument("--md-out")
    render.add_argument("--html-out")
    render.add_argument("--audit-out", required=True)
    render.add_argument("--ranked", required=True, help="核对原始事件集合，防止编辑中遗漏")
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            ranked = json.loads(Path(args.ranked).read_text(encoding="utf-8"))["ranked_events"]
            proposals = json.loads(Path(args.theses).read_text(encoding="utf-8")).get("candidate_theses", []) if args.theses else []
            final = prepare_report(ranked, week_meta(args.week_start, args.week_end), proposals)
            with Path(args.json_out).open("x", encoding="utf-8") as file:
                json.dump(final, file, ensure_ascii=False, indent=2)
                file.write("\n")
            print("已准备待编辑 JSON；Agent 必须完成评级、内容核验与发布审核。")
            return 0
        if not args.md_out and not args.html_out:
            raise ValueError("至少选择 --md-out 或 --html-out；无需同时生成")
        paths = [Path(args.json).resolve(), Path(args.ranked).resolve(), Path(args.audit_out).resolve()]
        paths += [Path(p).resolve() for p in (args.md_out, args.html_out) if p]
        if len(paths) != len(set(paths)):
            raise ValueError("输入、审计和渲染输出路径不得重合")
        from audit_report_structure import audit_report
        final = json.loads(Path(args.json).read_text(encoding="utf-8"))
        ranked = json.loads(Path(args.ranked).read_text(encoding="utf-8"))["ranked_events"]
        qa = audit_report(final, ranked=ranked)
        if qa["overall_status"] == "FAIL":
            Path(args.audit_out).write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print("内容审核失败，未生成展示文件。", file=sys.stderr)
            return 1
        md = render_markdown(final) if args.md_out else None
        html_text = render_html(final) if args.html_out else None
        qa = audit_report(final, ranked=ranked, md=md, html_text=html_text)
        if qa["overall_status"] != "FAIL":
            if args.md_out:
                Path(args.md_out).write_text(md, encoding="utf-8")
            if args.html_out:
                Path(args.html_out).write_text(html_text, encoding="utf-8")
        Path(args.audit_out).write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"同一 JSON 的审核与展示检查：{qa['overall_status']}")
        return 1 if qa["overall_status"] == "FAIL" else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
