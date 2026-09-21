# 来源注册表 3.0

`source-registry.json` 是发布主体与采集入口的机器真源；`source-policy.json` 保存质量门阈值。来源主体回答“谁发布”，endpoint 回答“程序从哪里取得内容”。同一主体的多个 endpoint 不构成多个独立信源。

## Source 字段

保留 `source_id`、`name`、`role`、`priority`、`hard_required`、`coverage_dimensions`、`parent_group`、`independence_group`、`status`、`evidence_limit` 等字段。`channel` 仅保留为旧版主体分类，不再用于选择采集器。

- C1、C2：`check_frequency=weekly`；
- C3：`check_frequency=event_driven`；
- `unverified` 仍进入 C1/C2 调度，但不能作为独立确认或 `no_update` 的依据；
- `hard_required` 来源至少配置一个可执行 endpoint，并自动进入调度范围，不完全依赖手工 pilot 名单。

微信公众号另外保留身份指纹：`aliases`、`wechat_id`、`wechat_biz_ids`、`official_domains`、`identity_status`、`identity_last_verified_at` 与 `discovery_state.last_seen_*`。`__biz`/`wechat_id` 用于严格身份匹配，名称只允许作推断；这些字段与 endpoint 地址不可混用。

## 独立性字段（证据门用）

每条候选/证据必须能回溯独立性。`independence_status` 取值：

| 值 | 含义 |
|---|---|
| `verified` | 发布主体已人工核验，独立关系明确 |
| `inferred` | 从域名/父账号规则推断，未经人工确认 |
| `unknown` | 无法判断独立关系 |

`unknown` **不能被自动视为相互独立**：在判断证据门中，含 `independence_status=unknown` 或无 `independence_group` 的证据一律不得通过独立证据门。

配套字段：`independence_status`、`source_group`（内容同源分组）、`provider_group`（采集基础设施分组）、`canonical_source_id`（同一原始来源的归一 ID，用于识别转载/镜像）。

## endpoints[]

每个 source 必须包含至少一个 endpoint。endpoint 统一字段：

| 字段 | 含义 |
|---|---|
| `endpoint_id` | 全局唯一入口 ID |
| `type` | `official_rss`、`official_atom`、`official_api`、`official_html_list`、`mpscraper_mcp`、`werss_api`、`werss_rss`、`rsshub`、`wechat_article`、`wechat_machine`、`search`、`manual` |
| `status` | `stable`、`candidate`、`fallback`、`unconfigured`、`blocked`、`inactive` |
| `purpose` | `discovery`、`evidence`、`fallback_discovery` 的非空数组 |
| `officiality` | `official`、`official_proxy`、`third_party`、`unknown` |
| `provider_group` | 采集基础设施故障域，例如 `official`、`werss`、`rsshub` |
| `url` / `base_url` / `route` | 实际访问路径 |
| `account_name` / `account_id` / `feed_id` | mpScraper、WeRSS 等机器服务中的账号标识 |
| `credential_ref` | 环境变量名；不得保存真实密钥 |
| `date_filterable` / `list_enumerable` | 能否按日期过滤、并完整枚举该时间窗；两者均为真才允许自动确认 `no_update` |
| `content_scope` | `full_text`、`metadata`、`headline_only`、`snippet` |
| `last_verified_at` | 最近人工或自动成功核验日期 |
| `limitations` | 反爬、认证、延迟、内容范围等限制 |

## 状态规则

- `stable`：至少两轮连续成功；必须有可访问地址和 `last_verified_at`。
- `candidate`：入口已完整配置但仍在观察；必须有可访问地址。
- `fallback`：仅在更高优先级 endpoint 失败时使用。
- `unconfigured`：缺 URL、Feed ID、公众号 ID 或必要路径；不得调度，不得写成“本周无更新”。
- `blocked`：入口存在但受登录、验证码、反爬或权限阻断。
- `inactive`：不再使用。

## 推荐解析顺序

微信公众号：

1. 官方网页列表或官方 API；
2. 已完成本机鉴权和账号心跳核验的 mpScraper；
3. 规范名、别名、微信号多查询并集；
4. 微信原文读取、账号身份验证和自然周后过滤；
5. RSS、WeRSS、RSSHub 备用入口；
6. C1 人工基准输入。

非微信来源继续优先官方 API/RSS/Atom，再使用官方网页和其他降级路径。RSS 的降级只针对微信公众号发现链路，不降低公司官方 Feed、监管 Feed 等一手结构化来源的权重。

mpScraper、WeRSS、RSSHub 和搜索是采集或发现基础设施。正式 claim 应尽量引用原始微信文章或发布主体网页；镜像不得被算作独立内容来源。

`wechat_article` 是已取得 URL 后的正文增强能力，不是列表发现 endpoint。搜索查询不包含日期，时间窗只用于原文 `published_at` 后过滤。搜索无命中不得生成 `no_update`。

## Runtime coverage

`coverage.json` 的每个 source 记录 `endpoint_attempts`：

```json
{
  "source_id": "example",
  "scheduled": true,
  "checked_at": "2026-09-20T08:00:00+08:00",
  "status": "ok",
  "account_window_complete": true,
  "endpoint_attempts": [
    {
      "endpoint_id": "example-official-rss-1",
      "provider_group": "official",
      "checked_at": "2026-09-20T08:00:00+08:00",
      "status": "ok",
      "items_found": 2,
      "window_complete": true,
      "failure_code": ""
    }
  ]
}
```

`no_update` 只在主体已核验、至少一个 endpoint 成功且 `account_window_complete=true` 时成立。
