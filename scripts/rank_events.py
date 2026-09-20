#!/usr/bin/env python3
"""Rank event clusters by a user-specified weighted materiality score (0-100).

Weights (user-specified; NOT board-pinned fixed high scores):
- 25: industry / competitive-landscape change
- 25: mid-long term industrial direction
- 20: commercialization / capital / value chain
- 15: lasting impact
- 10: source credibility
- 5: incremental / counter-intuitive

Each dimension emits BOTH a numeric score and a human-readable ``reason``.
There is NO bonus for being close to Wednesday.

Tier thresholds:
- 80-100 : core
- 65-79  : possible_core / judgment evidence
- 50-64  : watchlist
- <50    : appendix (not in body)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _editorial_normalize import load_raw_articles

# Dimension weight table (must sum to 100)
WEIGHTS = {
    "industry_competitive": 25,
    "long_term_direction": 25,
    "commercial_capital": 20,
    "lasting_impact": 15,
    "source_credibility": 10,
    "incremental": 5,
}

# Keyword banks (heuristic; deterministic, used only to fill the reason field)
_FRONTIER_PLAYERS = {
    "openai", "anthropic", "google", "deepmind", "meta", "microsoft",
    "deepseek", "nvidia", "moonshot", "智谱", "月之暗面", "qwen", "阿里",
    "字节", "bytedance", "xai", "mistral", "cognition", "devin",
}
_RESEARCH_KW = r"架构|模型|研究|科学|解决|突破|首次|首个|千禧|基因组|论文|benchmark|推理能力|能力边界"
_POLICY_KW = r"规划|政策|监管|十五五|数据产权|工信部|数据局|合规|备案|立法"
_COMMERCE_KW = r"融资|估值|IPO|上市|轮|收购|并购|定价|降价|API|客户|收入|营收|市占|份额|订单|合同|采购"
_DURABLE_KW = r"IPO|上市|融资|并购|战略|架构|政策|规划|开源|生态|供应链|算力"
_NOVELTY_KW = r"首次|首个|首次|解决|突破|千禧|首创|第一次|首例|前所未有|颠覆"


def _has(text: str, pattern: str) -> bool:
    return re.search(pattern, text or "", flags=re.IGNORECASE) is not None


def _count(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text or "", flags=re.IGNORECASE))


def _materiality_pts(mat: str) -> int:
    return {"high": 12, "medium": 7, "low": 3, "unrated": 0}.get(mat, 0)


def score_industry_competitive(cl: dict, arts: list[dict]) -> tuple[int, str]:
    w = WEIGHTS["industry_competitive"]
    title = cl["representative_title"]
    summary = cl.get("summary", "")
    text = f"{title} {summary}"
    pts = 0
    reasons: list[str] = []

    mat = arts[0].get("materiality", "unrated") if arts else "unrated"
    m_pts = {"high": 13, "medium": 7, "low": 2, "unrated": 0}.get(mat, 0)
    pts += m_pts
    reasons.append(f"materiality={mat} (+{m_pts})")

    players = {c.lower() for c in cl.get("companies", [])}
    if players & _FRONTIER_PLAYERS:
        pts += 6
        reasons.append("前沿/头部玩家 (+6)")
    et = (arts[0].get("entity_type", "") if arts else "")
    if et in {"public_company", "large_private"}:
        pts += 3
        reasons.append(f"主体规模={et} (+3)")

    if _has(text, _COMMERCE_KW):
        kws = sorted(set(re.findall(_COMMERCE_KW, text, flags=re.IGNORECASE)))
        bonus = min(4, 1 + len(kws))
        pts += bonus
        reasons.append(f"竞争/商业信号 {','.join(kws[:3])} (+{bonus})")

    if len(cl.get("independence_groups", [])) >= 2:
        pts += 3
        reasons.append("多独立来源 (+3)")

    pts = min(w, pts)
    return pts, "；".join(reasons) or "无明显竞争格局信号"


def score_long_term_direction(cl: dict, arts: list[dict]) -> tuple[int, str]:
    w = WEIGHTS["long_term_direction"]
    title = cl["representative_title"]
    summary = cl.get("summary", "")
    text = f"{title} {summary}"
    pts = 0
    reasons: list[str] = []

    if _has(text, _RESEARCH_KW):
        kws = sorted(set(re.findall(_RESEARCH_KW, text, flags=re.IGNORECASE)))
        bonus = min(16, 8 + len(kws) * 2)
        pts += bonus
        reasons.append(f"前沿/能力信号 {','.join(kws[:3])} (+{bonus})")
    if _has(text, _POLICY_KW):
        kws = sorted(set(re.findall(_POLICY_KW, text, flags=re.IGNORECASE)))
        bonus = min(12, 6 + len(kws) * 2)
        pts += bonus
        reasons.append(f"结构性政策 {','.join(kws[:3])} (+{bonus})")

    th = (arts[0].get("time_horizon", "") if arts else "")
    if "年" in th or "季度" in th:
        pts += 4
        reasons.append(f"时间维度={th} (+4)")

    mat = arts[0].get("materiality", "unrated") if arts else "unrated"
    if mat == "high":
        pts += 4
        reasons.append("高材料性 (+4)")

    players = {c.lower() for c in cl.get("companies", [])}
    if players & _FRONTIER_PLAYERS:
        pts += 4
        reasons.append("头部实验室/公司 (+4)")

    pts = min(w, pts)
    return pts, "；".join(reasons) or "未识别中长期方向信号"


def score_commercial_capital(cl: dict, arts: list[dict]) -> tuple[int, str]:
    w = WEIGHTS["commercial_capital"]
    title = cl["representative_title"]
    summary = cl.get("summary", "")
    text = f"{title} {summary}"
    board = cl.get("board", "")
    pts = 0
    reasons: list[str] = []

    money = re.findall(r"\$?\s?\d+(?:\.\d+)?\s?[BM亿]|€\s?\d+", text, flags=re.IGNORECASE)
    # Detect mega-rounds (>= $5B or >= €3B) as an extra commercial signal.
    mega = False
    for tok in money:
        m = re.search(r"(\d+(?:\.\d+)?)\s*([BM亿])", tok, flags=re.IGNORECASE)
        if m:
            val = float(m.group(1))
            unit = m.group(2).upper()
            billions = val if unit == "B" else val / 1000.0 if unit == "M" else val / 10.0
            if "€" in tok or unit == "B":
                if billions >= 3:
                    mega = True
    if board == "投融资" and money:
        pts += 12
        reasons.append(f"大额融资/资本 {','.join(money[:2])} (+12)")
        if mega:
            pts += 4
            reasons.append("mega-round (≥$3B/€3B) (+4)")
    elif board == "投融资":
        pts += 7
        reasons.append("投融资事件但金额未披露 (+7)")
    elif money:
        pts += 6
        reasons.append(f"含具体金额 {','.join(money[:1])} (+6)")

    if _has(text, r"定价|降价|API|客户|收入|营收|订单|合同|采购|企业|工作流|Agent"):
        pts += 8
        reasons.append("商业化/客户信号 (+8)")

    mat = arts[0].get("materiality", "unrated") if arts else "unrated"
    if mat == "high":
        pts += 3
        reasons.append("高材料性 (+3)")
    et = (arts[0].get("entity_type", "") if arts else "")
    if et in {"public_company", "large_private"}:
        pts += 2
        reasons.append(f"主体规模={et} (+2)")

    pts = min(w, pts)
    return pts, "；".join(reasons) or "无明确商业化/资本信号"


def score_lasting_impact(cl: dict, arts: list[dict]) -> tuple[int, str]:
    w = WEIGHTS["lasting_impact"]
    title = cl["representative_title"]
    summary = cl.get("summary", "")
    text = f"{title} {summary}"
    pts = 0
    reasons: list[str] = []

    th = (arts[0].get("time_horizon", "") if arts else "")
    if "年" in th:
        pts += 5
        reasons.append(f"长期时间维度={th} (+5)")
    elif "季度" in th:
        pts += 3
        reasons.append(f"中期时间维度={th} (+3)")

    mat = arts[0].get("materiality", "unrated") if arts else "unrated"
    if mat == "high":
        pts += 5
        reasons.append("高材料性 (+5)")

    if _has(text, _DURABLE_KW):
        pts += 3
        reasons.append("结构性事件类型 (+3)")

    if len(cl.get("independence_groups", [])) >= 2:
        pts += 2
        reasons.append("多独立来源 (+2)")

    pts = min(w, pts)
    return pts, "；".join(reasons) or "持续影响有限"


def score_source_credibility(cl: dict, arts: list[dict]) -> tuple[int, str]:
    w = WEIGHTS["source_credibility"]
    verif = arts[0].get("verification_status", "unverified") if arts else "unverified"
    base = {
        "independently_verified": 10,
        "verified_primary": 9,
        "company_disclosure": 6,
        "regulator_disclosure": 7,
        "independent_media": 6,
        "media_report": 5,
        "single_source": 3,
        "unverified": 1,
        "": 1,
    }.get(verif, 2)
    groups = set(cl.get("independence_groups", []))
    bonus = 0
    if len(groups) >= 2:
        bonus = 2
    pts = min(w, base + bonus)
    reasons = [f"verification={verif} ({base})"]
    if bonus:
        reasons.append(f"{len(groups)} 个独立组 (+{bonus})")
    return pts, "；".join(reasons)


def score_incremental(cl: dict, arts: list[dict]) -> tuple[int, str]:
    w = WEIGHTS["incremental"]
    title = cl["representative_title"]
    summary = cl.get("summary", "")
    text = f"{title} {summary}"
    if _has(text, _NOVELTY_KW):
        kws = sorted(set(re.findall(_NOVELTY_KW, text, flags=re.IGNORECASE)))
        return w, f"增量/反常识信号 {','.join(kws[:2])}"
    # Repeat marketing / generic phrasing -> low
    generic = len(re.findall(r"重磅|发布|亮相|推出", text))
    if generic >= 2 and not _has(text, r"\d|%|亿|元"):
        return 1, "偏营销/重复表述，增量低 (+1)"
    return 3, "有新增事实但非强反常识 (+3)"


def tier_for(score: int) -> str:
    if score >= 80:
        return "core"
    if score >= 65:
        return "possible_core"
    if score >= 50:
        return "watchlist"
    return "appendix"


def rank_clusters(clusters: list[dict], articles_by_id: dict[str, dict]) -> list[dict]:
    ranked = []
    for cl in clusters:
        arts = [articles_by_id.get(aid, {}) for aid in cl.get("article_ids", [])]
        arts = [a for a in arts if a]
        if not arts:
            # Fall back to canonical fields already on the cluster
            arts = [{"materiality": "", "verification_status": "", "time_horizon": "", "entity_type": ""}]

        breakdown = {
            "industry_competitive": score_industry_competitive(cl, arts),
            "long_term_direction": score_long_term_direction(cl, arts),
            "commercial_capital": score_commercial_capital(cl, arts),
            "lasting_impact": score_lasting_impact(cl, arts),
            "source_credibility": score_source_credibility(cl, arts),
            "incremental": score_incremental(cl, arts),
        }
        score_breakdown = {k: v[0] for k, v in breakdown.items()}
        reasons = {k: v[1] for k, v in breakdown.items()}
        total = sum(score_breakdown.values())
        assert sum(WEIGHTS[k] for k in WEIGHTS) == 100
        # Clamp defensively (should never exceed weights anyway)
        total = min(100, total)

        ranked.append({
            **cl,
            "score_breakdown": score_breakdown,
            "score_reasons": reasons,
            "score_weights": dict(WEIGHTS),
            "importance_score": total,
            "tier": tier_for(total),
            "representative_article": cl["article_ids"][0] if cl.get("article_ids") else "",
            "representative_url": cl["sources"][0]["url"] if cl.get("sources") else "",
        })

    ranked.sort(key=lambda x: x["importance_score"], reverse=True)
    for i, r in enumerate(ranked):
        r["rank"] = i + 1
    return ranked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clusters", help="clusters JSON")
    parser.add_argument("candidates", help="raw articles / merged candidates JSON")
    parser.add_argument("--output", "-o", required=True)
    args = parser.parse_args()

    cl_data = json.loads(Path(args.clusters).read_text(encoding="utf-8"))
    articles, _ = load_raw_articles(args.candidates)
    articles_by_id = {a["id"]: a for a in articles}

    ranked = rank_clusters(cl_data.get("clusters", []), articles_by_id)

    out = {
        "schema_version": "2.0",
        "pipeline_stage": "ranked_events",
        "weights": WEIGHTS,
        "thresholds": {"core": 80, "possible_core": 65, "watchlist": 50, "appendix_below": 50},
        "total_events": len(ranked),
        "ranked_events": ranked,
    }
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    top = ranked[0]["importance_score"] if ranked else 0
    n_core = sum(1 for r in ranked if r["tier"] == "core")
    print(f"Ranked {len(ranked)} events, top score {top}, core={n_core}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
