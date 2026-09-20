# 来源入口解析与降级

来源主体与入口分离。一个 source 可有多个 endpoints；解析器按 endpoint 能力、权威性和健康状态选择路径，不把多个入口当成多个独立来源。

## 能力层级

| 层级 | 入口 | 用途 |
|---|---|---|
| P1 | 官方 RSS、Atom、API | 发现与证据 |
| P2 | 官方可枚举 HTML 列表 | 发现与证据 |
| P3 | 私有 WeRSS API/RSS | 微信原生内容持续发现 |
| P4 | 已验证 RSSHub 路由 | 备用发现 |
| P5 | 搜索 | 查漏与反查 |
| P6 | 人工输入 | 封闭来源降级 |

## Resolver 决策

1. 只调度 `stable`、`candidate`、`fallback` 且地址完整的 endpoint。
2. 同一来源先尝试官方结构化入口，再尝试官方网页。
3. WeRSS 成功时保留原始 `mp.weixin.qq.com` 链接；WeRSS URL 只记录为 `mirror_url`。
4. RSSHub 与搜索不能提升来源独立性。
5. primary 路径成功发现有效条目后可停止；零条目只有在时间窗完整时才可停止，否则继续 fallback。
6. 登录、验证码、凭据缺失分别记录 `blocked` 或具体失败码，不无限重试。

## 健康度与升级

- candidate 连续两轮完整成功后才可人工提升为 stable；
- stable 连续两轮失败时降为 candidate 或 blocked；
- `last_success_at`、连续成功/失败次数和发现延迟属于运行状态，应写入运行产物，不要频繁改写静态注册表；
- `provider_group` 用于识别基础设施单点故障，`independence_group` 用于判断内容证据是否独立，二者不可混用。

## WeRSS 边界

- 推荐私有部署、认证访问、摘要或元数据模式；
- 注册表只保存 `credential_ref`，不保存 API Key、Cookie 或登录凭据；
- 未配置 `url + account_id/feed_id` 的 WeRSS endpoint 必须是 `unconfigured`；
- WeRSS 只负责发现和历史留存，最终证据仍回到原始微信文章或主体官网；
- 不绕过验证码、登录限制或其他技术保护措施。
