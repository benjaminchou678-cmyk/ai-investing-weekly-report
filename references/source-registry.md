# 来源与关注对象

完整周报使用同目录的 `source-registry.json` 作为机器可读清单，使用 `source-policy.json` 保存质量门阈值。本文件只说明选择原则；不要在 Markdown 和 JSON 中维护两套不一致的来源状态。字段定义见 [来源注册表 2.0](source-registry-schema.md)。

## 优先级

- `C1`：每周计划检查的核心来源；
- `C2`：出现动态时优先检查；
- `C3`：按赛道和本周信号选择性扫描。

`priority` 只决定采集调度，`hard_required` 才决定来源失败是否可能阻断发布。不得把全部 C1 或全部公众号设为硬性来源。

来源角色包括：

- `primary_company`：公司新闻、IR、财报、产品与工程文档；
- `primary_regulatory`：监管申报、交易所公告、政府文件；
- `independent_media`：具有编辑核验能力的媒体；
- `market_context`：市场预期、交易、估值和资本数据；
- `investor_stakeholder`：投资机构官号，是利益相关方披露；
- `customer_proxy` / `counter_evidence` / `talent_signal`：客户采用、反向验证和人才信号；
- `builder` / `research_primary` / `aggregator`：发现、技术和研究补充。

来源角色不直接决定事实真假；同一利益相关方旗下来源使用相同 `independence_group`。

## 覆盖原则

- 上市公司优先检查 IR、财报、监管申报和电话会原文；
- 非上市公司优先检查公司公告、客户/合同证据和独立报道；
- 融资、估值和用户量尽量找到原始披露，并注明是否得到独立验证；
- 技术媒体、公众号、榜单、Newsletter、Product Hunt 和聚合源主要用于发现；
- 同一 `parent_group` 的多个账号不得被视为独立交叉验证；
- `status: unverified` 的来源不进入硬门，也不能单独支撑独立验证结论；
- 证券层结论需要价格、估值和市场预期，缺失时只给研究优先级。

## 维护

每季度复核一次机器清单：运营主体、微信号、URL、备用入口、优先级、角色、分组、状态和 `hard_required`。临时新增来源可先记录在当期 coverage 中；多期稳定使用后再进入注册表。

人工维护的公众号 Markdown 通过 `scripts/import_wechat_sources.py` 导入。首次导入默认标为 `unverified`，禁止脚本猜测账号主体、微信号或备用官网。
