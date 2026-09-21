#!/usr/bin/env python3
"""保留全部事件，按 Agent 的 S/A/B/noise 评级稳定排序；不计算或换算百分制。"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

from _editorial_normalize import load_raw_articles

SIGNAL_LEVELS = ("S", "A", "B", "noise", "unrated")
SIGNAL_ORDER = {level: index for index, level in enumerate(SIGNAL_LEVELS)}
LEGACY_FIELDS = {"importance_score", "score_breakdown", "score_reasons", "score_weights", "tier"}


def clean_legacy(value):
    """保留原始文件，移除新产物中的旧百分制业务字段。"""
    if isinstance(value, dict):
        return {k: clean_legacy(v) for k, v in value.items() if k not in LEGACY_FIELDS}
    if isinstance(value, list):
        return [clean_legacy(v) for v in value]
    return copy.deepcopy(value)


def normalize_signal(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "unrated"
    if text.upper() in {"S", "A", "B"}:
        return text.upper()
    if text.lower() in {"noise", "unrated"}:
        return text.lower()
    raise ValueError(f"非法 signal_level：{value!r}；只能使用 S/A/B/noise/unrated")


def rank_clusters(clusters: list[dict], articles_by_id: dict[str, dict] | None = None) -> list[dict]:
    """事件级评级优先；文章评级一致时继承，冲突时留给 Agent，不自动择高。"""
    articles_by_id = articles_by_id or {}
    ranked = []
    seen = set()
    for cl in clusters:
        cid = cl.get("cluster_id")
        if not cid or cid in seen:
            raise ValueError(f"cluster_id 缺失或重复：{cid!r}")
        seen.add(cid)
        ev = clean_legacy(cl)
        ev.pop("score", None)  # 仅清理事件顶层旧百分制；不删除嵌套事实字段。
        explicit = normalize_signal(cl.get("signal_level", ""))
        reason = str(cl.get("signal_reason") or "").strip()
        arts = [articles_by_id[a] for a in cl.get("article_ids", []) if a in articles_by_id]
        if explicit == "unrated" and arts:
            levels = {normalize_signal(a.get("signal_level", "")) for a in arts}
            levels.discard("unrated")
            if len(levels) == 1:
                explicit = next(iter(levels))
                reasons = list(dict.fromkeys(str(a.get("signal_reason") or "").strip() for a in arts if a.get("signal_reason")))
                reason = "；".join(reasons)
            elif len(levels) > 1:
                ev.setdefault("review_reasons", []).append("signal_conflict")
        ev["signal_level"] = explicit
        ev["signal_reason"] = reason
        ranked.append(ev)
    ranked.sort(key=lambda e: SIGNAL_ORDER[e["signal_level"]])  # 同级保留 Agent 输入顺序
    for index, ev in enumerate(ranked, 1):
        ev["rank"] = index
    return ranked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clusters")
    parser.add_argument("candidates", nargs="?", help="可选：继承已有文章级评级，不推断评级")
    parser.add_argument("--output", "-o", required=True)
    args = parser.parse_args()
    try:
        data = json.loads(Path(args.clusters).read_text(encoding="utf-8"))
        articles = load_raw_articles(args.candidates)[0] if args.candidates else []
        events = rank_clusters(data.get("clusters", data.get("ranked_events", [])), {a["id"]: a for a in articles})
        out = {"schema_version": "4.0", "pipeline_stage": "ranked_events", "rating_method": "agent_signal_level",
               "total_events": len(events), "ranked_events": events}
        Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    print(f"保留 {len(events)} 个事件；按 S/A/B/noise 排序，未评级保留为 unrated。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
