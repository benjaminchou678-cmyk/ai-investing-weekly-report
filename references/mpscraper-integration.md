# mpScraper 接入

mpScraper 用于补足微信公众号官网未同步、网页列表不可枚举或发布日期难以解析的内容。它是本地采集基础设施，不是新的独立信源；最终证据仍应指向原始 `mp.weixin.qq.com` 文章或发布主体官网。

## 优先级与启用条件

微信公众号固定按以下顺序解析：

1. 官方网页列表或官方 API；
2. mpScraper MCP；
3. RSS、WeRSS、RSSHub 备用；
4. 搜索与人工补漏。

注册表已为微信公众号创建 `mpscraper_mcp` endpoint 占位。只有同时满足以下条件才把状态从 `unconfigured` 改为 `candidate`：

- 本机 mpScraper 服务可以访问；
- 用户已主动完成微信相关登录和鉴权；
- 对应 `account_name` 已导入，且心跳显示可用；
- MCP 能列出文章并返回标题、发布时间和原始文章链接；
- 未把密码、Cookie、令牌、证书或本地 `data/` 目录写入仓库。

`candidate` 连续两轮完整覆盖目标自然周后，才可人工提升为 `stable`。需要验证码、登录失效、频率限制或账号心跳过期时记为 `blocked`，不能记为 `no_update`。

## MCP 与主采集器的边界

mpScraper 公开说明提供本地 MCP 地址，文章列表和文章详情工具的实际名称与返回结构应在部署后通过 MCP 能力发现。不要在 Skill 中臆造或硬编码未核验的工具名。

运行时分两步：

1. MCP 适配层按公众号名称和目标日期查询，分页直到完整覆盖时间窗，并把结果保存为本地 JSON；
2. `collect_source_endpoints.py --mpscraper-snapshot <path>` 读取该快照，统一执行日期过滤、来源映射和 coverage 记录。

推荐快照结构：

```json
{
  "accounts": {
    "量子位": {
      "articles": [
        {
          "title": "文章标题",
          "article_url": "https://mp.weixin.qq.com/s/example",
          "publish_time": "2026-09-18 09:00:00",
          "digest": "摘要"
        }
      ]
    }
  }
}
```

采集命令示例：

```bash
python3 scripts/collect_source_endpoints.py \
  --registry references/source-registry.json \
  --week-start YYYY-MM-DD --week-end YYYY-MM-DD \
  --mpscraper-snapshot reports/current/raw/mpscraper-snapshot.json \
  --output reports/current/raw/machine-endpoints.json \
  --coverage-output reports/current/coverage.json
```

## 运行约束

- 优先按周批量、低频运行，不进行无界重试；
- 逐账号保留查询时间、分页偏移、返回条数、最早/最晚发布时间和失败码；
- 列表查询用于 discovery，只有入选事件才拉取详情，控制登录会话压力；
- 原始文章 URL 写入 `original_url`，本地 MCP 地址只作为采集 endpoint，不对外引用；
- 同一公众号通过官网、mpScraper 和 RSS 被发现仍只计算一个发布主体；
- mpScraper 项目自身提示可能出现登录过期、验证码和频率限制，运行状态必须如实记录。
