# 周报质量门

发布审核分为采编前 QA、内容生成中间层 QA 和 Release QA。机器检查与编辑检查必须同时完成。

## 内容生成中间层机械 QA（新）

由 `tests/test_editorial_layer.py` 与 `tests/test_mechanical_qa.py` 强制执行：

- 评分六维权重和 = 重要性总分（25+25+20+15+10+5=100）；
- 每维必须有理由字段；不出现周三就近加分；
- 分档正确：80–100 core、65–79 possible_core、50–64 watchlist、<50 appendix；
- <50 不进正文；50–64 不进 core；
- 判断证据门：每条判断的证据必须两两独立；`independence_status=unknown` 的证据不能通过独立证据门；不得重复计算同集团、转载或同一原始来源；单事件不升格；
- 逐事件独立性检查（非 group 合集）；
- 同一 cluster 只出一张卡；
- 判断数量动态 0–3（>3 为 FAIL；0 条且明确证据不足可 PASS/WARN；0 条但导语仍声称形成趋势为 FAIL）；
- 核心事件建议 5–7（不足 5 但已明确披露证据不足可 WARN，不得用低等级事件静默补足）；Watchlist 3–5；候选池数量不受正文 5–7 限制；
- 正文较旧详版下降 30%–50%（sparse 周可超，并在对比中说明）。

## Gate 0：执行完整性（硬门）

- 周期与时区明确；
- 官方与媒体、Builder Feed、补漏搜索均有执行状态；
- 标准化、URL 审计、去重均完成；
- 抓取失败与无更新分开记录；
- 必需步骤失败时不得发布正式版。

## Gate 1：来源健康（硬门）

Gate 1 由 `source-registry.json`、`source-policy.json`、`coverage.json` 和生成的 `source-qa.json` 驱动，分为：

1. **注册表完整性**：source 与 endpoint ID 唯一、枚举合法、分组完整；硬性来源必须已核验、active 且至少有一个可执行 endpoint。C1 没有可执行 endpoint 视为配置缺口。
2. **采集覆盖率**：**C1 + C2 discovery 全量执行（100% endpoint attempt evidence）**，硬性来源成功率达到策略阈值；任一 C1/C2 缺 attempt evidence 即 FAIL。C3 为 event_driven，未触发事件时不要求 attempt evidence，但需在 run-manifest 标注。
3. **维度覆盖**：公司一手、资本、政策等核心维度达到最低数量；软性维度不足时 WARN。
4. **来源独立性**：按 `independence_group` 计算，不得用同集团账号、WeRSS/RSSHub 镜像或多 endpoint 制造多源验证；单一集团占比过高时 WARN。
5. **采集基础设施集中度**：按 `provider_group` 统计 endpoint 成功记录；单一 WeRSS、RSSHub 或其他服务占比过高时 WARN。
6. **新鲜度与访问**：注册信息超过复核周期、Feed 过期、付费墙、备用入口和抓取失败单独记录。
7. **Endpoint status gate**：stable/candidate/fallback 必须有完整地址；stable 还必须有核验日期。空 URL、空 Feed ID 或空账号 ID 只能标记为 `unconfigured`。

`no_update` 只表示已核验主体通过成功 endpoint 完整枚举周期后无更新；缺少 `checked_at`、`operator_verified` 或 `account_window_complete=true` 时 FAIL。`unverified` 来源仍需按 C1/C2 留 attempt evidence，但不参与独立确认。

## Gate 2：时间窗、去重与历史连续性

- 本期时间窗固定为 **2026-09-07（周一 00:00）至 2026-09-13（周日 23:59），Asia/Shanghai**；用户指定区间时覆盖默认值，并在 QA 首行标注。
- 日期缺失必须 WARN；超出周期且无本周新增事实必须删除或降级；
- 自动合并需同时满足公司、日期与事件类型；
- 标题相似但信息不足只进入人工复核；
- 融资轮次、财报季度、产品版本不可误合并；
- `event_id` 与 `previous_issue_refs` 用于识别跨周重复和新增事实。

## Gate 3：信号等级与投资假设

Release 阶段每条入选内容必须：

- 标为 S/A/B，不能为 `unrated` 或 `noise`；
- 至少有一个业务信号；
- 写明 `materiality` 与 `time_horizon`；
- 写明投资假设及 `new/strengthen/weaken/invalidate/neutral` 影响；
- 提供催化剂或可验证的反证。

评级不能只由金额、热度、公司知名度或来源数量决定。

## Gate 4：事实与证据（硬门）

- 公司、产品、版本、日期及关键数字均可回溯；
- 每个核心 claim 绑定至少一个来源；
- 公司披露不得写成独立验证；
- 多源验证必须跨独立来源组；
- 冲突信息并列呈现，不自行消除；
- 每条入选项必须 `editor_reviewed: true`。

初创公司的收入、客户、留存、毛利、现金流和 runway 没有独立验证时必须标明“公司披露”。

## Gate 5：周报完整性与可用性（动态规则）

- 产品与模型、组织与人事、投融资，以及政策、算力、安全、人才等只作为后台标签/分类/审计维度，不再是前台强制栏目，也不要求每个板块都出判断；
- **判断数量动态 0–3**：超过 3 为 FAIL；正常周建议 1–3；证据不足允许 0 条并明示"本周未形成达到证据门槛的产业判断"，不得为凑数降低证据标准；
- 每条实际发布的判断必须字段完整：主张、核心变化、关键证据、为什么重要、Investment Readthrough、反方证据、推翻条件、置信度、关联板块（`related_boards`，可跨板块）；
- 核心事件建议 5–7；少于 5 但明确披露证据不足可 WARN；不得静默使用低等级事件补足数量；
- Watchlist 建议 3–5；
- 候选池分层保留供人判断：65+ 核心候选、50–64 Watchlist、<50 Appendix；日期未知/独立性未知进 `human_review_queue`，不静默删除；`excluded_events` 至少记录 `event_id/reason/score`；
- 0 条判断时，导语不得仍声称形成了产业趋势（FAIL）；
- 周度判断允许由一件高材料性事件主导，不因事件数量少而降级；但不能把公司宣传或未经核验的传闻直接写成判断；
- 高置信度判断至少提供两个相互独立的来源链接；中/低置信度至少提供一个可回溯来源，低置信度必须使用条件式表述；
- 上期判断必须标记为已验证、部分验证、未验证或被推翻；只有连续 2–3 周获得方向一致的独立证据，才能升级为中期趋势；
- 至少呈现一项投资假设变化和一项反方证据（正常周）；
- 区分行业吸引力、公司经营质量和证券吸引力；默认输出研究优先级，不伪装成买入建议；
- 对上期观察项给出已验证、未验证或失效状态；首期明确说明无历史基线。

## 发布判定

| 状态 | 含义 | 处理 |
|---|---|---|
| PASS | 机器与编辑检查通过 | 可形成正式版 |
| WARN | 存在可披露的覆盖或证据风险 | 明示风险并人工复核 |
| FAIL | 执行、来源、结构或证据存在硬问题 | 不得标记完成或推送 |

QA 最低内容：周期与时区、候选与入选数量、来源覆盖及失败项、URL 与去重审计、评级分布、证据问题、Gate 0–5 状态、`final_weekly_report.json` 结构审计（动态判断数/字段完整性/独立性门/各层数量一致）、上期判断验证状态和最终判定。审计优先审 JSON Schema，再核对 Markdown/HTML 是否完整呈现 JSON 核心字段。
