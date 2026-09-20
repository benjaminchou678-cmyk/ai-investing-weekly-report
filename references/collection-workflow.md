# 周度信息采集流程

## 时间窗口

- 默认上一个完整自然周，Asia/Shanghai；用户指定区间时覆盖默认值。
- 所有时间先转换为 `Asia/Shanghai`，采用**半开区间**：
  `week_start 00:00+08:00 <= published_at < next_week_start 00:00+08:00`。
- 区分 `published_at`、`event_date`、`first_seen_at` 和 `last_seen_at`。
- 可保留周期前48小时内、但在本周产生新增事实的候选；必须标出新增事实。
- **日期无法解析的内容进入 `date_unknown_review_queue`，不自动进入当周事实池**；endpoint 抓取失败不等于"本周无更新"。
- 读取上一期 `selected-items.json` 或周报，识别重复事件、待验证项和假设变化。首期明确无历史基线。

## 四条采集轨道

1. **公司与监管一手材料**：公司新闻、IR、财报、监管申报、交易所公告、官方产品与工程文档。
2. **媒体与经营验证**：权威媒体、客户案例、合同、定价、招聘、流量和渠道数据。
3. **Builder 与技术生态**：博客、播客、社交原文、论文、开源仓库和安全公告，用于弱信号和工程变化。
4. **资本与市场预期**：融资、并购、资本开支、机构预期和市场反应；只有用户要求证券层分析时才使用价格与估值结论。

搜索用于查漏补缺，不能替代逐项检查 required 来源。搜索摘要只用于发现，不作为完整事实证据。

## 事件分类标签（后台，非前台栏目）

采集范围覆盖政策、安全、客户、算力、论文和市场信息。`产品与模型`、`组织与人事`、`投融资`，以及政策、算力、安全、人才等只作为**检索标签、事件分类标签、来源覆盖审计维度和事件关联分析维度**：

- `产品与模型`：科技大厂重要产品、重要模型发布及显著影响定价/分发的升级；
- `组织与人事`：核心高管、AI 负责人、知名科技人员和重大组织重组；
- `投融资`：重要融资、战略投资、并购及 IPO/募资。

这些标签**不再构成前台强制栏目，也不要求每个板块都形成判断**。一条判断可关联多个板块（`related_boards`）。采集阶段应保留更多候选，编辑阶段再按材料性、证据强度筛选；不为栏目完整性把低价值事件升级为正文核心。

## 采集输出三类队列

采集器固定输出以下三类，不互相混淆：

```text
in_window_candidates          日期可解析且落在半开窗口内，进入当周事实池
date_unknown_review_queue     日期无法解析，单独复核，不静默进入当周事实
fetch_or_verification_failures 抓取/校验失败的 endpoint attempt，不写成"无更新"
```

endpoint、provider、原始 URL 与镜像 URL 必须保留到下游（`provenance` 块）。

## 调度与 discovery 分级

完整周报条件由 C1 扩展为 **C1 + C2 全部做 discovery**（`scheduled_c1_checked_ratio = 1.0`，`c2_discovery_required = true`）：

- **C1**：weekly required discovery，逐项访问并保留 attempt evidence；有候选才进入正文。
- **C2**：weekly lightweight discovery，只做轻量 discovery（如 Feed/列表/搜索快照），必须留 attempt evidence；是否进入正文按是否入窗、是否相关、是否有材料性决定，未入窗不展开。
- **C3**：event_driven，不做例行周检，仅在出现明确事件线索（融资传闻、监管动态、重大客户/竞品动作）时按需检索并补 attempt evidence。

来源状态补充规则：

- `unverified`：仍进入本周调度并记录 attempt evidence，但不计入 hard_required，也不参与独立性计数。
- `no_update`：仅当身份已核验（`operator_verified = true`）且 `account_window_complete = true` 时可用；否则按 `failed` 或 `blocked` 记录。

每个来源必须使用 `references/source-registry.json` 的 `source_id`，每次访问同时记录 `endpoint_id` 与 `provider_group`。至少记录：`scheduled`、`checked_at`、`status`、`account_window_complete`、逐 endpoint attempt、新增条数、最新条目时间、是否使用备用入口、失败代码和备注。

合法状态：`ok`、`no_update`、`failed`、`blocked`、`stale`、`not_scheduled`。`no_update` 仅在成功访问且周期内确无更新时使用；抓取失败写 `failed`，登录或反爬限制写 `blocked`。`not_scheduled` 只适用于本轮未计划检查的非硬性来源。

Builder Feed 记录 `generatedAt`，超过48小时标为陈旧。采集顺序为官方 RSS/API → 官方网页列表 → 私有 WeRSS → RSSHub → 搜索/人工。微信公众号账号主体、微信号、WeRSS Feed ID 或入口不明时保持 `unverified` / `unconfigured`，不猜测工具、路径或运营主体。

WeRSS、RSSHub 与搜索仅用于 discovery；同一主体通过多个 endpoint 被发现仍只算一个来源。候选保留 `discovered_via`、`collector_provider`、`canonical_url` 和可选 `mirror_url`，正式证据优先回到原始微信文章或发布主体官网。

## 来源 rollout

- `source-endpoint-audit.json/csv`：覆盖15个基础来源与29个微信C1，分别记录主体核验、入口配置、HTTP可达性和时间窗枚举能力。
- `source-rollout-plan.json`：固定20源 pilot、50个微信C2周度轻扫描和94个微信C3事件驱动三类 cohort。
- pilot 先回填两个完整自然周；`compare_source_runs.py` 比较 endpoint成功率、来源命中数、带日期/无日期候选数。
- 真实召回率必须有人工 ground truth。没有基准集时只允许使用“发现覆盖率”或“召回代理”表述。
- 私有WeRSS未提供服务地址、账号ID与凭据变量前保持 `unconfigured`，不可用公开网页试跑冒充WeRSS试跑。

## 网页降级

1. 搜索具体标题、域名和日期；
2. 使用可用正文提取；
3. 使用动态浏览器；
4. 寻找同一事件的一手替代来源。

连续方法仍无法取得正文或一手证据时，标为待核验或删除，不无限重试。

## 汇合与周度补漏

- 原始条目写入独立 JSON/JSONL；
- 标准化后进行 URL 检查和去重；
- 对照上期 `event_id` 与观察项；
- 补搜财报/资本开支、融资并购、组织调整、客户与定价、监管与供应链；
- 保留 `discovered_via` 与 claim 来源，不把不同观点合成不存在的共同事实。

采集完成条件：硬性来源均有记录，**计划检查的 C1 + C2 均有明确状态（含 attempt evidence）**，核心覆盖维度达到策略要求，必需轨道有状态，原始候选落盘，失败与无更新可区分，上期观察项已回看或明确无历史基线。C3 未触发事件时允许无记录，但需在 run-manifest 中说明 event_driven 未触发。
