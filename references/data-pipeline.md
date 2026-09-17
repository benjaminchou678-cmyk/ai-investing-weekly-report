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
├── weekly-report.md
└── report-structure-qa.json
```

## 阶段一：采编前处理

```text
原始采集
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

## 阶段二：编辑与发布前审核

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

完成 `weekly-report.md` 后，检查三个关键判断是否分别对应产品与模型、组织与人事、投融资，并包含影响链、置信度与推翻条件：

```bash
python3 scripts/audit_report_structure.py weekly-report.md \
  --output report-structure-qa.json
```

结构为 `FAIL` 时必须修正后重新运行。周度判断允许由单一高材料性事件主导，不要求凑足两个事件；但至少提供一个可回溯来源，高置信度判断至少提供两个来源链接并由编辑确认独立性。不得把单周判断直接表述为长期趋势。

## coverage 与执行清单

`coverage.json` 必须使用来源注册表中的 `source_id`。`audit_source_coverage.py` 同时检查硬性来源、计划 C1、维度覆盖、来源独立性和注册表新鲜度，输出 `source-qa.json`；`audit_candidates.py` 将其作为 Gate 1 的判定结果。未提供 `source-qa.json` 时只运行兼容性检查，并至少返回 WARN。

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
