#!/usr/bin/env python3
"""Import a tiered WeChat Markdown list into source-registry 2.0."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SECTION_CONFIG = {
    "科技与 AI": ("industry_media", ["product_distribution", "research"]),
    "科技与AI": ("industry_media", ["product_distribution", "research"]),
    "创投与资本": ("market_context", ["capital"]),
    "投资机构": ("investor_stakeholder", ["capital"]),
    "中国 AI 公司官方账号": ("primary_company", ["company_primary", "product_distribution"]),
    "芯片与基础设施产业链": ("primary_company", ["company_primary", "infrastructure"]),
    "政策、标准与产业研究": ("research_primary", ["policy", "research"]),
    "客户与行业应用": ("customer_proxy", ["customer_demand"]),
    "客户、采购与行业应用观察": ("customer_proxy", ["customer_demand"]),
    "安全、法律与负面验证": ("counter_evidence", ["counter_evidence", "policy"]),
    "招聘、组织与人才流动": ("talent_signal", ["talent"]),
}
GROUPS = {
    "36kr": {"36氪", "36氪 Pro", "36氪出海", "硬氪"},
    "zero2ipo": {"清科研究", "投资界"},
    "bytedance": {"火山引擎", "字节即梦", "扣子Coze", "字节跳动招聘"},
    "alibaba": {"阿里云", "阿里战略投资", "阿里招聘"},
    "baidu": {"百度智能云", "百度风投", "百度文心智能体平台"},
    "tencent": {"腾讯云", "腾讯投资", "腾讯招聘"},
    "zhipu": {"智谱AI", "智谱清影"},
    "sensetime": {"商汤科技", "商汤国香资本"},
}
LIMITS = {
    "investor_stakeholder": "可确认该机构宣布的投资及其观点，不能单独证明估值合理性、客户质量或经营表现。",
    "primary_company": "可确认公司主动披露，客户效果、收入和市场份额仍需独立来源验证。",
    "customer_proxy": "主要用于发现行业采用线索；媒体案例不能自动等同于采购合同、续费或规模化收入。",
    "counter_evidence": "可提供安全、法律与合规线索；事件责任和影响范围仍需一手文件确认。",
    "talent_signal": "招聘与人才流动只代表计划或组织信号，不能写成已经形成产品或收入。",
    "research_primary": "可确认机构发布的政策或研究判断，政策目标和研究预测不能直接等同于产业收入。",
    "market_context": "用于融资与市场线索；金额、估值和交易状态需回到原始披露核验。",
    "industry_media": "用于发现与媒体核验；关键经营数字和投资结论需一手或独立来源支持。",
}


def source_id(name: str) -> str:
    ascii_bits = re.findall(r"[A-Za-z0-9]+", name.lower())
    suffix = "-".join(ascii_bits)[:32].strip("-")
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    return f"wechat-{suffix}-{digest}" if suffix else f"wechat-{digest}"


def group_for(name: str) -> str:
    for group, names in GROUPS.items():
        if name in names:
            return group
    return source_id(name).removeprefix("wechat-")


def parse_markdown(text: str) -> list[dict[str, Any]]:
    section = ""
    priority = ""
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            candidate = line[3:].strip()
            section = candidate if candidate in SECTION_CONFIG else ""
            priority = ""
        elif line.startswith("### "):
            match = re.search(r"\b(C[123])\b", line)
            priority = match.group(1) if match else ""
        elif section and priority and line.startswith("- "):
            match = re.match(r"-\s+(.+?)\s+`\[(C[123])\]`", line)
            if not match:
                continue
            name, marked_priority = match.group(1).strip(), match.group(2)
            if name in seen:
                raise ValueError(f"公众号名称重复: {name}")
            seen.add(name)
            role, dimensions = SECTION_CONFIG[section]
            group = group_for(name)
            result.append({
                "source_id": source_id(name), "name": name,
                "channel": "wechat_official_account", "url": "", "wechat_id": "", "fallback_url": "",
                "operator": "", "operator_verified": False, "role": role,
                "priority": marked_priority, "hard_required": False,
                "check_frequency": {"C1": "weekly", "C2": "biweekly", "C3": "event_driven"}[marked_priority],
                "coverage_dimensions": dimensions, "parent_group": group, "independence_group": group,
                "access": {"mode": "wechat_search", "paywall": False},
                "status": "unverified", "last_verified_at": "", "evidence_limit": LIMITS[role],
                "catalog_section": section,
            })
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown")
    parser.add_argument("--registry", required=True, help="现有 2.0 注册表；非微信来源将保留")
    parser.add_argument("--output", "-o", required=True)
    args = parser.parse_args()
    registry_path = Path(args.registry).expanduser()
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    imported = parse_markdown(Path(args.markdown).expanduser().read_text(encoding="utf-8"))
    preserved = [s for s in registry.get("sources", []) if s.get("channel") != "wechat_official_account"]
    result = {**registry, "schema_version": "2.0", "sources": preserved + imported}
    Path(args.output).expanduser().write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已导入 {len(imported)} 个公众号；注册表共 {len(result['sources'])} 个来源")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
