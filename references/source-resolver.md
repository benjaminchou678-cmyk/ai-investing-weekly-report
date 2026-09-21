# 来源入口解析与降级

来源主体与入口分离。一个 source 可有多个 endpoints；解析器按 endpoint 能力、权威性和健康状态选择路径，不把多个入口当成多个独立来源。

## 能力层级

| 层级 | 入口 | 用途 |
|---|---|---|
| P1 | 微信来源的官方网页/API | 发现与证据 |
| P2 | 规范名/别名/微信号多查询 | 查漏与反查；结果取并集 |
| P3 | 微信原文读取与身份/日期核验 | 候选增强与后过滤，不是列表发现 |
| P4 | RSS、WeRSS、RSSHub | 备用发现 |
| P5 | C1 人工基准 | 补漏与召回率评估 |

上述层级针对微信公众号。非微信来源仍按官方 API/RSS/Atom → 官方网页 → 其他降级路径执行。

## Resolver 决策

1. 只调度 `stable`、`candidate`、`fallback` 且地址完整的 endpoint。
2. 微信来源先尝试官网网页/API，然后执行不含日期词的多查询搜索；RSS、WeRSS、RSSHub 只作备用。
3. WeRSS 成功时保留原始 `mp.weixin.qq.com` 链接；采集服务地址只记录为 `mirror_url`。
4. RSSHub 与搜索不能提升来源独立性。
5. 候选 URL 必须回到微信原文，按 `__biz` → `wechat_id` → 规范名称/别名的顺序核验身份，再按自然周过滤发布日期。
6. primary 路径成功发现有效条目后可停止；零条目只有在时间窗完整时才可停止，否则继续 fallback。搜索零命中永远不证明 `no_update`。
7. 登录、验证码、凭据缺失分别记录 `blocked` 或具体失败码，不无限重试。

## 状态必须区分（不得混为一谈）

采集结束时，以下五种状态语义不同，必须分别记录，尤其不能把"抓取失败"写成"本周无更新"：

| 状态 | 含义 | 记录 |
|---|---|---|
| `source unavailable` | 来源主体本身在注册表中缺失或未启用 | 配置缺口，FAIL/WARN |
| `endpoint unconfigured` | 主体存在但无可用 endpoint（缺 URL/账号 ID） | `unconfigured`，不调度 |
| `endpoint failed` | 已发起请求但失败/被反爬拦截 | `failed`/`blocked`，记 failure_code |
| `success with no in-window update` | 成功且完整枚举时间窗，窗口内确无更新 | 仅此时可用 `no_update` |
| `verification required` | 发现条目但日期/独立性无法确认 | 进 `date_unknown_review_queue` / `human_review_queue` |

## 健康度与升级

- candidate 连续两轮完整成功后才可人工提升为 stable；
- stable 连续两轮失败时降为 candidate 或 blocked；
- `last_success_at`、连续成功/失败次数和发现延迟属于运行状态，应写入运行产物，不要频繁改写静态注册表；
- `provider_group` 用于识别基础设施单点故障，`independence_group` 用于判断内容证据是否独立，二者不可混用。

## RSS / WeRSS 边界

- RSS 类入口在微信公众号链路中作为备用；WeRSS 如仍使用，推荐私有部署、认证访问、摘要或元数据模式；
- 注册表只保存 `credential_ref`，不保存 API Key、Cookie 或登录凭据；
- 未配置 `url + account_id/feed_id` 的 WeRSS endpoint 必须是 `unconfigured`；
- WeRSS 只负责发现和历史留存，最终证据仍回到原始微信文章或主体官网；
- 不绕过验证码、登录限制或其他技术保护措施。
