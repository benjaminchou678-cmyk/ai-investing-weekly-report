#!/usr/bin/env python3
"""Run the new content-layer pipeline on demo data and produce old-vs-new metrics.

Old body = verbose full-detail rendering of every event using the legacy template
(assumption table + 3 forced judgments + per-event detailed bullets + priority table).
New body = compressed weekly_editorial_pass output.

Target: body length down 30%-50%.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _run(args: list[str]) -> None:
    r = subprocess.run([sys.executable, *args], cwd=ROOT, text=True, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"cmd failed: {' '.join(args)}\n{r.stderr}")


def old_verbose_body(articles: list[dict]) -> str:
    """Simulate the legacy verbose report body over the same candidate set."""
    lines = ["## 本周投资假设变化", ""]
    lines += ["| 假设 | 变化 | 新增证据 | 反方证据 | 下一催化剂 |", "|---|---|---|---|---|"]
    for a in articles:
        lines.append(f"| {a['title'][:20]} | 强化 | {a.get('summary','')[:20]} | 待验证 | 下周披露 |")
    lines += ["", "## 本周关键判断", ""]
    for dim in ["产品与模型", "组织与人事", "投融资"]:
        lines += [f"### 判断｜{dim}", "", "- 本周最重要的事情：见下文明细。", "- 核心判断：", "- 为什么重要：",
                  "- 直接影响：", "- 二阶影响：", "- 受益者/承压者：", "- 时间范围：", "- 反方证据/推翻条件：",
                  "- 判断置信度：中", "- 未来验证：", "- 来源：", ""]
    lines += ["## 公司研究优先级", "", "| 公司 | 类型 | 本周变化 | 假设影响 | 优先级 | 风险 |", "|---|---|---|---|---|---|"]
    for a in articles:
        co = (a.get("companies") or [""])[0]
        lines.append(f"| {co} | 非上市 | {a['title'][:16]} | 强化 | 中 | 缺独立验证 |")
    lines += ["", "## 本周核心新闻", ""]
    for i, a in enumerate(articles, 1):
        lines += [f"**{i}. {a['title']}** [A]", "", f"- 经营/产品影响：{a.get('summary','')}",
                  "- 产品/商业影响：", "- 与上一代差异：", "- 投资假设：", "- 催化剂：", "- 风险或反证：",
                  "- 证据状态：公司披露", f"- 来源：{a.get('url','')}", ""]
    lines += ["## 上期判断验证", "", "## 未来催化剂", "", "## 证据缺口", "", "## 质量审核", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--demo", default=str(ROOT / "examples/demo-merged-candidates.json"))
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    wd = Path(args.workdir)
    wd.mkdir(parents=True, exist_ok=True)

    clusters = wd / "clusters.json"
    ranked = wd / "ranked.json"
    theses = wd / "theses.json"
    plan = wd / "plan.json"
    md = wd / "final_weekly_report.md"
    htmlout = wd / "final_weekly_report.html"

    _run([str(SCRIPTS / "cluster_events.py"), args.demo, "-o", str(clusters)])
    _run([str(SCRIPTS / "rank_events.py"), str(clusters), args.demo, "-o", str(ranked)])
    _run([str(SCRIPTS / "build_theses.py"), str(ranked), "-o", str(theses)])
    _run([
        str(SCRIPTS / "editorial_pass.py"), str(ranked), str(theses),
        "--week-label", "2026-09-07—2026-09-13",
        "--plan-out", str(plan), "--md-out", str(md), "--html-out", str(htmlout),
    ])

    ranked_d = json.loads(ranked.read_text(encoding="utf-8"))
    theses_d = json.loads(theses.read_text(encoding="utf-8"))
    plan_d = json.loads(plan.read_text(encoding="utf-8"))

    from _editorial_normalize import load_raw_articles  # type: ignore
    # Allow running from repo root
    sys.path.insert(0, str(SCRIPTS))
    articles, _ = load_raw_articles(args.demo)

    old_body = old_verbose_body(articles)
    new_body = md.read_text(encoding="utf-8")
    old_chars = len(old_body)
    new_chars = len(new_body)
    compression = round((1 - new_chars / old_chars) * 100, 1) if old_chars else 0.0

    n_core = sum(1 for e in ranked_d["ranked_events"] if e["importance_score"] >= 80)
    n_possible = sum(1 for e in ranked_d["ranked_events"] if 65 <= e["importance_score"] < 80)
    n_watch = sum(1 for e in ranked_d["ranked_events"] if 50 <= e["importance_score"] < 65)
    n_appendix = sum(1 for e in ranked_d["ranked_events"] if e["importance_score"] < 50)

    per_thesis_evidence = [len(t["key_evidence"]) for t in theses_d["candidate_theses"]]

    result = {
        "demo_data": str(args.demo),
        "original_candidate_count": len(articles),
        "clustered_event_count": len(ranked_d["ranked_events"]),
        "old_body_chars": old_chars,
        "new_body_chars": new_chars,
        "compression_pct": compression,
        "compression_target_pct": "30-50",
        "old_event_count_approx": len(articles),
        "new_event_count_body": plan_d["core_count"] + plan_d["watchlist_count"],
        "thesis_count": len(theses_d["candidate_theses"]),
        "thesis_note": theses_d.get("note", ""),
        "per_thesis_evidence_count": per_thesis_evidence,
        "core_events_5to7": {"tier80plus": n_core, "selected": plan_d["core_count"]},
        "watchlist_3to5": {"tier50to64": n_watch, "selected": plan_d["watchlist_count"]},
        "tier_breakdown": {"core": n_core, "possible_core": n_possible, "watchlist": n_watch, "appendix": n_appendix},
    }
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
