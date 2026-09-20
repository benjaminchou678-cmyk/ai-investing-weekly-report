# AI 投资周报输出模板（动态版，v3）

本模板描述**渲染层**。唯一权威产物是 `final_weekly_report.json`；本 Markdown 与 HTML 都由该 JSON 渲染，不得各自重新生成内容。后台板块（产品与模型/组织与人事/投融资，及政策、算力、安全、人才等）只是标签，不构成前台栏目配额。

```markdown
# AI 投资周报 · YYYY-MM-DD—YYYY-MM-DD

> [weekly_lead：50–80 字本周主线；0 判断时写"本周未形成达到证据门槛的产业判断"。]

> 编辑说明：[core_note；核心事件不足 5 个时在此明示，宁缺毋滥。]

## 本周产业判断

> 本周形成 N 条可发布判断（N ∈ 0–3）。

### 判断｜{theme}（置信度：low/medium/high）

- 主张：{statement，明确、具体、可证伪}
- 核心变化：{structural_change}
- 关键证据：{evidence title}（score）；{evidence title}（score）
- 为什么重要：{why_it_matters}
- Investment Readthrough：{investment_readthrough}
- 反方证据：{counter_evidence}
- 推翻条件：{falsification_conditions}
- 关联板块：{related_boards，跨板块时列多个}

## 本周最重要的事件

**{事件标题}（score / tier）**

{card：发生了什么 / 真正新变化 / 为什么重要 / 关联判断}

来源：[来源名](原始 URL) / [来源名](原始 URL)

## Watchlist

- {标题}（score）— {原因}

> 待人工复核：N 条（日期/独立性未知，完整清单见 final_weekly_report.json）。

## Other Updates / Sources

附录（<50，不进正文）：N 条，完整清单见 final_weekly_report.json。
```

## 分层候选池（保留在 JSON，不必全部进入阅读正文）

```text
final_weekly_report.json
├── theses                  0–3 条可发布判断（每条字段完整、过独立性门）
├── core_events             ≥80，建议 5–7，宁缺毋滥
├── watchlist               50–64，3–5
├── editorial_candidate_pool  65–79 未进正文，完整保留供人判断
├── human_review_queue      日期未知 / 独立性未知 / 证据不足
├── appendix_events          <50，Source Pool
└── excluded_events         [{event_id, reason, score}]
```

## 写作与结构检查

- 首句先写变化；数字可在来源中定位；公司或投资方披露不冒充独立事实。
- 判断不把单周信号冒充长期趋势；研究优先级不写成买入建议。
- 一条判断可关联多个板块（`related_boards`），不再按产品/组织/投融资各占一条。
- 自动化负责排序与候选分层，人保留最终编辑判断权；不为凑栏目把低价值事件升级为正文核心。
- 同一事件只进入一个正文层；跨层重复由 `audit_report_structure.py` 报告。
- 0 条判断时，导语不得仍声称形成了产业趋势。
