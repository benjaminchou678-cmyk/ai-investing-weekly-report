# 微信公众号发现、身份核验与周窗过滤

本链路解决“指定公众号 + 指定时间”的低命中问题。核心原则是：**搜索负责发现，原文负责核验，日期负责后过滤**。不得把日期词塞进搜索查询，也不得把搜索无结果写成“本周无更新”。

## 最终链路

1. **官方网页/API**：先检查已配置的官网列表、公司新闻或官方 API。
2. **多查询并集搜索**：对规范名称、别名和 `wechat_id` 分别查询，同时使用普通网页的 `site:mp.weixin.qq.com/s` 查询。查询中不加入日期。
3. **微信原文增强**：拿到 `mp.weixin.qq.com` URL 后读取正文、作者/账号、原始发布日期和可取得的身份字段。现有 `wechat-article-fetch` 可承担正文读取；若它不能返回身份/日期，候选进入人工复核队列，不得猜测。
4. **身份严格验证**：优先 `__biz`，其次 `wechat_id`，最后才是规范账号名/别名精确匹配。标题或正文提及账号名不构成身份匹配。
5. **自然周后过滤**：统一转换到 `Asia/Shanghai`，使用半开区间 `week_start <= published_at < next_week_start`。
6. **RSS 备用**：RSS、WeRSS、RSSHub 只作备用发现与历史留存，不证明账号本周无更新。
7. **C1 人工基准补漏**：每周人工完整核对 5–10 个代表性 C1 来源，衡量官网和搜索的真实召回。

## 账号身份层

微信 source 在注册表中保留：

- `name`、`aliases`、`wechat_id`；
- `wechat_biz_ids`：从原文 URL/页面核验的 `__biz` 列表；
- `official_domains`：经过确认的对应官网域名；
- `identity_status`、`identity_last_verified_at`；
- `discovery_state.last_seen_*`：上次已确认文章，用于增量发现和断档检查。

`__biz` 或 `wechat_id` 冲突时必须进入 `identity_review_queue`。仅账号名匹配标为 `inferred`，不得等同于完成主体人工核验。

## 生成查询计划

```bash
python3 scripts/build_wechat_search_plan.py \
  --registry references/source-registry.json \
  --week-start 2026-09-14 \
  --week-end 2026-09-20 \
  --priorities C1,C2 \
  --output reports/current/raw/wechat-search-plan.json
```

时间窗只写入计划元数据，不写进 `query`。C3 默认不进入周度计划；仅当事件触发时用 `--source-id` 显式加入。

## 原文核验与后过滤

搜索或人工发现结果先整理成 `items[]`。每条至少包含 `source_id`、`title`、`url`，尽量包含 `account_name`、`wechat_id`、`biz_id`、`published_at` 和 discovery provenance。

```bash
python3 scripts/verify_wechat_candidates.py \
  --registry references/source-registry.json \
  --candidates reports/current/raw/wechat-discovered.json \
  --week-start 2026-09-14 \
  --next-week-start 2026-09-21 \
  --output reports/current/raw/wechat-verified.json
```

输出固定分为：`verified_in_window`、`identity_review_queue`、`date_unknown_review_queue`、`out_of_window`、`source_unknown_queue`。只有第一类可自动进入当周候选池。

## C1 人工基准

复制 `examples/wechat-ground-truth.example.json`，人工完整登记目标周内文章。`complete_for_window=true` 只能在核对者确认该 5–10 个账号当周文章已完整枚举后填写。

```bash
python3 scripts/compare_wechat_ground_truth.py \
  --ground-truth reports/current/qa/wechat-ground-truth.json \
  --discovered reports/current/raw/wechat-verified.json \
  --output reports/current/qa/wechat-recall.json
```

基准不完整时，脚本只输出 `discovery_coverage`；只有完整人工基准才输出 `recall`。

## no_update 的边界

搜索无命中、RSS 无命中、正文抓取失败、身份未知或日期未知都不等于 `no_update`。只有主体身份已核验，且至少一个能够完整枚举时间窗的 endpoint 成功运行，才允许使用 `no_update`。
