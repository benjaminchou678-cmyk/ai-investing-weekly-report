#!/usr/bin/env python3
"""Editorial pass: compress signal into weekly_editorial_plan + final_weekly_report.

Outputs:
- weekly_editorial_plan.json : structured editorial decisions
- final_weekly_report.md      : compressed Markdown report
- final_weekly_report.html   : minimal standalone HTML

Compression targets:
- one-liner 50-80 chars
- publishable theses 1-3 (never padded)
- core events 5-7 (better fewer than padded; explicitly note if <5)
- watchlist 3-5
- event cards 150-250 chars covering: what happened / what's new / why it matters / related thesis
- Other Updates / Sources kept minimal
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


def select_core_events(ranked: list[dict], thesis_event_ids: set[str]) -> tuple[list[dict], str]:
    """Pick 5-7 core events. Prefer tier=core. Fall back to possible_core if needed."""
    core = [e for e in ranked if e["importance_score"] >= CORE_MIN]
    note = ""
    if len(core) < MIN_CORE_TARGET:
        # Pull in highest possible_core (65-79) that are not already theses-only
        filler = [
            e for e in ranked
            if POSSIBLE_CORE_MIN <= e["importance_score"] < CORE_MIN
            and e["cluster_id"] not in thesis_event_ids
        ]
        filler.sort(key=lambda x: x["importance_score"], reverse=True)
        needed = MIN_CORE_TARGET - len(core)
        core = core + filler[:needed]
        if len(core) < MIN_CORE_TARGET:
            note = (
                f"本周达到核心阈值(≥{CORE_MIN})的事件不足{MIN_CORE_TARGET}个，"
                f"实际仅{len(core)}个；宁缺毋滥，不凑数。"
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
        # Keep the leading event title intact. Character slicing here previously
        # produced broken names such as "DeepSeek V4." in the published lead.
        title = core_events[0].get("representative_title", "").strip()
        text = (
            f"本周高优先级变化集中于{title}。但跨事件与独立经营证据仍不足，"
            "暂不升格为结构性判断。"
        )
    else:
        text = "本周未出现达到正文门槛的核心事件，现有信号均留在观察池，等待新增事实与独立证据。"

    if len(text) < 50:
        text += "后续重点验证客户采用、商业化进展和持续性。"
    if len(text) > 80:
        # Prefer a complete clause to an arbitrary mid-token cut.
        prefix = text[:80]
        stops = [prefix.rfind(mark) for mark in "。；，"]
        cut = max(stops)
        if cut >= 49:
            text = prefix[: cut + 1]
        else:
            text = prefix[:79].rstrip("，。；、 ") + "…"
    return text


def render_markdown(plan: dict, report: dict) -> str:
    lines: list[str] = []
    lines.append(f"# AI 投资周报 · {plan['week_label']}")
    lines.append("")
    lines.append(f"> {report['one_liner']}")
    lines.append("")
    if plan.get("core_note"):
        lines.append(f"> 编辑说明：{plan['core_note']}")
        lines.append("")

    lines.append("## 可发布判断")
    lines.append("")
    if not report["theses"]:
        lines.append("本周证据不足以形成可发布判断（见 candidate_theses.note）。")
    for t in report["theses"]:
        lines.append(f"### {t['theme']}（置信度：{t['confidence']}）")
        lines.append("")
        lines.append(f"- 主张：{t['statement']}")
        lines.append(f"- 结构性变化：{t['structural_change']}")
        lines.append(f"- 关键证据：" + "；".join(
            f"{e['title']}（{e['score']}）" for e in t["key_evidence"]
        ))
        lines.append(f"- 为什么重要：{t['why_it_matters']}")
        lines.append(f"- 投资含义：{t['investment_readthrough']}")
        lines.append(f"- 反方证据：{t['counter_evidence']}")
        lines.append(f"- 推翻条件：{t['falsification_conditions']}")
        lines.append("")

    lines.append("## 核心事件")
    lines.append("")
    for ev in report["core_event_cards"]:
        lines.append(f"**{ev['title']}**（{ev['score']} / {ev['tier']}）")
        lines.append("")
        lines.append(ev["card"])
        if ev["sources"]:
            src = " / ".join(f"[{s['url'][:40]}]({s['url']})" for s in ev["sources"][:2])
            lines.append(f"来源：{src}")
        lines.append("")

    lines.append("## Watchlist")
    lines.append("")
    for w in report["watchlist"]:
        lines.append(f"- {w['title']}（{w.get('score','')}）— {w['reason']}")
    lines.append("")

    lines.append("## Other Updates / Sources")
    lines.append("")
    appendix = report.get("appendix_events", [])
    if appendix:
        lines.append(f"附录（<{WATCH_MIN}，不进正文）：{len(appendix)} 条，见 ranked_events 输出。")
    else:
        lines.append("无。")
    lines.append("")
    return "\n".join(lines)


def render_html(plan: dict, report: dict) -> str:
    css = (
        "body{font-family:-apple-system,'PingFang SC',sans-serif;max-width:760px;margin:2rem auto;"
        "padding:0 1rem;color:#222;line-height:1.6}"
        "h1{font-size:1.6rem}h2{margin-top:2rem;border-bottom:1px solid #ddd;padding-bottom:.3rem}"
        "h3{margin-top:1.4rem}blockquote{border-left:3px solid #444;padding-left:.8rem;color:#555}"
        "code{background:#f4f4f4;padding:.1rem .3rem;border-radius:3px}"
    )
    parts = [
        "<!doctype html>",
        "<html lang='zh-CN'><head><meta charset='utf-8'>",
        f"<title>AI 投资周报 · {html.escape(plan['week_label'])}</title>",
        f"<style>{css}</style></head><body>",
        f"<h1>AI 投资周报 · {html.escape(plan['week_label'])}</h1>",
        f"<blockquote>{html.escape(report['one_liner'])}</blockquote>",
    ]
    if plan.get("core_note"):
        parts.append(f"<blockquote><em>编辑说明：{html.escape(plan['core_note'])}</em></blockquote>")

    parts.append("<h2>可发布判断</h2>")
    if not report["theses"]:
        parts.append("<p>本周证据不足以形成可发布判断。</p>")
    for t in report["theses"]:
        parts.append(f"<h3>{html.escape(t['theme'])}（置信度：{html.escape(t['confidence'])}）</h3><ul>")
        for label, key in [("主张", "statement"), ("结构性变化", "structural_change"),
                           ("为什么重要", "why_it_matters"), ("投资含义", "investment_readthrough"),
                           ("反方证据", "counter_evidence"), ("推翻条件", "falsification_conditions")]:
            parts.append(f"<li><b>{label}</b>：{html.escape(t[key])}</li>")
        ev_str = "；".join(f"{e['title']}（{e['score']}）" for e in t["key_evidence"])
        parts.append(f"<li><b>关键证据</b>：{html.escape(ev_str)}</li>")
        parts.append("</ul>")

    parts.append("<h2>核心事件</h2>")
    for ev in report["core_event_cards"]:
        parts.append(f"<h3>{html.escape(ev['title'])}（{ev['score']} / {html.escape(ev['tier'])}）</h3>")
        parts.append(f"<p>{html.escape(ev['card'])}</p>")

    parts.append("<h2>Watchlist</h2><ul>")
    for w in report["watchlist"]:
        parts.append(f"<li>{html.escape(w['title'])} — {html.escape(w['reason'])}</li>")
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

    appendix = [e for e in ranked if e["importance_score"] < WATCH_MIN]

    one_liner = build_one_liner(theses, core_events)

    plan = {
        "schema_version": "2.0",
        "pipeline_stage": "weekly_editorial_plan",
        "week_label": week_label,
        "thesis_count": len(theses),
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
    }
    return plan, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ranked", help="ranked events JSON")
    parser.add_argument("theses", help="candidate theses JSON")
    parser.add_argument("--week-label", default="YYYY-MM-DD—YYYY-MM-DD")
    parser.add_argument("--plan-out", required=True)
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

    Path(args.plan_out).write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(args.md_out).write_text(render_markdown(plan, report), encoding="utf-8")
    Path(args.html_out).write_text(render_html(plan, report), encoding="utf-8")
    print(
        f"Editorial: theses={plan['thesis_count']} core={plan['core_count']} watch={plan['watchlist_count']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
