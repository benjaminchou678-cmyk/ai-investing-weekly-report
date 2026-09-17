#!/usr/bin/env python3
"""Validate the final Markdown report's three dimension-aligned weekly judgments."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

EXPECTED = [("1", "产品与模型"), ("2", "组织与人事"), ("3", "投融资")]
REQUIRED_FIELDS = (
    "本周最重要的事情", "核心判断", "为什么重要", "直接影响", "二阶影响",
    "受益者/承压者", "时间范围", "反方证据/推翻条件", "判断置信度", "未来验证", "来源",
)
ALLOWED_CONFIDENCE = {"高", "中", "低"}
HEADING_RE = re.compile(
    r"^###\s+判断\s*([123])\s*[｜|]\s*(产品与模型|组织与人事|投融资)\s*[：:]\s*(.+?)\s*$",
    re.MULTILINE,
)


def add_issue(issues: list[dict[str, Any]], severity: str, code: str, message: str, **details: Any) -> None:
    issues.append({"severity": severity, "code": code, "message": message, **details})


def audit(markdown: str) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    matches = list(HEADING_RE.finditer(markdown))
    actual = [(match.group(1), match.group(2)) for match in matches]
    if actual != EXPECTED:
        add_issue(
            issues, "FAIL", "JUDGMENT_DIMENSIONS_MISMATCH",
            "必须按顺序包含且仅包含三个判断：产品与模型、组织与人事、投融资",
            expected=EXPECTED, actual=actual,
        )

    judgments: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        section = markdown[match.end():end]
        next_h2 = re.search(r"^##\s+", section, re.MULTILINE)
        if next_h2:
            section = section[:next_h2.start()]
        fields: dict[str, str] = {}
        for field in REQUIRED_FIELDS:
            field_match = re.search(rf"^-\s*{re.escape(field)}[：:]\s*(.+)$", section, re.MULTILINE)
            if not field_match:
                add_issue(
                    issues, "FAIL", "JUDGMENT_FIELD_MISSING",
                    f"判断 {match.group(1)} 缺少字段：{field}", dimension=match.group(2),
                )
            else:
                fields[field] = field_match.group(1).strip()

        confidence = fields.get("判断置信度", "")
        if confidence and confidence not in ALLOWED_CONFIDENCE:
            add_issue(
                issues, "FAIL", "JUDGMENT_CONFIDENCE_INVALID",
                f"判断置信度不合法：{confidence}", dimension=match.group(2),
            )
        link_count = len(re.findall(r"\[[^\]]+\]\(https?://[^)]+\)", fields.get("来源", "")))
        if link_count < 1:
            add_issue(
                issues, "FAIL", "JUDGMENT_SOURCE_MISSING",
                "每个判断至少需要一个可回溯来源链接", dimension=match.group(2),
            )
        if confidence == "高" and link_count < 2:
            add_issue(
                issues, "FAIL", "HIGH_CONFIDENCE_SOURCES_LOW",
                "高置信度判断至少需要两个来源链接，并由编辑确认其独立性",
                dimension=match.group(2), link_count=link_count,
            )
        judgments.append({
            "number": match.group(1), "dimension": match.group(2), "title": match.group(3),
            "confidence": confidence, "source_link_count": link_count,
        })

    status = "FAIL" if any(x["severity"] == "FAIL" for x in issues) else "WARN" if issues else "PASS"
    return {
        "schema_version": "2.0", "overall_status": status,
        "judgment_count": len(matches), "judgments": judgments, "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report")
    parser.add_argument("--output", "-o", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    try:
        markdown = Path(args.report).expanduser().read_text(encoding="utf-8")
    except OSError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    report = audit(markdown)
    Path(args.output).expanduser().write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"周报判断结构审计: {report['overall_status']} -> {args.output}", file=sys.stderr)
    return 1 if report["overall_status"] == "FAIL" or (args.strict and report["overall_status"] == "WARN") else 0


if __name__ == "__main__":
    raise SystemExit(main())
