# 周报数据处理管线

所有命令从 Skill 根目录运行。每次运行使用独立目录：

```text
reports/2026-08-31_to_2026-09-06/
├── raw/
├── candidates.json
├── candidates-validated.json
├── candidates-merged.json
├── selected-items.json
├── url-audit.json
├── merge-audit.json
├── coverage.json
├── source-qa.json
├── run-manifest.json
├── pre-edit-qa.json
├── release-qa.json
├── weekly_editorial_plan.json
├── final_weekly_report.json        ← 唯一权威产物
├── final_weekly_report.md          ← 从 JSON 渲染
├── final_weekly_report.html        ← 从 JSON 渲染
└── report-structure-qa.json
```

## 阶段一：采编前处理

```text
原始采集
→ collect_source_endpoints.py
→ validate_source_registry.py
→ audit_source_coverage.py
→ normalize_candidates.py
→ validate_candidate_urls.py
→ merge_candidates.py
→ audit_candidates.py --phase pre-edit
→ pre-edit-qa.json
```

```bash
python3 scripts/validate_source_registry.py \
  references/source-registry.json --output registry-qa.json

python3 scripts/collect_source_endpoints.py \
  --registry references/source-registry.json \
  --week-start YYYY-MM-DD --week-end YYYY-MM-DD \
  --output raw/machine-endpoints.json \
  --coverage-output coverage.json

python3 scripts/audit_source_coverage.py \
  --registry references/source-registry.json \
  --policy references/source-policy.json \
  --coverage coverage.json --profile full_weekly \
  --as-of YYYY-MM-DD --output source-qa.json

python3 scripts/normalize_candidates.py raw \
  --output candidates.json --drop-empty-title

python3 scripts/validate_candidate_urls.py candidates.json \
  --output candidates-validated.json --report url-audit.json --fix

python3 scripts/merge_candidates.py candidates-validated.json \
  --output candidates-merged.json --report merge-audit.json

python3 scripts/audit_candidates.py candidates-merged.json \
  --phase pre-edit --output pre-edit-qa.json \
  --week-start YYYY-MM-DD --week-end YYYY-MM-DD \
  --timezone Asia/Shanghai --coverage coverage.json \
  --source-registry references/source-registry.json \
  --source-qa source-qa.json \
  --run-manifest run-manifest.json
```

采编前 QA 只检查执行轨迹、来源覆盖、结构、时间窗、URL 状态和疑似重复，不检查最终条目数量或评级完成度。

## 阶段二：内容生成中间层（新增）

旧管线 `normalize → merge → report` 已拆为可校验的六步中间层。所有命令在来源校验通过后执行，只改内容生成层，不碰 Source Endpoint Registry。

```text
raw_articles
→ normalized_articles
→ event_clusters
→ ranked_events
→ candidate_theses
→ weekly_editorial_plan
→ final_weekly_report.json      ← 唯一权威状态
→ Markdown / HTML renderers     ← 从同一 JSON 渲染，不重新生成内容
```

```bash
python3 scripts/cluster_events.py merged-candidates.json -o event_clusters.json

python3 scripts/rank_events.py event_clusters.json merged-candidates.json \
  -o ranked_events.json

python3 scripts/build_theses.py ranked_events.json -o candidate_theses.json

python3 scripts/editorial_pass.py ranked_events.json candidate_theses.json \
  --week-label YYYY-MM-DD—YYYY-MM-DD \
  --plan-out weekly_editorial_plan.json \
  --json-out final_weekly_report.json \
  --md-out final_weekly_report.md \
  --html-out final_weekly_report.html
```

- **cluster_events.py**：保守聚类。同公司同日但不同产品版本 / 融资轮次 / 金额不合并；合并时更新 `source_ids` / `independence_groups` / `dates`；输出标准字段 `summary / what_is_new / why_it_matters / sources / related_events`。
- **rank_events.py**：用户指定权重打分（合计 100）：行业/竞争格局 25、中长期产业方向 25、商业化/资本/产业链 20、持续影响 15、来源可信度 10、增量/反常识 5。每维同时输出分数与理由；**不**因发布日接近周三加分。分档：80–100 core、65–79 possible_core、50–64 watchlist、<50 appendix。
- **build_theses.py**：不生成模板句。每条判断必须有 `statement / structural_change / key_evidence(2–4) / why_it_matters / investment_readthrough / counter_evidence / falsification_conditions / confidence / related_boards`。证据门槛：≥2 个跨 `independence_group` 的重要事件，或 1 个 ≥80 核心事件 + ≥2 条辅助证据；逐事件独立性检查，`independence_status=unknown` 不得通过独立证据门。判断数量动态 0–3，可跨板块，不凑数；证据不足时在 `note` 写明"本周未形成达到证据门槛的产业判断"。
- **editorial_pass.py**：以 `final_weekly_report.json` 为唯一权威产物，Markdown/HTML 从该 JSON 渲染。一句话 50–80 字；可发布判断动态 0–3 条（不凑数）；核心事件建议 5–7（不足 5 个则明示，不用 possible_core 自动补满）；Watchlist 3–5；事件卡 150–250 字；分层保留 `editorial_candidate_pool / human_review_queue / appendix_events / excluded_events` 供人判断。

### Demo 与 old-vs-new 对比

```bash
python3 scripts/demo_compare.py \
  --demo examples/demo-merged-candidates.json \
  --workdir reports/demo --out reports/demo/compare.json
```

对比原始候选数、旧/新正文字符数、压缩率（目标下降 30%–50%）、事件数、判断数、每判断证据事件数，以及核心 5–7 / Watchlist 3–5 的达成情况。

## 阶段三：编辑与发布前审核

模型读取候选、原始正文和审计报告，按编辑标准完成逐 claim 核验、筛选、评级、投资假设判断，保存 `selected-items.json`，再执行：

```bash
python3 scripts/audit_candidates.py selected-items.json \
  --phase release --output release-qa.json \
  --week-start YYYY-MM-DD --week-end YYYY-MM-DD \
  --timezone Asia/Shanghai --coverage coverage.json \
  --source-registry references/source-registry.json \
  --source-qa source-qa.json \
  --run-manifest run-manifest.json --strict
```

Release QA 检查入选条目数量、评级、投资相关性、编辑确认、claim 来源绑定和假设影响。通过后才能写正式版。

## 阶段三：成稿结构审核

完成 `final_weekly_report.json` 后，**优先审计 JSON**，再核对 Markdown/HTML 是否完整呈现 JSON 核心字段：

```bash
python3 scripts/audit_report_structure.py \
  --json final_weekly_report.json \
  --md final_weekly_report.md --html final_weekly_report.html \
  --output report-structure-qa.json
```

审计规则：判断动态 0–3 条（>3 FAIL）；每条判断字段完整；独立性未知证据不得通过门；核心事件 ≤7、Watchlist ≤5；各层候选不重复；Markdown/HTML 的判断数与核心事件数必须与 JSON 一致。结构为 `FAIL` 时必须修正后重新运行。周度判断允许由单一高材料性事件主导，不要求凑足两个事件；但不得把单周判断直接表述为长期趋势。

## coverage 与执行清单

`coverage.json` 必须使用来源注册表中的 `source_id`，并为每个已调度来源保存 `endpoint_attempts`。每条 attempt 的 `endpoint_id` 必须属于该来源，`provider_group` 用于检查采集基础设施集中度。只有主体已核验、endpoint 确实执行成功且完整枚举时间窗时，才可记录 `no_update`。`audit_source_coverage.py` 同时检查硬性来源、C1/C2 endpoint 尝试率、维度覆盖、内容来源独立性、采集商集中度和注册表新鲜度，输出 `source-qa.json`；`audit_candidates.py` 将其作为 Gate 1 的判定结果。未提供 `source-qa.json` 时只运行兼容性检查，并至少返回 WARN。

`run-manifest.json` 至少记录：

```json
{
  "week_start": "2026-08-31",
  "week_end": "2026-09-06",
  "timezone": "Asia/Shanghai",
  "steps": {
    "official_and_media": "completed",
    "builder_feeds": "completed",
    "supplemental_search": "completed",
    "normalize": "completed",
    "url_audit": "completed",
    "dedup": "completed"
  },
  "failures": []
}
```

合法步骤状态：`completed`、`failed`、`skipped_optional`。必需步骤缺失或为 `failed` 时 Gate 0 FAIL。

## 退出状态

- `PASS`：退出码 0；
- `WARN`：默认退出码 0，但必须复核；
- `FAIL`：退出码 1；
- 参数或文件错误：退出码 2；
- `--strict`：WARN 也返回退出码 1。

脚本只做结构和启发式检查，不能证明网页真实存在、来源相互独立或内容支持正文。原始数据与所有中间产物应保留，且默认写新文件，不覆盖上一步输入。
