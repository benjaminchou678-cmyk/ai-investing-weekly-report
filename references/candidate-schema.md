# 候选与入选数据结构

本文件定义脚本共享的数据契约。采集阶段使用候选字段；编辑完成后补齐发布字段并保存为 `selected-items.json`。

## 顶层结构

```json
{
  "schema_version": "2.0",
  "week_start": "2026-08-31",
  "week_end": "2026-09-06",
  "timezone": "Asia/Shanghai",
  "generated_at": "2026-09-07T01:00:00Z",
  "items": []
}
```

脚本兼容 JSON 数组、JSONL 及常见 wrapper，但正式周报应使用上述对象。

## 候选字段

| 字段 | 要求 |
|---|---|
| `id` | 当前记录稳定 ID |
| `event_id` | 跨来源、跨周追踪同一事件的人工确认 ID；未知时为空 |
| `title` | 必填，不夸大来源 |
| `url` | 首选具体原文；降级后允许为空但保留原因 |
| `published_at` | 原始发布时间，未知时不猜测 |
| `event_date` | 事件发生日期；与发布时间分开 |
| `first_seen_at` / `last_seen_at` | 周度追踪时间 |
| `companies` | 公司或机构数组 |
| `entity_type` | `public_company` / `private_company` / `nonprofit` / `government` / `unknown` |
| `tickers` | 市场与代码，如 `NASDAQ:NVDA`；不能确定时为空 |
| `event_type` | 产品、财报、融资、组织、并购、监管、供应链等 |
| `board` | 六个主板块之一；候选阶段可为空 |
| `summary` | 仅包含来源支持的内容 |
| `discovered_via` | 发现轨道或文件来源 |
| `sources` | 来源对象数组 |
| `business_signals` | 收入、成本、资本开支、渠道、壁垒、监管等 |

来源对象建议包含：

```json
{
  "source_id": "openai-news",
  "name": "OpenAI News",
  "url": "https://example.com/article",
  "source_type": "official",
  "source_provenance": "company_primary",
  "independence_group": "openai"
}
```

不要用一个字段混合来源层级、利益关系、来源数量和核验结果。

## 发布前必须补齐的字段

```json
{
  "selected": true,
  "signal_level": "A",
  "verification_status": "verified_primary",
  "claim_confidence": "high",
  "business_signals": ["收入", "企业工作流"],
  "materiality": "medium",
  "time_horizon": "1-4周",
  "thesis": {
    "thesis_id": "enterprise-agent-distribution",
    "statement": "企业 Agent 竞争转向工作流入口",
    "impact": "strengthen",
    "rationale": "新增生产部署证据",
    "counter_evidence": "续费与交付成本仍未披露"
  },
  "catalyst": "客户续费或合同扩张",
  "downside_risk": "实施成本侵蚀毛利",
  "claims": [
    {
      "claim": "公司宣布产品进入企业审批流程",
      "claim_type": "company_disclosure",
      "source_ids": ["source-1"],
      "verified": true,
      "evidence_locator": "公告产品能力段落"
    }
  ],
  "editor_reviewed": true,
  "reviewed_at": "2026-09-07T09:00:00+08:00",
  "previous_issue_refs": []
}
```

合法 `thesis.impact`：`new`、`strengthen`、`weaken`、`invalidate`、`neutral`。

合法 `verification_status`：`unverified`、`company_disclosure`、`single_source`、`verified_primary`、`independently_verified`、`conflicting`。

合法 `signal_level`：`S`、`A`、`B`、`noise`、`unrated`。

`multi-source` 只有在不同 `independence_group` 的来源支持同一 claim 时才能成立。多个转载站、同一通讯社转载或公司与创始人账号不视为独立来源。

## URL 降级

```json
{
  "url": "",
  "original_url": "https://example.com/",
  "url_demoted": true,
  "url_status": "navigation_page",
  "url_reason": "疑似首页或导航页"
}
```

URL 降级不等于事件为假；正式发布前应寻找具体一手 URL，找不到时明确标为待核验或删除。

## 去重约束

- 标题相似只能产生复核候选，不能单独证明同一事件。
- 日期、公司或事件类型缺失时禁止模糊自动合并。
- 融资轮次、财报季度、产品版本和组织变动默认不跨事件合并。
- 合并后仍须保留每个 claim 与来源的映射；不得用更长但证据更弱的摘要覆盖已核验摘要。
