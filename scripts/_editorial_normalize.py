#!/usr/bin/env python3
"""Canonicalize raw_articles from multiple source shapes into one internal schema.

Supports both:
- Rich normalized candidates (``items`` with structured ``sources``, ``board``, ...)
- Compact merged-candidates (``events`` with ``cat``/``role``/``materiality``/URL-list sources)

This module is content-layer only; it does not touch the source endpoint registry.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from _candidate_io import first_value, as_list, text_value, stable_id


def _read_items(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read JSON, accepting both ``items`` and ``events`` wrappers (compact demo shape)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)], {}
    if not isinstance(data, dict):
        return [], {}
    for key in ("items", "events", "news", "results", "articles", "entries", "list"):
        v = data.get(key)
        if isinstance(v, list):
            return [d for d in v if isinstance(d, dict)], {k: vv for k, vv in data.items() if k != key}
    if isinstance(data.get("data"), list):
        return [d for d in data["data"] if isinstance(d, dict)], {}
    return [data], {}


CAT_TO_BOARD = {
    "product": "产品与模型",
    "model": "产品与模型",
    "产品": "产品与模型",
    "org": "组织与人事",
    "people": "组织与人事",
    "组织": "组织与人事",
    "funding": "投融资",
    "capital": "投融资",
    "融资": "投融资",
}

ROLE_TO_VERIFICATION = {
    "stakeholder": "company_disclosure",
    "company": "company_disclosure",
    "official": "verified_primary",
    "media": "media_report",
    "regulator": "regulator_disclosure",
    "analyst": "independent_media",
}

MATERIALITY_ALIAS = {
    "high": "high",
    "hi": "high",
    "med": "medium",
    "medium": "medium",
    "mid": "medium",
    "low": "low",
    "unrated": "unrated",
    "": "unrated",
}

VERSION_TOKEN_RE = re.compile(
    r"(?:v|V)?\d+(?:\.\d+){1,3}"          # v4.1, K2.8, 5.0, 3.14
    r"|[A-Z]?\d+\.[A-Za-z]?\d+[A-Za-z]?"   # K2.8, GPT-4o
    r"|[A-Z]{1,3}-\d+(?:\.\d+)?",          # TPU-v5
    flags=re.IGNORECASE,
)
ROUND_TOKEN_RE = re.compile(
    r"(?:series\s*[A-E]\+?|[A-E]\s*轮(?:次)?|pre-?[A-E]\s*轮?|seed|angel|天使轮|A\+?轮|B\+?轮|C\+?轮|D\+?轮|E\+?轮|F\+?轮|Pre-?IPO|ipo|收购|并购|战略融资)",
    flags=re.IGNORECASE,
)
MONEY_TOKEN_RE = re.compile(r"\$?\s?\d+(?:\.\d+)?\s?[BM亿万亿]|€\s?\d+|£\s?\d+", flags=re.IGNORECASE)


def _domain_from_url(url: str) -> str:
    m = re.search(r"https?://(?:www\.)?([^/]+)", url or "")
    return m.group(1).lower() if m else ""


def _norm_sources(raw_sources: Any) -> list[dict[str, Any]]:
    """Normalize sources (list of dict OR list of URL strings) to canonical dicts."""
    out: list[dict[str, Any]] = []
    if not raw_sources:
        return out
    if isinstance(raw_sources, str):
        raw_sources = [raw_sources]
    for i, s in enumerate(raw_sources):
        if isinstance(s, dict):
            url = text_value(s.get("url", ""))
            ig = text_value(s.get("independence_group", "")) or _domain_from_url(url) or f"src{i}"
            out.append({
                **s,
                "source_id": text_value(s.get("source_id", "")) or f"s{i}",
                "name": text_value(s.get("name", "")),
                "url": url,
                "source_type": text_value(s.get("source_type", "")),
                "independence_group": ig,
            })
        else:
            url = text_value(s)
            ig = _domain_from_url(url) or f"src{i}"
            out.append({
                "source_id": f"u{i}",
                "name": _domain_from_url(url),
                "url": url,
                "source_type": "",
                "independence_group": ig,
            })
    return out


def canonicalize_article(raw: dict[str, Any]) -> dict[str, Any]:
    """Turn one raw article/event into the canonical internal shape."""
    title = text_value(raw.get("title", ""))
    url = text_value(first_value(raw, "url", "link", default=""))

    # board
    board = text_value(raw.get("board", ""))
    if not board:
        cat = text_value(raw.get("cat", "")).lower()
        board = CAT_TO_BOARD.get(cat, CAT_TO_BOARD.get(cat, ""))
    if not board:
        et = text_value(raw.get("event_type", ""))
        board = CAT_TO_BOARD.get(et, "")
    if not board:
        board = "其他"

    # companies
    companies = as_list(raw.get("companies", ""))
    if not companies:
        src_name = text_value(raw.get("src", "")) or text_value(raw.get("source", ""))
        if src_name:
            companies = [src_name]

    # dates
    event_date = text_value(raw.get("event_date", ""))
    if not event_date:
        event_date = text_value(raw.get("date", ""))[:10]
    published = text_value(raw.get("published_at", ""))

    # materiality
    mat = text_value(raw.get("materiality", "")).lower()
    materiality = MATERIALITY_ALIAS.get(mat, "unrated")

    # verification
    verif = text_value(raw.get("verification_status", ""))
    if not verif:
        role = text_value(raw.get("role", "")).lower()
        verif = ROLE_TO_VERIFICATION.get(role, "unverified")

    sources = _norm_sources(raw.get("sources", ""))
    independence_groups = sorted({s["independence_group"] for s in sources if s.get("independence_group")})

    summary = text_value(raw.get("summary", ""))

    return {
        **raw,
        "id": text_value(raw.get("id", "")) or stable_id(title, url),
        "title": title,
        "url": url,
        "board": board,
        "companies": companies,
        "event_date": event_date,
        "published_at": published,
        "materiality": materiality,
        "verification_status": verif,
        "entity_type": text_value(raw.get("entity_type", "")),
        "event_type": text_value(raw.get("event_type", "")),
        "summary": summary,
        "sources": sources,
        "independence_groups": independence_groups,
        "business_signals": as_list(raw.get("business_signals", "")),
        "signal_level": text_value(raw.get("signal_level", "")),
        "time_horizon": text_value(raw.get("time_horizon", "")),
    }


def load_raw_articles(path: str | Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    items, meta = _read_items(Path(path))
    canon = [canonicalize_article(it) for it in items]
    return canon, meta


def version_tokens(title: str) -> set[str]:
    return {m.group(0).lower() for m in VERSION_TOKEN_RE.finditer(title or "")}


def round_tokens(title: str) -> set[str]:
    return {m.group(0).lower() for m in ROUND_TOKEN_RE.finditer(title or "")}


def money_tokens(title: str) -> set[str]:
    return {m.group(0).lower().replace(" ", "") for m in MONEY_TOKEN_RE.finditer(title or "")}
