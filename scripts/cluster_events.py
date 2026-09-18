#!/usr/bin/env python3
"""Cluster raw_articles into event_clusters (conservative merge policy).

Rules:
- Merge only when: shared company + title similarity + date within window + same event topic.
- Date participates in the merge decision (not just title).
- Conservative: same company, same day but DIFFERENT product / funding round /
  model version / dollar figure must NOT be merged.
- On merge, union source_ids / independence_groups / dates and update earliest/latest.
- Output standard event fields: summary / what_is_new / why_it_matters / sources /
  related_events.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from _editorial_normalize import (
    load_raw_articles,
    version_tokens,
    round_tokens,
    money_tokens,
)


def normalized_title(t: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (t or "").lower())


def title_similarity(a: str, b: str) -> float:
    """Jaccard over character bigrams (Chinese-friendly)."""
    na, nb = normalized_title(a), normalized_title(b)
    sa = {na[i:i+2] for i in range(len(na) - 1)}
    sb = {nb[i:i+2] for i in range(len(nb) - 1)}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _parse_date(s: str) -> Any:
    try:
        return datetime.strptime((s or "")[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def titles_diverge(a_title: str, b_title: str) -> bool:
    """Return True when the two titles clearly describe DIFFERENT sub-events
    (different product version, funding round, deal size). Used to block over-merging."""
    av, bv = version_tokens(a_title), version_tokens(b_title)
    if av and bv and av.isdisjoint(bv):
        return True
    ar, br = round_tokens(a_title), round_tokens(b_title)
    if ar and br and ar.isdisjoint(br):
        return True
    am, bm = money_tokens(a_title), money_tokens(b_title)
    if am and bm and am.isdisjoint(bm):
        # Two distinct dollar figures in the same week for the same company usually
        # mean two different deals (e.g. $1B equity vs $3B convertible) -> don't merge.
        return True
    return False


def _make_cluster(cluster_id: str, art: dict[str, Any]) -> dict[str, Any]:
    return {
        "cluster_id": cluster_id,
        "representative_title": art["title"],
        "articles": [art["id"]],
        "all_titles": [art["title"]],
        "companies": list(art["companies"]),
        "board": art["board"],
        "event_type": art["event_type"],
        "dates": [d for d in [art["event_date"]] if d],
        "earliest_date": art["event_date"],
        "latest_date": art["event_date"],
        "source_ids": [s["source_id"] for s in art["sources"]],
        "source_urls": [s["url"] for s in art["sources"] if s["url"]],
        "independence_groups": list(art["independence_groups"]),
        "summaries": [s for s in [art["summary"]] if s],
        "representative_summary": art["summary"],
    }


def _merge_into(cl: dict[str, Any], art: dict[str, Any]) -> None:
    cl["articles"].append(art["id"])
    cl["all_titles"].append(art["title"])
    cl["companies"] = sorted(set(cl["companies"]) | set(art["companies"]))
    for s in art["sources"]:
        if s["source_id"] not in cl["source_ids"]:
            cl["source_ids"].append(s["source_id"])
        if s["url"] and s["url"] not in cl["source_urls"]:
            cl["source_urls"].append(s["url"])
    cl["independence_groups"] = sorted(set(cl["independence_groups"]) | set(art["independence_groups"]))
    if art["event_date"]:
        if art["event_date"] not in cl["dates"]:
            cl["dates"].append(art["event_date"])
        cl["dates"].sort()
        cl["earliest_date"] = cl["dates"][0]
        cl["latest_date"] = cl["dates"][-1]
    if art["summary"] and art["summary"] not in cl["summaries"]:
        cl["summaries"].append(art["summary"])
    # Keep the higher-materiality / longest title as representative, but only if topic still matches
    if art["materiality"] == "high" and cl.get("_rep_materiality") != "high":
        cl["representative_title"] = art["title"]
        cl["representative_summary"] = art["summary"]
    cl["_rep_materiality"] = "high" if cl.get("_rep_materiality") == "high" or art["materiality"] == "high" else ""


def _should_merge(cl: dict[str, Any], art: dict[str, Any], window_days: int) -> bool:
    # Must share at least one company (unless both have no company -> skip merging)
    cl_companies = set(cl["companies"])
    art_companies = set(art["companies"])
    if not cl_companies or not art_companies:
        return False
    if not (cl_companies & art_companies):
        return False

    # Date participation: must be within window_days
    d1 = _parse_date(cl["latest_date"])
    d2 = _parse_date(art["event_date"])
    if d1 and d2:
        if abs((d1 - d2).days) > window_days:
            return False
    else:
        # Missing date -> be conservative, only merge on very strong title match
        if title_similarity(cl["representative_title"], art["title"]) < 0.75:
            return False

    # Same board / event topic
    if cl["board"] != art["board"] and cl["board"] and art["board"]:
        # Allow cross-board only if title is extremely close (rare)
        if title_similarity(cl["representative_title"], art["title"]) < 0.85:
            return False

    # Title similarity threshold
    sim = title_similarity(cl["representative_title"], art["title"])
    if sim < 0.45:
        return False

    # Conservative guard: different product version / round / deal size -> never merge
    if titles_diverge(cl["representative_title"], art["title"]):
        return False

    return True


def cluster_articles(articles: list[dict[str, Any]], window_days: int = 2) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    assigned: set[str] = set()

    for art in articles:
        aid = art["id"]
        if aid in assigned:
            continue

        best_cluster = None
        best_sim = 0.0
        for cl in clusters:
            if aid in cl["articles"]:
                continue
            if not _should_merge(cl, art, window_days):
                continue
            sim = title_similarity(cl["representative_title"], art["title"])
            if sim > best_sim:
                best_sim = sim
                best_cluster = cl

        if best_cluster is not None:
            _merge_into(best_cluster, art)
            assigned.add(aid)
        else:
            cl = _make_cluster(f"cluster-{len(clusters)+1:03d}", art)
            clusters.append(cl)
            assigned.add(aid)

    # Finalize standard event fields + related_events
    by_company: dict[str, list[str]] = {}
    for cl in clusters:
        for c in cl["companies"]:
            by_company.setdefault(c, []).append(cl["cluster_id"])

    out: list[dict[str, Any]] = []
    for cl in clusters:
        related = sorted({rid for c in cl["companies"] for rid in by_company.get(c, []) if rid != cl["cluster_id"]})
        sources = [{"url": u} for u in cl["source_urls"]]
        summary = cl["representative_summary"] or "；".join(cl["summaries"])[:200]
        out.append({
            "cluster_id": cl["cluster_id"],
            "representative_title": cl["representative_title"],
            "companies": cl["companies"],
            "board": cl["board"],
            "event_type": cl["event_type"],
            "dates": cl["dates"],
            "earliest_date": cl["earliest_date"],
            "latest_date": cl["latest_date"],
            "source_ids": cl["source_ids"],
            "independence_groups": cl["independence_groups"],
            "article_ids": cl["articles"],
            "all_titles": cl["all_titles"],
            "summary": summary,
            "what_is_new": summary,
            "why_it_matters": "",  # filled by editorial pass / model
            "sources": sources,
            "related_events": related,
        })
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="raw articles / merged candidates JSON")
    parser.add_argument("--output", "-o", required=True)
    parser.add_argument("--window-days", type=int, default=2)
    args = parser.parse_args()

    articles, meta = load_raw_articles(args.input)
    clusters = cluster_articles(articles, window_days=args.window_days)

    out = {
        "schema_version": "2.0",
        "pipeline_stage": "event_clusters",
        "cluster_count": len(clusters),
        "article_count": len(articles),
        "clusters": clusters,
    }
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Clustered {len(articles)} articles into {len(clusters)} event clusters", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
