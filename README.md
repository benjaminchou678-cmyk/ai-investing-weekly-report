# AI Investing Weekly Report

一个面向投资与产品决策者的中文 Codex Skill，用于检索、核验并撰写 AI 行业投资周报。它关注公司经营、产品分发、组织变化、资本开支与产业链信号，并追踪投资假设如何被强化、削弱或推翻。

## 能力

- 以上一个完整自然周为默认时间窗口；
- 区分事实、公司披露、媒体转述、独立验证与编辑判断；
- 追踪跨周事件、投资假设、催化剂和反方证据；
- 产品与模型、组织与人事、投融资，以及政策、算力、安全、人才等作为后台检索/分类/审计标签，不再是前台强制栏目；
- 动态输出 0–3 条可发布、可证伪的产业判断（正常周 1–3，证据不足允许 0 条并明示），解释最重要事件及其后续影响；
- 以 `final_weekly_report.json` 为唯一权威产物，Markdown/HTML 均从该 JSON 渲染；候选池分层保留供人判断；
- 单周判断不冒充长期趋势，连续 2–3 周验证后才允许升级；
- 提供采编前 QA 与发布前 QA；
- 使用 source + endpoints 机器注册表检查硬性来源、C1/C2 调度、入口健康度、基础设施集中度、来源独立性和新鲜度；
- 默认输出公司研究优先级，不把它写成买入建议。

## 安装

将仓库克隆到 Codex Skills 目录：

```bash
git clone https://github.com/benjaminchou678-cmyk/ai-investing-weekly-report.git \
  ~/.codex/skills/ai-investing-weekly-report
```

安装后在下一轮 Codex 任务中显式调用：

```text
$ai-investing-weekly-report

生成上一完整自然周的 AI 投资周报。执行完整信源巡检和 Gate 0–5，只生成本地 Markdown，不发布飞书，也不生成图片。
```

## 工作流

```text
采集与覆盖记录
→ 官网网页/API → 多查询搜索 → 微信原文身份/日期核验 → RSS 备用
→ 来源注册表校验与 Source QA
→ 标准化与 URL 审计
→ 保守去重
→ Pre-edit QA
→ 事实核验与投资假设判断
→ Release QA
→ final_weekly_report.json（唯一权威产物）
→ Markdown / HTML（从同一 JSON 渲染）
```

详细说明：

- [Skill 入口](SKILL.md)
- [采集流程](references/collection-workflow.md)
- [来源注册表 3.0](references/source-registry-schema.md)
- [来源入口解析与降级](references/source-resolver.md)
- [微信发现与身份核验](references/wechat-discovery.md)
- [来源质量门策略](references/source-policy.json)
- [数据管线](references/data-pipeline.md)
- [编辑标准](references/editorial-policy.md)
- [质量门](references/quality-gates.md)
- [周报模板](references/report-template.md)

## 验证

```bash
python3 -m unittest discover -s tests -v
```

## 来源入口配置

旧版注册表可一次性迁移为 source + endpoints 结构：

```bash
python3 scripts/migrate_source_registry_v3.py \
  references/source-registry-v2.json \
  --output references/source-registry.json
```

配置好官网网页/API，或备用 RSS/WeRSS/RSSHub 路由后，执行机器采集并生成逐入口覆盖证据：

```bash
python3 scripts/collect_source_endpoints.py \
  --registry references/source-registry.json \
  --week-start YYYY-MM-DD --week-end YYYY-MM-DD \
  --output reports/current/raw/machine-endpoints.json \
  --coverage-output reports/current/coverage.json
```

微信公众号解析顺序为官网网页/API优先，再以规范名/别名/微信号做不含日期词的多查询搜索，读取原文后验证身份并按自然周过滤；RSS/WeRSS/RSSHub只作备用。详见 [微信发现与身份核验](references/wechat-discovery.md)。

密钥只通过 endpoint 的 `credential_ref` 指向环境变量，不写入仓库。空 URL、公众号 ID 或 Feed ID 会保持 `unconfigured`，不会被误记为“本周无更新”。

首批来源迭代由以下机器文件驱动：

- `references/source-endpoint-overrides.json`：经审阅的候选入口；
- `references/source-rollout-plan.json`：20源 pilot、50个微信C2与94个微信C3的调度定义；
- `audits/source-endpoint-audit.json/csv`：15个基础来源与29个微信C1的逐入口审计；
- `audits/source-rollout-schedule.json`：实际可运行数量与缺口；
- `reports/source-pilot/two-week-comparison.json`：两周回填对比。

仓库中的示例均为占位内容，不代表真实新闻或投资结论。

## 免责声明

本项目用于行业研究和信息整理，不构成投资建议、证券推荐、要约或招揽。使用者应独立核验信息，并根据自身情况作出判断。

## License

[MIT](LICENSE)
