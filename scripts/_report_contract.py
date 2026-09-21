"""周报分流、内容契约和渲染字段；不承担 Agent 的事实判断。"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

LAYERS = ("core_events", "watchlist", "editorial_candidate_pool", "human_review_queue", "appendix_events", "excluded_events")
THESIS_FIELDS = (("主张", "statement"), ("核心变化", "structural_change"),
                 ("为什么重要", "why_it_matters"), ("Investment Readthrough", "investment_readthrough"),
                 ("反方证据", "counter_evidence"), ("推翻条件", "falsification_conditions"))
EVENT_FIELDS = (("发生了什么", "what_happened"), ("真正新变化", "what_is_new"),
                ("为什么重要", "why_it_matters"))
SHANGHAI = ZoneInfo("Asia/Shanghai")


def event_id(event: dict) -> str:
    return str(event.get("cluster_id") or event.get("event_cluster_id") or event.get("event_id") or "")


def date_in_shanghai(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=SHANGHAI)).astimezone(SHANGHAI).date()
    except (ValueError, TypeError):
        return None


def week_meta(start: str, end: str) -> dict:
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    if b < a:
        raise ValueError("week_end 不能早于 week_start")
    return {"week_start": start, "week_end": end, "week_label": f"{start}—{end}",
            "timezone": "Asia/Shanghai", "generated_at": datetime.now(SHANGHAI).isoformat()}


AUTO_REVIEW_REASONS = {"date_unknown", "out_of_window", "independence_unknown", "identity_unverified",
                       "evidence_requires_review", "signal_unrated", "signal_reason_missing", "signal_conflict"}


def review_reasons(event: dict, meta: dict | None = None) -> list[str]:
    # 自动原因依据当前字段重算；Agent 修正字段后无需手工清理旧标记。
    reasons = [r for r in event.get("review_reasons", []) if r not in AUTO_REVIEW_REASONS]
    dates = event.get("dates") or [event.get("event_date") or event.get("published_at") or event.get("earliest_date")]
    parsed = [date_in_shanghai(d) for d in dates]
    if event.get("date_status") == "unknown" or not parsed or any(d is None for d in parsed):
        reasons.append("date_unknown")
    elif meta and not any(date.fromisoformat(meta["week_start"]) <= d <= date.fromisoformat(meta["week_end"]) for d in parsed):
        reasons.append("out_of_window")
    if event.get("independence_status") == "unknown" or not any(event.get("independence_groups", [])):
        reasons.append("independence_unknown")
    if event.get("identity_status") in {"unknown", "mismatch", "unverified"}:
        reasons.append("identity_unverified")
    if event.get("verification_status", "unverified") in {"", "unverified", "conflicting"}:
        reasons.append("evidence_requires_review")
    if event.get("signal_level", "unrated") == "unrated":
        reasons.append("signal_unrated")
    elif not str(event.get("signal_reason", "")).strip():
        reasons.append("signal_reason_missing")
    return list(dict.fromkeys(reasons))


def fingerprint(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def source_links(event: dict) -> list[tuple[str, str]]:
    links = []
    for source in event.get("sources", []):
        if not isinstance(source, dict):
            continue
        url = str(source.get("original_url") or source.get("url") or "").strip()
        if url:
            links.append((str(source.get("name") or source.get("source_id") or "来源"), url))
    return list(dict.fromkeys(links))


def safe_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"https", "http"} and bool(parsed.netloc) and not any(c.isspace() for c in url)


def all_events(final: dict) -> dict[str, dict]:
    return {event_id(e): e for layer in LAYERS for e in final.get(layer, [])}


def evidence_events(final: dict, thesis: dict) -> list[dict]:
    events = all_events(final)
    return [events[e["cluster_id"]] for e in thesis["key_evidence"]]


def public_events(final: dict) -> list[dict]:
    """正文事件及仅作为判断证据的备选事件也必须显示来源。"""
    out = final["core_events"] + final["watchlist"]
    ids = {event_id(e) for e in out}
    for thesis in final["theses"]:
        for event in evidence_events(final, thesis):
            if event_id(event) not in ids:
                out.append(event)
                ids.add(event_id(event))
    return out
