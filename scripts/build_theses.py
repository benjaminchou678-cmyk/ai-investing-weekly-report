#!/usr/bin/env python3
"""整理 Agent 提出的候选判断；不靠主题模板或评级数量自动生成产业结论。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _report_contract import review_reasons
from rank_events import clean_legacy


def build_theses(ranked: list[dict], proposals: list[dict] | None = None) -> tuple[list[dict], list[dict]]:
    events = {e["cluster_id"]: e for e in ranked}
    theses = clean_legacy(proposals or [])
    if len(theses) > 3:
        raise ValueError("候选判断最多 3 条；不得静默截断 Agent 判断")
    for thesis in theses:
        if not thesis.get("key_evidence"):
            raise ValueError("候选判断需要明确的事件引用")
        for evidence in thesis["key_evidence"]:
            event = events.get(evidence.get("cluster_id"))
            if event is None or review_reasons(event) or event.get("signal_level") in {"noise", "unrated"}:
                raise ValueError("候选判断引用了缺失、待复核或 noise 事件")
    watch = [clean_legacy(e) for e in ranked if e.get("signal_level") == "B" and not review_reasons(e)]
    return theses, watch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ranked")
    parser.add_argument("--agent-theses", help="Agent 已写出的判断 JSON；缺省不生成模板判断")
    parser.add_argument("--output", "-o", required=True)
    args = parser.parse_args()
    try:
        data = json.loads(Path(args.ranked).read_text(encoding="utf-8"))
        proposed = json.loads(Path(args.agent_theses).read_text(encoding="utf-8")) if args.agent_theses else []
        if isinstance(proposed, dict):
            proposed = proposed.get("theses", proposed.get("candidate_theses", []))
        if not isinstance(proposed, list):
            raise ValueError("agent-theses 必须是列表或包含 theses 的对象")
        theses, watch = build_theses(data["ranked_events"], proposed)
        out = {"schema_version": "4.0", "pipeline_stage": "candidate_theses", "candidate_theses": theses,
               "watchlist": watch, "note": "候选判断须由 Agent 在权威 JSON 中完成事实核验与定稿；脚本不代写结论。"}
        Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
