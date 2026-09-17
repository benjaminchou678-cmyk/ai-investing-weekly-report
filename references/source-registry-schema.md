# 来源注册表 2.0

`source-registry.json` 是来源事实的唯一机器真源；`source-policy.json` 保存可调整的质量门阈值。不要把优先级直接等同于硬性门槛。

## 核心字段

| 字段 | 含义 |
|---|---|
| `source_id` | 稳定且唯一的机器标识；更名时不应改变 |
| `channel` | `web`、`feed`、`wechat_official_account`、`social`、`database` |
| `operator` / `operator_verified` | 运营主体及其是否经过人工核验 |
| `role` | 来源在证据链中的角色 |
| `priority` | `C1` 每周、`C2` 双周/月度、`C3` 事件触发 |
| `hard_required` | 缺失是否可能直接阻断发布，与 `priority` 分离 |
| `check_frequency` | `weekly`、`biweekly`、`monthly`、`event_driven` |
| `coverage_dimensions` | 来源可覆盖的研究维度，可多选 |
| `parent_group` | 同一公司、机构或媒体集团的归属 |
| `independence_group` | 用于判断证据是否独立；同集团账号必须相同 |
| `access` | 访问方式与付费墙信息 |
| `status` | `active`、`unverified`、`inactive`、`blocked` |
| `last_verified_at` | 来源主体、访问路径和状态最后核验日期 |
| `evidence_limit` | 该来源不能单独证明什么 |

角色可取：`primary_company`、`primary_regulatory`、`investor_stakeholder`、`independent_media`、`industry_media`、`research_primary`、`market_context`、`builder`、`aggregator`、`customer_proxy`、`counter_evidence`、`talent_signal`。

核心覆盖维度可取：`company_primary`、`capital`、`policy`、`infrastructure`、`customer_demand`、`counter_evidence`、`product_distribution`、`research`、`talent`、`global_context`。

## 微信来源初始化规则

从人工名单导入时，未知微信号、运营主体和备用网址不得猜测。新条目默认：

- `operator_verified: false`；
- `status: unverified`；
- `hard_required: false`；
- 保留名单中的 C1/C2/C3，只用于调度；
- 完成人工核验后再更新运营主体、微信号、备用网址、状态和核验日期。

公司与投资机构官号属于利益相关方来源。它们可确认自己发布、投资或合作的事实，但不能独立证明客户效果、估值合理性或公司经营质量。
