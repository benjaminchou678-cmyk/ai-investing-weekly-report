# 关键判断视觉工作流

仅在用户明确要求判断配图或视觉版周报时读取。视觉层不替代 Markdown、结构化数据和来源。

## 前置条件

- 最终 Markdown 已确认；
- 判断标题、关键事实和影响链不再变化；
- 默认为三个最终判断各生成一张 16:9 PNG；
- 三张图固定依次对应产品与模型、组织与人事、投融资，不得交换或重复维度；
- 图中只使用已进入最终 Markdown 的文字和已核验数字。

## 默认后端

默认使用 ImageGen 独立生成每张判断图。不要生成 HTML、SVG 或网页截图充当判断图，除非用户明确要求其他格式。

全局视觉控制词可由用户覆盖；未指定时采用：

```text
粗颗粒胶片质感，高细节，Swiss editorial layout, retro computer UI,
cybernetic collage, tech noir, brutalist graphic design
```

控制词负责共同材质和版式纪律，三张图仍需使用不同主体、构图骨架和阅读方向。

## visual-spec

每次运行新建 `visual-spec-YYYY-MM-DD.json`，至少包含：

```json
{
  "visual_backend": "imagegen",
  "source_markdown": "weekly-report.md",
  "global_style_control": "...",
  "global_style_override": false,
  "fresh_graphic": true,
  "judgments": [
    {
      "dimension": "产品与模型",
      "source_confidence": "高/中/低",
      "source_title": "最终判断标题",
      "source_critical": "最终推翻条件",
      "short_title": "短标题",
      "motif": "视觉主体",
      "labels": ["标签1", "标签2"],
      "composition": "构图与阅读方向",
      "frame_label": "JUDGMENT 01",
      "footer": "AI Investing Weekly",
      "aria_label": "无障碍描述"
    },
    {
      "dimension": "组织与人事",
      "source_confidence": "高/中/低",
      "source_title": "最终判断标题",
      "source_critical": "最终推翻条件",
      "short_title": "短标题",
      "motif": "视觉主体",
      "labels": ["标签1", "标签2"],
      "composition": "构图与阅读方向",
      "frame_label": "JUDGMENT 02",
      "footer": "AI Investing Weekly",
      "aria_label": "无障碍描述"
    },
    {
      "dimension": "投融资",
      "source_confidence": "高/中/低",
      "source_title": "最终判断标题",
      "source_critical": "最终推翻条件",
      "short_title": "短标题",
      "motif": "视觉主体",
      "labels": ["标签1", "标签2"],
      "composition": "构图与阅读方向",
      "frame_label": "JUDGMENT 03",
      "footer": "AI Investing Weekly",
      "aria_label": "无障碍描述"
    }
  ]
}
```

`judgments` 必须恰好三项，`dimension` 依次为“产品与模型”“组织与人事”“投融资”。禁止复制上一期的 spec、PNG、短标题或辅助标签。

判断置信度为“低”时，画面和文字必须明确表达不确定性，不得将其视觉包装为确定结论。

## 每张图的要求

- 画布固定为 16:9，优先 1920×1080 或 1440×810；
- 包含判断编号、短标题、一个清晰视觉主体和推翻条件；
- 辅助标签或数字不超过 3–4 个；
- 标题是第一阅读层，核心观点第二层，批判性判断第三层；
- 主体不得穿过文字，装饰不得压过信息；
- 中文标题和判断必须在桌面和移动端均可读；
- 三张图不能只是同一模板换字、换色或换主体名。

如果 ImageGen 文字出现错字、遮挡或溢出，重新生成。若精确文字长期无法稳定生成，应征得用户同意后改用确定性文字排版，不假装图片已通过 QA。

## 可选 artist-lottery 后端

只有用户明确启用 `artist-lottery` 时才执行风格抽签和艺术机制研究。

### 来源与记录

候选风格必须锚定官方馆藏、艺术家自述、工坊/材料研究或策展资料。现代/当代可参考 MoMA、Centre Pompidou、The Met 和 Art Basel 官方名录；古典与跨文明目录必须记录时期、地域和机构来源。

`style_lottery` 至少记录：

- `pool`、`seed`、`selected_style`、`selection_reason`；
- `recent_styles_excluded`；
- `catalog_id`、`artist_or_movement`、`period`、`culture_region`；
- `catalog_kind`、`catalog_query`、`museum_basis`、`source_urls`；
- `museum_grounded`、`style_note`、`style_catalog_version`。

艺术家姓名只作为 provenance，不作为 Prompt 捷径。

### 机制提取

先提取可证据支持的工作机制，再做当代设计转译：

- 如何组织空间和观看；
- 如何处理材料和动作；
- 如何建立节奏、停顿和留白；
- 为什么这些机制能解释当周判断与影响链。

Prompt 顺序：

```text
艺术机制事实 -> 当周判断命题 -> 主体/空间关系 -> 材料与光
-> 版式与文字层级 -> 排除项
```

`style_contract` 包含 `visual_intent`、`mechanisms`、`translation_rules`、`anti_patterns`、`fit_signals`、`prompt_components`、`evaluator_subchecks` 和 `reference_works`。

`evaluation_contract` 只基于最终图、判断输入和契约评估。失败应指向 `catalog`、`mechanism_extract`、`judgment_translation`、`prompt` 或 `craft`，并给出可观察问题和修复动作。

### 形似与神似

- 形似：材质、色彩、构图和表面语言是否执行；
- 神似：空间关系、工作方法、观看条件和信息隐喻是否保留。

只有表面装饰而不能解释判断及影响链时判定失败。先重写机制转译；仍不适配时重新抽取并记录原因。

## 生成与保存

每个判断单独生成，保存到：

```text
reports/YYYY-MM-DD_to_YYYY-MM-DD/judgments-imagegen/judgment-1.png
reports/YYYY-MM-DD_to_YYYY-MM-DD/judgments-imagegen/judgment-2.png
reports/YYYY-MM-DD_to_YYYY-MM-DD/judgments-imagegen/judgment-3.png
```

同时保存 Prompt、尺寸、资产路径和 QA 结果。使用图像查看工具验收最终 PNG，不依赖生成器自评。

## QA 清单

- [ ] 判断数量和最终 Markdown 一致；
- [ ] 三张判断图依次对应产品与模型、组织与人事、投融资；
- [ ] `source_title` 与 `source_critical` 完全一致；
- [ ] 每张图为 16:9；
- [ ] 三张图主体与构图均不同；
- [ ] 标题、判断和标签清晰、无错字、无遮挡；
- [ ] 视觉主体与判断及其影响链有明确语义关系；
- [ ] 完整事实和来源仍保留在正文；
- [ ] 未复用上一期资产；
- [ ] artist-lottery 同时通过形似和神似检查；
- [ ] 失败项已重新生成或明确报告。
