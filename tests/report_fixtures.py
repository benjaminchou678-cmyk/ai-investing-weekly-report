"""合成测试事件；不代表真实新闻、评级或 Agent 核验结果。"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import editorial_pass as EP
from _report_contract import week_meta


def event(cid, level="A", **updates):
    item = {"cluster_id": cid, "representative_title": f"测试事件 {cid}", "title": f"测试事件 {cid}",
            "article_ids": [cid], "companies": [cid], "board": "产品与模型", "event_type": "产品",
            "dates": ["2026-09-15"], "earliest_date": "2026-09-15", "latest_date": "2026-09-15",
            "signal_level": level, "signal_reason": f"测试评级理由 {cid}", "verification_status": "verified_primary",
            "independence_status": "verified", "independence_groups": [f"g-{cid}"], "review_reasons": [],
            "summary": f"测试摘要 {cid}", "what_happened": f"已核验事件 {cid}",
            "what_is_new": f"测试增量 {cid}", "why_it_matters": f"测试业务含义 {cid}",
            "sources": [{"source_id": f"s-{cid}", "name": "合成来源", "url": f"https://example.com/{cid}", "independence_group": f"g-{cid}"}],
            "editor_reviewed": True, "claims": [{"claim": f"已核验事件 {cid}", "source_ids": [f"s-{cid}"], "verified": True}]}
    item.update(updates)
    return item


def thesis(tid="t1", evidence=None):
    return {"thesis_id": tid, "theme": f"测试判断 {tid}", "statement": f"可证伪的测试主张 {tid}",
            "structural_change": "测试结构变化", "why_it_matters": "测试原因", "investment_readthrough": "测试投资含义",
            "counter_evidence": "测试反证", "falsification_conditions": "测试推翻条件", "confidence": "medium",
            "related_boards": ["产品与模型", "组织与人事"], "editor_reviewed": True,
            "key_evidence": [{"cluster_id": cid} for cid in (evidence or ["c0"])]}


def final_report(events=None, theses=None):
    events = events if events is not None else [event(f"c{i}") for i in range(5)] + [event(f"w{i}", "B") for i in range(3)]
    theses = [thesis()] if theses is None else theses
    final = EP.prepare_report(events, week_meta("2026-09-14", "2026-09-20"), theses)
    final["weekly_lead"] = "测试主线：成本变化需要持续核验。" if theses else "本周未形成达到证据门槛的产业判断。"
    final["source_audit"] = {"overall_status": "PASS", "scope": "合成回归用例，非真实周报", "limitations": []}
    final["quality_status"] = {"editor_reviewed": True, "reviewed_at": "2026-09-20T20:00:00+08:00",
                               "sparse_note": "", "zero_thesis_reason": "" if theses else "本周未形成达到证据门槛的产业判断。", "disclosures": []}
    if len(final["core_events"]) < 5 or len(final["watchlist"]) < 3:
        final["quality_status"]["sparse_note"] = "可核验事件不足建议数量，不补数。"
    return final, events
