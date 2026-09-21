---
name: ai-investing-weekly-report
description: 检索、核验并撰写面向投资与产品决策者的中文 AI 行业周报。产品与模型、组织与人事、投融资，以及政策、算力、安全、人才等作为检索/分类/审计标签使用，最终形成 0–3 条动态、可证伪的产业判断，并判断公司经营与投资假设如何变化。适用于“AI 投资周报”“本周 AI 公司动态”“AI 商业化周度复盘”等请求；不用于单一公司深度尽调、个性化证券交易建议、实时快讯或普通技术问答。
---

# AI 投资周报

生成高信噪比、可验证、附原始来源的中文 AI 投资周报。重点不是罗列一周新闻，而是判断三个核心维度本周发生的最重要变化、解释其后续影响，并说明哪些公司与赛道的研究优先级或既有投资假设发生变化。

## 核心边界

- 默认周期为上一个完整自然周（周一 00:00 至周日 23:59，Asia/Shanghai）；用户指定区间时以用户要求为准。
- 区分文章发布日期、事件发生日期和首次发现时间。旧文章只有在本周出现新增事实时才纳入，并明确新增部分。
- “研究优先级最高”不等于买入建议。除非用户明确要求且提供适用市场与约束，否则不做证券排序、目标价或个性化交易建议。
- 产品发布、融资额、估值、用户量、榜单和厂商 benchmark 不能单独证明投资价值。
- 不得编造事实、数字或链接。抓取失败不得写成“本周无更新”。不确定信息必须标明证据状态。
- 事实、利益相关方披露、媒体转述、独立验证、编辑判断和待核验线索必须分开。

每条核心事件至少回答：

1. 发生了什么，证据来自哪里？
2. 它影响收入、成本、资本开支、渠道、竞争壁垒或监管约束中的哪一项？
3. 影响哪些公司、客户、预算所有者或供应链参与者？
4. 它对哪条投资假设构成强化、削弱、新增或失效？
5. 下一步可验证的催化剂或反证是什么？

## 选择运行模式

只读取当前任务需要的参考文件，不默认加载 `references/` 下所有内容。

### 完整周报

1. 读取 [采集流程](references/collection-workflow.md)、[来源清单](references/source-registry.md)、[机器来源策略](references/source-registry-schema.md) 与 [来源入口解析器](references/source-resolver.md)。涉及微信公众号时再读取 [微信发现与身份核验](references/wechat-discovery.md)；批量使用 mpScraper 时同时读取 [mpScraper 接入](references/mpscraper-integration.md)。来源主体与采集 endpoint 分离；来源调度与质量门分别由 `source-registry.json` 和 `source-policy.json` 驱动，C1+C2 全部做 discovery，C3 事件驱动。
2. 先运行注册表校验；对已配置 endpoint 使用 `collect_source_endpoints.py` 采集，将结果保存为结构化候选，并在 `coverage.json` 中记录逐 endpoint attempt、时间窗完整性与 provider group。未配置入口不得伪装成已检查。
   - 微信搜索先用 `build_wechat_search_plan.py` 生成不含日期词的规范名/别名/微信号多查询计划，合并结果后读取原文，再用 `verify_wechat_candidates.py` 按账号身份和自然周后过滤。搜索无结果不得写成 `no_update`。
   - 来源入口迭代时，先运行 `audit_source_endpoints.py` 生成 JSON/CSV 审计，再按 `source-rollout-plan.json` 运行 pilot 或 C2 cohort；两周结果使用 `compare_source_runs.py` 比较。C1 每周人工完整核对 5–10 个代表性账号，并用 `compare_wechat_ground_truth.py` 评估；没有完整 ground truth 时只报告发现覆盖率，不得称为真实召回率。
3. 按 [数据管线](references/data-pipeline.md) 完成标准化、URL 结构检查、保守去重和采编前 QA。
4. 进入内容生成中间层：`cluster_events.py → rank_events.py → build_theses.py → editorial_pass.py`，产出 `event_clusters`、`ranked_events`、`candidate_theses`、`weekly_editorial_plan`，并以 `final_weekly_report.json` 为唯一权威产物；Markdown 与 HTML 均从该 JSON 渲染。评分权重与判断证据门槛见 [编辑标准](references/editorial-policy.md)。
5. 先运行来源注册表校验和来源覆盖审计，生成 `source-qa.json`；再按 [质量门](references/quality-gates.md) 执行发布前 QA（含内容层机械 QA）。硬性 Gate 失败时不得标记为正式版。
6. 按 [周报模板](references/report-template.md) 从 `final_weekly_report.json` 渲染压缩版 Markdown 与最小 HTML；核心事件建议 5–7、Watchlist 3–5、可发布判断动态 0–3 条，不凑数。
7. 运行 `scripts/audit_report_structure.py --json final_weekly_report.json [--md ... --html ...]` 生成 `report-structure-qa.json`；优先审计 JSON Schema，再核对 Markdown/HTML 是否完整呈现 JSON 核心字段。结构 FAIL 时修正后再交付。

### 基于已有材料撰写

用户已提供新闻、链接、候选 JSON 或研究笔记时，不重复完整信源巡检，除非用户要求补充搜索。读取候选结构、编辑标准和质量门；只对需要的材料做标准化、去重与核验，并明确覆盖范围不能代表完整周报。

### 审核或修改已有周报

读取编辑标准和质量门。只有需要改写结构时才读取周报模板；不重新搜索，除非用户要求核验或补充最新信息。

### 生成视觉或发布飞书

- 仅当用户明确要求判断配图或视觉版时读取 [视觉工作流](references/visual-workflow.md)。
- 仅当用户明确要求创建、更新或推送飞书时读取 [飞书发布流程](references/feishu-publishing.md)。本地生成不等于获得外部发布授权。

## 数据与判断边界

**诚实性说明（重要）**：`rank_events` 的 80/65/50 分档是**正则关键词启发式打分，未经历史标定**，只用于排序与分层，不代表事件真实重要性；`build_theses` 产出的 `statement`/`editorial_pass` 产出的事件卡是**编辑草稿**，不是结论。脚本负责格式、排序与证据门；**最终可发布的产业判断必须由人（或 LLM）复核主张、证据与反证后定稿**，不得把脚本生成的模板句直接当成品。

脚本负责格式统一、URL 结构检查、保守去重、来源覆盖核对、字段统计和机械 QA。模型负责网页事实核验、来源独立性、claim 与来源绑定、投资相关性、假设影响、信号等级、关键判断和最终写作。

脚本返回 `PASS` 不代表事实真实；`WARN` 必须人工复核；硬性 Gate 返回 `FAIL` 时不得发布正式版。

mpScraper、WeRSS、RSSHub 与搜索只属于采集或发现基础设施，不构成新的独立信源。微信公众号优先检查官网网页，其次使用已验证的本地 mpScraper，再做多查询搜索并读取微信原文；RSS 类入口作为备用。搜索查询不混入日期，日期在原文核验后按周窗过滤。候选必须同时保留发布主体、采集 endpoint、原始 URL 与镜像 URL；正式 claim 优先引用原始文章或主体官网。

## 默认输出

- 全程使用中文，必要的海外原文短句除外。
- 报告主标题保持简洁，使用“AI 投资周报 · 日期区间”；不要添加“关键判断版”“趋势版”“扩展版”等版本型后缀。试跑、来源限制或质量状态应在正文说明，不写进主标题。
- 核心新闻按新中间层产出：可发布判断动态 0–3 条（不凑数，正常周建议 1–3，证据不足允许 0 条并明示）、核心事件建议 5–7（宁缺毋滥，不足则明示）、Watchlist 3–5；正文较旧详版下降 30%–50%。
- 可发布判断不强制按产品/组织/投融资各一条，也不要求每个后台板块都出判断；一条判断可跨多个板块并带 `related_boards`。证据门槛未达到时明确写"本周未形成达到证据门槛的产业判断"。单事件不升格为判断。
- 周度判断允许由一件高材料性事件主导，不要求凑足两个事件；但核心事实必须充分核验，并写明核心变化、为什么重要、Investment Readthrough、反方证据或推翻条件、判断置信度。
- 只有经过连续 2–3 周证据验证的判断才可升级为中期趋势；不得把单周判断直接表述为长期趋势。
- 产品与模型、组织与人事、投融资，以及政策、算力、安全、人才等只作为检索标签、事件分类标签、来源覆盖审计维度和事件关联分析维度，不再是前台强制栏目。
- 候选池分层保留供人判断：65+ 进核心候选、50–64 进 Watchlist 候选、<50 留 Appendix；日期未知/独立性未知进 `human_review_queue`，不静默删除。
- 每条核心事件附原始链接或明确的 URL 降级说明。
- 默认输出“研究优先级/假设变化”，不输出“最值得买入”排名。
- 先完成 Markdown 与发布前 QA，再执行可视化或外部发布。

## 完成条件

- 周期、时区、来源覆盖、失败项和执行轨迹有记录；
- C1/C2 的已配置 endpoint 均留有 attempt evidence；未配置 C1 已作为硬性配置缺口披露；
- 候选已完成标准化、URL 检查、去重与采编前 QA；
- 入选内容已完成人工核验、信号评级、claim 来源映射和投资假设判断；
- 发布前 Gate 0–5 已执行，硬性失败已处理；
- 结构化权威产物 `final_weekly_report.json` 已生成并通过结构审计（动态 0–3 条判断、每条字段完整、独立性门通过、Markdown/HTML 与 JSON 数量与标题一致）；
- 最终产物符合用户要求，未擅自生成或发布额外产物。
