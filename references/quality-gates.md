# 周报质量门（v4）

## Gate 0：执行与输入完整性

- 周期、时区、采集、标准化、URL、去重和失败项有记录；
- `ranked_events` 完整保留聚类事件；
- 权威 JSON 的 `input_event_ids` 与 `ranked_events` 一致；
- 每个事件恰好进入一个候选层，不能静默丢失、重复或凭空新增。

## Gate 1：来源健康

沿用 `source-registry.json`、`source-policy.json`、`coverage.json` 与 `source-qa.json` 的检查。来源审核 FAIL 不得发布；WARN 必须把限制写入 `source_audit.limitations` 和 `quality_status.disclosures`，并展示给读者。

## Gate 2：先复核、后选正文

以下事件必须先进入 `human_review_queue`：

- 日期缺失、无法解析或超出窗口；
- 发布主体身份未知或不匹配；
- 来源独立性未知；
- 事实冲突或未核验；
- `signal_level=unrated`、评级冲突或缺少评级理由。

待复核事件不得进入正文，也不得作为判断证据。完成复核后，Agent 修改权威 JSON 并重新审核。

## Gate 3：S/A/B/noise 与正文选择

- 等级由 Agent 在事实核验后给出，必须写 `signal_reason`；
- 脚本不得从关键词、金额、公司知名度、来源数或旧百分制自动换算；
- S/A 通常进入核心事件；B 通常进入 Watchlist；特殊升降级须记录 `editorial_override=true` 和 `override_reason`；
- noise 进入来源池，不得进入正文；unrated 不等于 noise；
- 正文额度外的有效 S/A/B 必须留在 `editorial_candidate_pool`。

## Gate 4：事实、claim 与 Agent 定稿（硬门）

正文事件和产业判断使用的所有事件必须：

- `editor_reviewed=true`；
- 公司、产品、版本、日期和关键数字可回溯；
- `what_happened / what_is_new / why_it_matters` 完整；
- 每个核心 claim 绑定存在的 `source_ids`；
- 至少保留一个合法原始来源 URL；
- 公司披露不冒充独立验证，冲突信息不得自行消除。

Agent 直接编辑 `final_weekly_report.json`。审核的是准备发布的同一份 JSON，不再审核另一份 `selected-items.json` 后回头重跑成稿脚本。

## Gate 5：判断、稀疏周和展示一致性

- 产业判断动态 0–3 条，不凑数；
- 一件 S/A 级高材料性事件可以主导周度判断，不设机械事件数量门槛；
- 每条判断必须有主张、核心变化、关键证据、为什么重要、Investment Readthrough、反方证据、推翻条件、置信度和关联板块；
- 判断证据只能引用已审核的 core/watchlist/editorial_candidate_pool 事件；
- 零判断须明确披露，导语不得宣称已形成趋势；
- 核心事件建议 5–7、Watchlist 建议 3–5；不足时写 `sparse_note`，不得补数；
- 产品、组织、投融资、政策、算力、安全、人才都只是标签，不构成栏目配额；
- Markdown/HTML 仅按需生成；实际交付格式必须与权威 JSON 的标题、内容、数量和来源链接一致，渲染不得重新生成或截断业务内容。

## 发布状态

| 状态 | 含义 | 处理 |
|---|---|---|
| PASS | JSON 发布契约及所选展示格式一致性通过 | 可交付 |
| WARN | 已披露的覆盖、证据或稀疏周风险 | 保留披露后可交付 |
| FAIL | 输入、来源、事实、候选保留、结构或展示不合格 | 不得生成或发布展示文件 |

审计输出记录权威 JSON 的 SHA-256 和实际检查的格式。机械 PASS 不等于事实真实；事实、独立性与投资推理仍由 Agent 负责。
