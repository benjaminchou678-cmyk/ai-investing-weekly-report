#!/usr/bin/env python3
"""Editorial pass: compress signal into the authoritative final_weekly_report.json.

Contract (v3):
- final_weekly_report.json is the SINGLE source of truth.
- final_weekly_report.md and final_weekly_report.html are RENDERINGS of that JSON
  and must not regenerate content.
- Publishable theses are dynamic 0-3 (never padded to 3).
- Back-end boards (产品/组织/投融资/政策/算力/...) are labels only, not a quota.
- Candidate pool is preserved in layers for human judgement:
    core_events (>=80) / watchlist (50-64, 3-5) /
    editorial_candidate_pool (65-79 held back) /
    human_review_queue (date- or independence-unknown) /
    appendix_events (<50) / excluded_events.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

CORE_MIN = 80
POSSIBLE_CORE_MIN = 65
WATCH_MIN = 50
MAX_CORE = 7
MIN_CORE_TARGET = 5
WATCH_MIN_TARGET = 3
WATCH_MAX_TARGET = 5
CARD_MIN = 150
CARD_MAX = 250


def _assign_thesis_links(theses: list[dict]) -> dict[str, str]:
    """Map cluster_id -> thesis title (short label)."""
    mapping: dict[str, str] = {}
    for t in theses:
        for ev in t.get("key_evidence", []):
            mapping[ev["cluster_id"]] = t.get("theme", t["thesis_id"])
    return mapping


def _independence_unknown(ev: dict) -> bool:
    """An event whose source independence cannot be verified goes to the human
    review queue instead of silently passing the independent-evidence gate."""
    status = ev.get("independence_status", "")
    if status == "unknown":
        return True
    groups = {g for g in ev.get("independence_groups", []) if g}
    return not groups


def select_core_events(ranked: list[dict], thesis_event_ids: set[str]) -> tuple[list[dict], str]:
    """Pick core events from tier=core (>=80) only.

    We do NOT silently pad with possible_core (65-79) to hit 5: those events are
    preserved in editorial_candidate_pool for human judgement instead. If fewer
    than 5 clear the core bar, that is disclosed explicitly rather than padded.
    """
    core = [e for e in ranked if e["importance_score"] >= CORE_MIN]
    note = ""
    if len(core) < MIN_CORE_TARGET:
        note = (
            f"本周达到核心阈值(≥{CORE_MIN})的事件为{len(core)}个，低于建议{MIN_CORE_TARGET}个；"
            f"宁缺毋滥，未用 possible_core(65-79) 自动补满，剩余候选保留在 editorial_candidate_pool 供人工判断。"
        )
    core = core[:MAX_CORE]
    return core, note


def select_watchlist(watchlist_in: list[dict], ranked: list[dict], core_ids: set[str]) -> list[dict]:
    out = [w for w in watchlist_in if w.get("event_cluster_id") not in core_ids]
    if len(out) < WATCH_MIN_TARGET:
        extra = [
            e for e in ranked
            if WATCH_MIN <= e["importance_score"] < POSSIBLE_CORE_MIN
            and e["cluster_id"] not in core_ids
        ]
        extra.sort(key=lambda x: x["importance_score"], reverse=True)
        existing = {w["event_cluster_id"] for w in out}
        for e in extra:
            if len(out) >= WATCH_MIN_TARGET:
                break
            if e["cluster_id"] in existing:
                continue
            out.append({
                "watch_id": f"watch-{len(out)+1}",
                "title": e.get("representative_title", ""),
                "board": e.get("board", ""),
                "score": e["importance_score"],
                "reason": "50-64 Watchlist",
                "event_cluster_id": e["cluster_id"],
            })
    return out[:WATCH_MAX_TARGET]


def _editorial_why(ev: dict) -> str:
    """Reader-facing 'why it matters' derived from tier + board + top signals
    (never dumps raw scoring reasons)."""
    board = ev.get("board", "")
    score = ev["importance_score"]
    signals: list[str] = []
    text = f"{ev.get('representative_title','')} {ev.get('summary','')}"
    if re.search(r"模型|架构|Agent|API|产品", text):
        signals.append("影响产品能力或企业采用")
    if re.search(r"融资|估值|IPO|上市|轮|收购", text):
        signals.append("改变资本与竞争格局")
    if re.search(r"规划|政策|监管|算力|芯片", text):
        signals.append("影响供给侧与合规成本")
    if re.search(r"客户|收入|定价|降价|订单", text):
        signals.append("关联商业化进展")
    if not signals:
        signals.append("属于本周需关注的变动")
    tail = "；".join(signals[:2])
    if score >= 80:
        return f"核心级事件，{tail}，可能改变板块假设。"
    if score >= 65:
        return f"重要事件，{tail}，但证据尚待补强。"
    return f"观察级事件，{tail}，暂不改变假设。"


def build_card(ev: dict, thesis_link: str) -> str:
    """Compose a 150-250 char event card: what/new/why/related thesis."""
    title = ev.get("representative_title", "")
    summary = ev.get("summary", "")
    companies = "、".join(ev.get("companies", [])[:3])
    board = ev.get("board", "")
    happened = f"【{board}】{title}"
    if companies:
        happened += f"（{companies}）"
    new_change = f"真正新变化：{summary}" if summary else "真正新变化：以原始来源披露为准。"
    why = f"为什么重要：{_editorial_why(ev)}"
    related = f"关联判断：{thesis_link}" if thesis_link else "关联判断：独立事件。"

    card = "。".join([happened, new_change, why, related]).replace("。。", "。")
    if len(card) > CARD_MAX:
        card = card[: CARD_MAX - 1] + "…"
    return card


def build_one_liner(theses: list[dict], core_events: list[dict]) -> str:
    """Compose a 50–80 character weekly thesis without truncating event names."""
    if theses:
        t = theses[0]
        theme = t.get("theme", "")
        evidence = t.get("key_evidence", [])
        companies: list[str] = []
        for ev in evidence:
            for c in ev.get("companies", [])[:1]:
                if c not in companies:
                    companies.append(c)
        co = "、".join(companies[:3])
        text = f"本周主线：{co}等信号集中指向{theme}，资本与能力竞争同步加码。"
    elif core_events:
        title = core_events[0].get("representative_title", "").strip()
        text = (
            f"本周高优先级变化集中于{title}。但跨事件与独立经营证据仍不足，"
            "暂不升格为结构性判断。"
        )
    else:
        text = "本周未形成达到证据门槛的产业判断，现有信号均留在观察池，等待新增事实与独立证据。"

    if len(text) < 50:
        text += "后续重点验证客户采用、商业化进展和持续性。"
    if len(text) > 80:
        prefix = text[:80]
        stops = [prefix.rfind(mark) for mark in "。；，"]
        cut = max(stops)
        if cut >= 49:
            text = prefix[: cut + 1]
        else:
            text = prefix[:79].rstrip("，。；、 ") + "…"
    return text


def render_markdown(final: dict) -> str:
    lines: list[str] = []
    meta = final["report_meta"]
    lines.append(f"# AI 投资周报 · {meta['week_label']}")
    lines.append("")
    lines.append(f"> {final['weekly_lead']}")
    lines.append("")
    if final.get("quality_status", {}).get("core_note"):
        lines.append(f"> 编辑说明：{final['quality_status']['core_note']}")
        lines.append("")

    lines.append("## 本周产业判断")
    lines.append("")
    n_thesis = len(final["theses"])
    lines.append(f"> 本周形成 {n_thesis} 条可发布判断。")
    lines.append("")
    if n_thesis == 0:
        lines.append("本周未形成达到证据门槛的产业判断（跨事件独立证据不足，不凑数）。")
        lines.append("")
    for t in final["theses"]:
        boards = "、".join(t.get("related_boards", []))
        lines.append(f"### 判断｜{t.get('theme', t['thesis_id'])}（置信度：{t['confidence']}）")
        lines.append("")
        lines.append(f"- 主张：{t['statement']}")
        lines.append(f"- 核心变化：{t['structural_change']}")
        lines.append("- 关键证据：" + "；".join(
            f"{e['title']}（{e['score']}）" for e in t["key_evidence"]
        ))
        lines.append(f"- 为什么重要：{t['why_it_matters']}")
        lines.append(f"- Investment Readthrough：{t['investment_readthrough']}")
        lines.append(f"- 反方证据：{t['counter_evidence']}")
        lines.append(f"- 推翻条件：{t['falsification_conditions']}")
        if boards:
            lines.append(f"- 关联板块：{boards}")
        lines.append("")

    lines.append("## 本周最重要的事件")
    lines.append("")
    for ev in final["core_events"]:
        lines.append(f"**{ev['title']}**（{ev['score']} / {ev['tier']}）")
        lines.append("")
        lines.append(ev["card"])
        if ev.get("sources"):
            src = " / ".join(f"[{s['url'][:40]}]({s['url']})" for s in ev["sources"][:2])
            lines.append(f"来源：{src}")
        lines.append("")

    lines.append("## Watchlist")
    lines.append("")
    for w in final["watchlist"]:
        lines.append(f"- {w['title']}（{w.get('score','')}）— {w['reason']}")
    if not final["watchlist"]:
        lines.append("无。")
    lines.append("")

    if final.get("human_review_queue"):
        lines.append(f"> 待人工复核：{len(final['human_review_queue'])} 条（日期/独立性未知，见 JSON）。")
        lines.append("")

    lines.append("## Other Updates / Sources")
    lines.append("")
    appendix = final.get("appendix_events", [])
    if appendix:
        lines.append(f"附录（<{WATCH_MIN}，不进正文）：{len(appendix)} 条，完整清单见 final_weekly_report.json。")
    else:
        lines.append("无。")
    lines.append("")
    return "\n".join(lines)


def render_html(final: dict) -> str:
    css = (
        "body{font-family:-apple-system,'PingFang SC',sans-serif;max-width:760px;margin:2rem auto;"
        "padding:0 1rem;color:#222;line-height:1.6}"
        "h1{font-size:1.6rem}h2{margin-top:2rem;border-bottom:1px solid #ddd;padding-bottom:.3rem}"
        "h3{margin-top:1.4rem}blockquote{border-left:3px solid #444;padding-left:.8rem;color:#555}"
        "code{background:#f4f4f4;padding:.1rem .3rem;border-radius:3px}"
    )
    meta = final["report_meta"]
    parts = [
        "<!doctype html>",
        "<html lang='zh-CN'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1, viewport-fit=cover'>",
        "<link rel=\"icon\" type=\"image/svg+xml\" href=\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%231f4f6f'/%3E%3Cpath d='M18 46L29 16h7l11 30h-7l-2-7H27l-2 7zM29 33h7l-3.5-11z' fill='white'/%3E%3C/svg%3E\">",
        f"<title>AI 投资周报 · {html.escape(meta['week_label'])}</title>",
        f"<style>{css}</style></head><body>",
        f"<h1>AI 投资周报 · {html.escape(meta['week_label'])}</h1>",
        f"<blockquote>{html.escape(final['weekly_lead'])}</blockquote>",
    ]
    note = final.get("quality_status", {}).get("core_note")
    if note:
        parts.append(f"<blockquote><em>编辑说明：{html.escape(note)}</em></blockquote>")

    parts.append(f"<h2>本周产业判断（{len(final['theses'])} 条）</h2>")
    if not final["theses"]:
        parts.append("<p>本周未形成达到证据门槛的产业判断。</p>")
    for t in final["theses"]:
        parts.append(f"<h3>{html.escape(t.get('theme', t['thesis_id']))}（置信度：{html.escape(t['confidence'])}）</h3><ul>")
        for label, key in [("主张", "statement"), ("核心变化", "structural_change"),
                           ("为什么重要", "why_it_matters"), ("Investment Readthrough", "investment_readthrough"),
                           ("反方证据", "counter_evidence"), ("推翻条件", "falsification_conditions")]:
            parts.append(f"<li><b>{label}</b>：{html.escape(t[key])}</li>")
        ev_str = "；".join(f"{e['title']}（{e['score']}）" for e in t["key_evidence"])
        parts.append(f"<li><b>关键证据</b>：{html.escape(ev_str)}</li>")
        boards = "、".join(t.get("related_boards", []))
        if boards:
            parts.append(f"<li><b>关联板块</b>：{html.escape(boards)}</li>")
        parts.append("</ul>")

    parts.append("<h2>本周最重要的事件</h2>")
    for ev in final["core_events"]:
        parts.append(f"<h3>{html.escape(ev['title'])}（{ev['score']} / {html.escape(ev['tier'])}）</h3>")
        parts.append(f"<p>{html.escape(ev['card'])}</p>")

    parts.append("<h2>Watchlist</h2><ul>")
    for w in final["watchlist"]:
        parts.append(f"<li>{html.escape(w['title'])} — {html.escape(w['reason'])}</li>")
    if not final["watchlist"]:
        parts.append("<li>无。</li>")
    parts.append("</ul>")
    parts.append("</body></html>")
    return "\n".join(parts)


def editorial_pass(
    ranked: list[dict],
    theses: list[dict],
    watchlist_in: list[dict],
    week_label: str,
) -> tuple[dict, dict]:
    thesis_event_ids = set()
    for t in theses:
        for ev in t.get("key_evidence", []):
            thesis_event_ids.add(ev["cluster_id"])

    core_events, core_note = select_core_events(ranked, thesis_event_ids)
    core_ids = {e["cluster_id"] for e in core_events}
    watchlist = select_watchlist(watchlist_in, ranked, core_ids)
    watch_ids = {w["event_cluster_id"] for w in watchlist}

    link_map = _assign_thesis_links(theses)
    cards = []
    for ev in core_events:
        cards.append({
            "cluster_id": ev["cluster_id"],
            "title": ev["representative_title"],
            "score": ev["importance_score"],
            "tier": ev["tier"],
            "card": build_card(ev, link_map.get(ev["cluster_id"], "")),
            "sources": ev.get("sources", []),
        })

    # Layered candidate pool (preserved for human judgement, not deleted).
    used_ids = core_ids | watch_ids | thesis_event_ids
    editorial_candidate_pool = [
        {
            "cluster_id": e["cluster_id"],
            "title": e["representative_title"],
            "score": e["importance_score"],
            "tier": e["tier"],
            "board": e.get("board", ""),
        }
        for e in ranked
        if POSSIBLE_CORE_MIN <= e["importance_score"] < CORE_MIN and e["cluster_id"] not in used_ids
    ]
    human_review_queue = [
        {
            "cluster_id": e["cluster_id"],
            "title": e.get("representative_title", ""),
            "score": e["importance_score"],
            "reason": "independence_unknown" if _independence_unknown(e) else "needs_review",
        }
        for e in ranked
        if e["cluster_id"] not in used_ids and _independence_unknown(e)
    ]
    appendix = [e for e in ranked if e["importance_score"] < WATCH_MIN]
    excluded: list[dict] = []  # deduped/merged events recorded upstream; none dropped silently here

    one_liner = build_one_liner(theses, core_events)

    thesis_n = len(theses)
    if thesis_n > 3:
        status = "FAIL"
    elif core_note:
        status = "WARN"
    else:
        status = "PASS"
    quality_status = {
        "thesis_count": thesis_n,
        "core_count": len(core_events),
        "watchlist_count": len(watchlist),
        "status": status,
        "core_note": core_note,
    }

    plan = {
        "schema_version": "3.0",
        "pipeline_stage": "weekly_editorial_plan",
        "week_label": week_label,
        "thesis_count": thesis_n,
        "core_count": len(core_events),
        "watchlist_count": len(watchlist),
        "core_note": core_note,
        "core_cluster_ids": sorted(core_ids),
        "watchlist_cluster_ids": [w["event_cluster_id"] for w in watchlist],
        "one_liner": one_liner,
    }
    report = {
        "one_liner": one_liner,
        "theses": theses,
        "core_event_cards": cards,
        "watchlist": watchlist,
        "appendix_events": appendix,
        "editorial_candidate_pool": editorial_candidate_pool,
        "human_review_queue": human_review_queue,
        "excluded_events": excluded,
        "quality_status": quality_status,
    }
    return plan, report


def build_final_report(plan: dict, report: dict, week_meta: dict | None = None) -> dict:
    """Assemble the authoritative final_weekly_report.json (schema v3)."""
    meta = {
        "week_label": plan["week_label"],
        "week_start": (week_meta or {}).get("week_start", ""),
        "week_end": (week_meta or {}).get("week_end", ""),
        "timezone": "Asia/Shanghai",
        "generated_at": (week_meta or {}).get("generated_at", ""),
        "trial_run": (week_meta or {}).get("trial_run", False),
        "profile": (week_meta or {}).get("profile", ""),
    }
    return {
        "schema_version": "3.0",
        "report_meta": meta,
        "weekly_lead": report["one_liner"],
        "theses": report["theses"],
        "core_events": report["core_event_cards"],
        "watchlist": report["watchlist"],
        "editorial_candidate_pool": report["editorial_candidate_pool"],
        "human_review_queue": report["human_review_queue"],
        "appendix_events": report["appendix_events"],
        "excluded_events": report["excluded_events"],
        "source_audit": {},
        "quality_status": report["quality_status"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ranked", help="ranked events JSON")
    parser.add_argument("theses", help="candidate theses JSON")
    parser.add_argument("--week-label", default="YYYY-MM-DD—YYYY-MM-DD")
    parser.add_argument("--plan-out", required=True)
    parser.add_argument("--json-out", default="", help="authoritative final_weekly_report.json")
    parser.add_argument("--md-out", required=True)
    parser.add_argument("--html-out", required=True)
    args = parser.parse_args()

    ranked_data = json.loads(Path(args.ranked).read_text(encoding="utf-8"))
    theses_data = json.loads(Path(args.theses).read_text(encoding="utf-8"))

    plan, report = editorial_pass(
        ranked_data.get("ranked_events", []),
        theses_data.get("candidate_theses", []),
        theses_data.get("watchlist", []),
        args.week_label,
    )

    final = build_final_report(plan, report)

    Path(args.plan_out).write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Markdown / HTML are rendered from the SAME authoritative JSON.
    Path(args.md_out).write_text(render_markdown(final), encoding="utf-8")
    Path(args.html_out).write_text(render_html(final), encoding="utf-8")
    print(
        f"Editorial: theses={plan['thesis_count']} core={plan['core_count']} watch={plan['watchlist_count']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
