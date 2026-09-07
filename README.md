# AI Investing Weekly Report

一个面向投资与产品决策者的中文 Codex Skill，用于检索、核验并撰写 AI 行业投资周报。它关注公司经营、产品分发、组织变化、资本开支与产业链信号，并追踪投资假设如何被强化、削弱或推翻。

## 能力

- 以上一个完整自然周为默认时间窗口；
- 区分事实、公司披露、媒体转述、独立验证与编辑判断；
- 追踪跨周事件、投资假设、催化剂和反方证据；
- 提供采编前 QA 与发布前 QA；
- 使用机器可读来源注册表核对 required 来源覆盖；
- 默认输出公司研究优先级，不把它写成买入建议。

## 安装

将仓库克隆到 Codex Skills 目录：

```bash
git clone https://github.com/benjaminchou678-cmyk/ai-investing-weekly-report.git \
  ~/.codex/skills/ai-investing-weekly-report
```

安装后在下一轮 Codex 任务中显式调用：

```text
$ai-investing-weekly-report

生成上一完整自然周的 AI 投资周报。执行完整信源巡检和 Gate 0–5，只生成本地 Markdown，不发布飞书，也不生成图片。
```

## 工作流

```text
采集与覆盖记录
→ 标准化与 URL 审计
→ 保守去重
→ Pre-edit QA
→ 事实核验与投资假设判断
→ Release QA
→ Markdown 周报
```

详细说明：

- [Skill 入口](SKILL.md)
- [采集流程](references/collection-workflow.md)
- [数据管线](references/data-pipeline.md)
- [编辑标准](references/editorial-policy.md)
- [质量门](references/quality-gates.md)
- [周报模板](references/report-template.md)

## 验证

```bash
python3 -m unittest discover -s tests -v
```

仓库中的示例均为占位内容，不代表真实新闻或投资结论。

## 免责声明

本项目用于行业研究和信息整理，不构成投资建议、证券推荐、要约或招揽。使用者应独立核验信息，并根据自身情况作出判断。

## License

[MIT](LICENSE)
