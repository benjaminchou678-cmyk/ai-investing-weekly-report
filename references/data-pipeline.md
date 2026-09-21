# 周报数据处理与发布管线（v4）

所有命令从 Skill 根目录运行，每次使用独立周目录。JSON 是业务状态，Markdown/HTML 只是按需交付格式。

## 1. 采集与候选处理

保持现有链路：

```text
collect_source_endpoints.py
→ validate_source_registry.py / audit_source_coverage.py
→ normalize_candidates.py
→ validate_candidate_urls.py
→ merge_candidates.py
→ audit_candidates.py --phase pre-edit
→ cluster_events.py
```

候选处理必须保留来源、endpoint、原始链接、日期状态和复核原因。抓取失败不等于无更新。

## 2. Agent 评级与完整分流

Agent 读取原始正文与聚类事件，核验后为每个事件填写：

```json
{
  "signal_level": "S | A | B | noise",
  "signal_reason": "为什么是这个等级",
  "verification_status": "核验状态",
  "what_happened": "来源支持的事实",
  "what_is_new": "本周新增事实",
  "why_it_matters": "经营或产业含义",
  "claims": [],
  "editor_reviewed": true
}
```

未完成评级时保持 `unrated`，不得自动推断或降为 noise。然后执行：

```bash
python3 scripts/rank_events.py event_clusters.json candidates-merged.json \
  -o ranked_events.json

python3 scripts/editorial_pass.py prepare ranked_events.json \
  --week-start YYYY-MM-DD --week-end YYYY-MM-DD \
  --json-out final_weekly_report.json
```

`rank_events.py` 只按 Agent 的 S/A/B/noise 稳定排序并清理旧百分制字段。`prepare` 使用独占创建，已有 `final_weekly_report.json` 时拒绝覆盖。

`prepare` 先把日期、身份、独立性、证据或评级不完整的事件放进 `human_review_queue`，再选择正文。正文额度外 S/A/B 保留在 `editorial_candidate_pool`；noise 留在 `appendix_events`。每个输入事件必须恰好有一个去向。

## 3. Agent 直接编辑权威 JSON

Agent 以 `final_weekly_report.json` 为唯一编辑状态，完成：

- 逐 claim 核验和 `source_ids` 绑定；
- 事件 S/A/B/noise 评级及 `signal_reason`；
- 0–3 条产业判断、反方证据、推翻条件和置信度；
- 来源覆盖限制和稀疏周说明；
- `quality_status.editor_reviewed=true` 与审核时间。

不要在 Agent 定稿后重跑 `prepare`。脚本不得重写判断或事件内容。

## 4. 审核同一 JSON，再纯渲染

仅生成用户需要的格式。例如只交付 Markdown：

```bash
python3 scripts/editorial_pass.py render \
  --json final_weekly_report.json \
  --ranked ranked_events.json \
  --md-out final_weekly_report.md \
  --audit-out report-structure-qa.json
```

如同时需要 HTML，再增加：

```text
--html-out final_weekly_report.html
```

`render` 在写展示文件前审核同一 JSON，检查：

- Schema 与日期契约；
- Agent 已审核、来源 QA 未失败；
- S/A/B/noise 与去向是否合法；
- 所有 ranked event 是否恰好保留一次；
- 判断证据是否引用已审核事件；
- claim 是否指向存在的来源；
- Markdown/HTML 是否完整保留 JSON 内容和来源链接。

审计结果包含 `json_sha256` 与实际检查的格式。不存在的 `--md`/`--html` 文件必须失败；未要求的格式无需生成或检查。

## 5. 退出状态

- PASS：0；
- WARN：0，必须保留披露；
- FAIL：1，不得发布；
- 参数、文件或依赖问题：2。

机械审核不证明事实真实。网页事实、来源独立性、事件评级和投资判断仍由 Agent 负责。
