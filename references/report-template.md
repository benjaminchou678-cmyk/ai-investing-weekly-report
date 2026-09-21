# AI 投资周报渲染模板（v4）

业务内容只存在于 Agent 定稿后的 `final_weekly_report.json`。模板不生成结论、不压缩正文，也不要求同时输出 Markdown 和 HTML。

```markdown
# AI 投资周报 · YYYY-MM-DD—YYYY-MM-DD

{weekly_lead，原样呈现}

> {sparse_note / source disclosures，如有}

## 本周产业判断

### 判断｜{theme}
- 主张：{statement}
- 核心变化：{structural_change}
- 为什么重要：{why_it_matters}
- Investment Readthrough：{investment_readthrough}
- 反方证据：{counter_evidence}
- 推翻条件：{falsification_conditions}
- 置信度：{confidence}
- 关联板块：{related_boards}
- 关键证据：{event title}（S/A/B）+ 原始来源链接

## 本周最重要的事件

### {title}（S/A）
- 发生了什么：{what_happened}
- 真正新变化：{what_is_new}
- 为什么重要：{why_it_matters}
- 评级理由：{signal_reason}
- 证据状态：{verification_status}
- 来源：{source links}

## Watchlist

### {title}（B，或有明确编辑理由的 A）
{同一事件字段}

## 编辑候选与来源池
- editorial_candidate_pool：N 条
- human_review_queue：N 条
- appendix_events：N 条
- excluded_events：N 条
```

## JSON 候选层

```text
先分离 human_review_queue（日期/身份/独立性/事实/评级待复核）
├── core_events                 正文核心，通常 S/A，建议 5–7
├── watchlist                   继续观察，通常 B 或 A，建议 3–5
├── editorial_candidate_pool    正文额度外、仍有效的 S/A/B
├── appendix_events             noise 来源池
└── excluded_events             明确排除且保留 reason
```

每个 `input_event_id` 必须恰好出现在一个层。判断引用的备选事件即使不在正文，也必须完整保留并通过事实与来源审核。
