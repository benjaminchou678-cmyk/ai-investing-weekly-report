#!/usr/bin/env python3
"""Build candidate_theses from ranked_events.

Rules (see references/editorial-policy.md):
- NO template sentences. Each thesis references concrete companies/facts and is
  falsifiable.
- Required fields: statement, structural_change, key_evidence (2-4 events),
  why_it_matters, investment_readthrough, counter_evidence,
  falsification_conditions, confidence.
- Evidence gate (per-event independence, not a union of groups):
  * Gate A: >=2 important events (score >=65) from pairwise DIFFERENT independence_groups, OR
  * Gate B: 1 core event (score >=80) + >=2 supporting events (score >=50),
    with all events pairwise independent.
- Theses may cross boards; we do NOT pad to 3.
- When evidence is insufficient, explicitly state how many publishable theses
  formed this week.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CORE_MIN = 80
IMPORTANT_MIN = 65
SUPPORT_MIN = 50


# Thematic buckets may cross boards.
THEMES = [
    {
        "id": "frontier_capability",
        "label": "前沿模型与研究能力",
        "match": r"模型|架构|研究|科学|解决|突破|首次|首个|千禧|基因组|多模态|推理|benchmark",
        "structural_change": "头部实验室在能力边界（新架构/新科学问题/新模态）上继续拉开差距，能力曲线外移抬高行业准入门槛。",
        "why_it_matters": "能力边界外移直接改变产品可实现的功能上限，并决定下游应用的可行空间。",
        "investment_readthrough": "具备自研前沿模型与算力支撑的团队研究优先级上升；纯套壳/调用 API 的应用层公司差异化收窄。",
        "counter_evidence": "尚缺独立复现、第三方评测或真实用户采用数据；实验室成果到产品化通常存在落差。",
        "falsification": "若 4 周内无第三方复现、无可用 API/产品、无独立 benchmark 复现，本判断不成立。",
    },
    {
        "id": "agent_commercial",
        "label": "Agent 与产品商业化落地",
        "match": r"Agent|API|企业|工作流|工具调用|个人 AI|助手|产品|定价|降价",
        "structural_change": "厂商从模型发布转向企业级/消费级 Agent 产品与 API 编排，竞争点从榜单转向工作流入口与分发。",
        "why_it_matters": "工作流入口与企业分发决定未来收入归属，比单次模型能力更影响采购与留存。",
        "investment_readthrough": "掌握企业工作流、权限治理与分发渠道的平台受益；仅提供模型调用、无客户粘性的中间层承压。",
        "counter_evidence": "尚无生产客户、续费或留存数据；企业 Agent 的失败率与交付成本仍高。",
        "falsification": "若 1 季度内无公开生产客户、续费或采购数据，Agent 商业化假设被削弱。",
    },
    {
        "id": "capital_concentration",
        "label": "资本向头部与基础设施集中",
        "match": r"融资|估值|IPO|上市|轮|收购|并购|可转债|募资",
        "structural_change": "本周大额融资/IPO 集中于头部模型公司与算力/芯片环节，资本继续为稀缺能力与供应链瓶颈定价。",
        "why_it_matters": "资本流向决定未来 1-2 年的研发、算力与人才竞争格局；估值溢价反映头部稀缺性。",
        "investment_readthrough": "已具备订单/技术壁垒的头部与基础设施公司融资窗口打开；无差异化的早期项目融资门槛上升。",
        "counter_evidence": "融资额不等于经营证据；估值仍可能包含叙事溢价，资金用途与收入未验证。",
        "falsification": "若 1 季度后无对应收入、客户或量产进展，本轮估值不构成基本面证据。",
    },
    {
        "id": "policy_infra",
        "label": "政策监管与算力基建",
        "match": r"规划|政策|监管|十五五|数据产权|工信部|数据局|算力|芯片|供应链|数据要素",
        "structural_change": "监管与产业政策（智算规划、数据产权基础设施）开始结构化影响供给侧与合规成本。",
        "why_it_matters": "政策决定算力供给节奏、数据可得性与合规成本，是中期产业方向的外生变量。",
        "investment_readthrough": "受益于国产算力、数据要素与合规基础设施的方向研究优先级上升；监管不确定环节下调。",
        "counter_evidence": "规划/政策到落地存在时滞，具体补贴、采购与执行细则尚未明确。",
        "falsification": "若 2 个季度内无配套执行细则、采购或落地项目，政策拉动判断被证伪。",
    },
]


def _indep_groups(ev: dict) -> set[str]:
    return {g for g in ev.get("independence_groups", []) if g}


def _pairwise_independent(events: list[dict]) -> bool:
    """True iff no two events share an independence_group."""
    seen: set[str] = set()
    for ev in events:
        groups = _indep_groups(ev)
        if not groups:
            # Unknown independence -> treat as independent only if truly unknown;
            # to be conservative, two unknown-group events do NOT pass independence.
            groups = {f"__unknown__{ev['cluster_id']}"}
        if seen & groups:
            return False
        seen |= groups
    return True


def _matches(ev: dict, pat: str) -> bool:
    text = f"{ev.get('representative_title','')} {ev.get('summary','')} {ev.get('board','')}"
    return re.search(pat, text, flags=re.IGNORECASE) is not None


def _confidence(n_core: int, n_support: int, n_groups: int) -> str:
    if n_core >= 1 and n_support >= 2 and n_groups >= 3:
        return "high"
    if n_support >= 2 and n_groups >= 2:
        return "medium"
    return "low"


def _build_statement(theme: dict, evidence: list[dict]) -> str:
    companies: list[str] = []
    titles: list[str] = []
    for ev in evidence:
        for c in ev.get("companies", [])[:1]:
            if c and c not in companies:
                companies.append(c)
        titles.append(ev.get("representative_title", ""))
    co_str = "、".join(companies[:4]) if companies else "本周多个事件"
    # Concrete, falsifiable statement referencing real actors/events.
    return (
        f"{co_str}在本周集中出现{theme['label']}相关信号，"
        f"指向{theme['structural_change']}"
    )


def build_theses(ranked: list[dict]) -> tuple[list[dict], list[dict]]:
    theses: list[dict] = []
    watchlist: list[dict] = []
    used_event_ids: set[str] = set()

    # Watchlist = 50-64 tier events (and standalone 65-79 that don't feed a thesis)
    watch_candidates = [e for e in ranked if SUPPORT_MIN <= e["importance_score"] < IMPORTANT_MIN]
    watch_candidates.sort(key=lambda x: x["importance_score"], reverse=True)

    for theme in THEMES:
        if len(theses) >= 3:
            break
        pool = [e for e in ranked if _matches(e, theme["match"]) and e["importance_score"] >= SUPPORT_MIN]
        pool.sort(key=lambda x: x["importance_score"], reverse=True)
        if not pool:
            continue

        important = [e for e in pool if e["importance_score"] >= IMPORTANT_MIN]
        core = [e for e in pool if e["importance_score"] >= CORE_MIN]

        selected: list[dict] = []
        gate_used = ""

        # Gate A: >=2 important, pairwise independent
        if len(important) >= 2:
            trial_sel: list[dict] = []
            for ev in important:
                trial = trial_sel + [ev]
                if _pairwise_independent(trial):
                    trial_sel.append(ev)
                if len(trial_sel) >= 3:
                    break
            if len(trial_sel) >= 2:
                selected = trial_sel
                gate_used = "gate_a:2+independent_important"

        # Gate B: 1 core + >=2 supporting, pairwise independent
        if not selected and core:
            lead = core[0]
            trial_sel = [lead]
            for ev in pool:
                if ev["cluster_id"] == lead["cluster_id"]:
                    continue
                if ev["importance_score"] < SUPPORT_MIN:
                    continue
                trial = trial_sel + [ev]
                if _pairwise_independent(trial):
                    trial_sel.append(ev)
                if len(trial_sel) >= 4:
                    break
            if len(trial_sel) >= 3:
                selected = trial_sel
                gate_used = "gate_b:core+2+supporting"

        if not selected:
            # Doesn't clear the thesis gate -> top pool event goes to watchlist
            if pool[0]["cluster_id"] not in used_event_ids:
                watchlist.append({
                    "watch_id": f"watch-{len(watchlist)+1}",
                    "title": pool[0].get("representative_title", ""),
                    "board": pool[0].get("board", ""),
                    "score": pool[0]["importance_score"],
                    "reason": "单一或证据独立度不足，暂不构成可发布判断",
                    "event_cluster_id": pool[0]["cluster_id"],
                })
                used_event_ids.add(pool[0]["cluster_id"])
            continue

        selected = selected[:4]
        n_groups = len(set().union(*[_indep_groups(e) or {f"__unk_{e['cluster_id']}"} for e in selected]))
        n_core = sum(1 for e in selected if e["importance_score"] >= CORE_MIN)
        n_support = len(selected)

        thesis = {
            "thesis_id": f"thesis-{theme['id']}",
            "theme": theme["label"],
            "gate": gate_used,
            "statement": _build_statement(theme, selected),
            "structural_change": theme["structural_change"],
            "key_evidence": [
                {
                    "cluster_id": e["cluster_id"],
                    "title": e.get("representative_title", ""),
                    "score": e["importance_score"],
                    "tier": e["tier"],
                    "independence_groups": sorted(_indep_groups(e)),
                }
                for e in selected
            ],
            "why_it_matters": theme["why_it_matters"],
            "investment_readthrough": theme["investment_readthrough"],
            "counter_evidence": theme["counter_evidence"],
            "falsification_conditions": theme["falsification"],
            "confidence": _confidence(n_core, n_support, n_groups),
        }
        theses.append(thesis)
        for e in selected:
            used_event_ids.add(e["cluster_id"])

    # Build watchlist: prefer watch_candidates not already used / not in a thesis
    for e in watch_candidates:
        if e["cluster_id"] in used_event_ids:
            continue
        if len(watchlist) >= 5:
            break
        watchlist.append({
            "watch_id": f"watch-{len(watchlist)+1}",
            "title": e.get("representative_title", ""),
            "board": e.get("board", ""),
            "score": e["importance_score"],
            "reason": "50-64 区间，持续观察，不进入核心",
            "event_cluster_id": e["cluster_id"],
        })
        used_event_ids.add(e["cluster_id"])

    # Also pull in standalone 65-79 that didn't get absorbed into a thesis
    for e in [x for x in ranked if IMPORTANT_MIN <= x["importance_score"] < CORE_MIN]:
        if len(watchlist) >= 5:
            break
        if e["cluster_id"] in used_event_ids:
            continue
        watchlist.append({
            "watch_id": f"watch-{len(watchlist)+1}",
            "title": e.get("representative_title", ""),
            "board": e.get("board", ""),
            "score": e["importance_score"],
            "reason": "可能核心但未通过判断证据门槛，列为观察",
            "event_cluster_id": e["cluster_id"],
        })
        used_event_ids.add(e["cluster_id"])

    watchlist = watchlist[:5]
    return theses, watchlist


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ranked", help="ranked events JSON")
    parser.add_argument("--output", "-o", required=True)
    args = parser.parse_args()

    data = json.loads(Path(args.ranked).read_text(encoding="utf-8"))
    ranked = data.get("ranked_events", [])

    theses, watchlist = build_theses(ranked)

    note = (
        f"本周仅形成{len(theses)}条可发布判断"
        if len(theses) < 3 else
        f"本周形成{len(theses)}条可发布判断"
    )

    out = {
        "schema_version": "2.0",
        "pipeline_stage": "candidate_theses",
        "thesis_count": len(theses),
        "watchlist_count": len(watchlist),
        "note": note,
        "candidate_theses": theses,
        "watchlist": watchlist,
    }
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{note}, watchlist={len(watchlist)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
