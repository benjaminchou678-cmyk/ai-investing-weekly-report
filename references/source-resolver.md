# 来源解析器（Source Resolver）

定义来源访问路径的层级、轨道映射与稳定性状态，供 `source-registry.json` 的 `resolver` / `primary_track` / `secondary_tracks` 字段使用。

## L1–L5 层级定义

| 层级 | 名称 | 含义 | 典型入口 |
|---|---|---|---|
| L1 | 官方结构化 API | 官方提供的机器可读接口，字段稳定、可日期过滤、可枚举 | 公司官方 RSS/Atom、监管 OpenAPI、IR feed |
| L2 | 官方可枚举列表页 | 官方 HTML 列表，无需浏览器即可解析，支持翻页或日期范围 | 公司 Newsroom 列表、监管公告列表页 |
| L3 | 官方需浏览器/检索 | 官方页面但需 JS 渲染、登录或站内检索才能拿到条目 | 需登录的投资者页、需 JS 的产品博客 |
| L4 | 第三方聚合/镜像 | 非官方但权威的聚合，内容完整、更新及时 | 行业数据库、RSS 镜像、第三方归档 |
| L5 | 手动/降级路径 | 无稳定机器入口，依赖搜索快照、人工粘贴或备用 URL | 微信公众号、封闭社交平台、付费墙后页面 |

层级越低，自动化与可验证性越强；同来源应优先选用 L1/L2，缺失时逐级降级到 L5 并记录 `limitations`。

## 四轨道映射规则

采集轨道由 `role` 映射到 `primary_track`，每个 source 有且仅有一个 `primary_track`，可有多个 `secondary_tracks`。

| 轨道（track） | 纳入的 role |
|---|---|
| `company_regulatory` | `primary_company`、`primary_regulatory` |
| `media_business_verification` | `independent_media`、`industry_media`、`customer_proxy`、`counter_evidence` |
| `builder_technical` | `research_primary`、`builder` |
| `capital_market` | `investor_stakeholder`、`market_context` |

映射规则：

1. 按上表先把 `role` 归入唯一 `primary_track`。
2. 若来源实际覆盖其他轨道的信号，把那些轨道写入 `secondary_tracks`（数组，可空）。
3. `aggregator`、`talent_signal` 不强制映射，按其实际证据内容归入最贴近的轨道。
4. 一个 source 的 `primary_track` 不允许为空；`secondary_tracks` 不得重复、不得包含 `primary_track`。

## 稳定性状态（resolver.primary.status）

| 状态 | 定义 | 门禁要求 |
|---|---|---|
| `stable` | 入口 URL 长期不变、可稳定枚举或日期过滤，过去 90 天内连续可用 | 必须同时具备 `evidence URL` 与 `last_checked_at`；缺任一项 FAIL |
| `candidate` | 入口已配置但尚未完成两轮以上连续验证，或近期有改版/迁移迹象 | 允许缺 `last_checked_at`，但必须在 `limitations` 写明受限原因与待核验项 |
| `wechat_only` | 仅能通过微信机器服务/备用 URL 访问，无公开网页列表 | 按微信来源初始化规则管理；`last_checked_at` 可空，`officiality` 一般为 `official_proxy` 或 `unknown` |

`resolver.fallbacks` 中的备用路径沿用同一状态语义；当 `primary` 为 `stable` 但连续失败时，可临时使用 fallback，并在 coverage 记录中标注 `used_fallback: true`。
