#!/usr/bin/env python3
"""Safely import a tiered WeChat Markdown catalog into source-registry 3.0.

The importer is fail-closed: malformed or empty catalogs never write output.
Existing WeChat records are merged by stable id, current name, or aliases. By
default records missing from the incoming catalog are retained; use
--replace-wechat to explicitly replace the complete WeChat catalog.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


SECTION_CONFIG = {
    "科技与 AI": ("industry_media", ["product_distribution", "research"]),
    "科技与AI": ("industry_media", ["product_distribution", "research"]),
    "创投与资本": ("market_context", ["capital"]),
    "投资机构": ("investor_stakeholder", ["capital"]),
    "FA / 融资顾问": ("investor_stakeholder", ["capital"]),
    "FA/融资顾问": ("investor_stakeholder", ["capital"]),
    "FA 与融资顾问": ("investor_stakeholder", ["capital"]),
    "FA与融资顾问": ("investor_stakeholder", ["capital"]),
    "中国 AI 公司官方账号": ("primary_company", ["company_primary", "product_distribution"]),
    "中国AI公司官方账号": ("primary_company", ["company_primary", "product_distribution"]),
    "芯片与基础设施产业链": ("primary_company", ["company_primary", "infrastructure"]),
    "政策、标准与产业研究": ("research_primary", ["policy", "research"]),
    "客户与行业应用": ("customer_proxy", ["customer_demand"]),
    "客户、采购与行业应用观察": ("customer_proxy", ["customer_demand"]),
    "安全、法律与负面验证": ("counter_evidence", ["counter_evidence", "policy"]),
    "招聘、组织与人才流动": ("talent_signal", ["talent"]),
}

GROUPS = {
    "36kr": {"36氪", "36氪 Pro", "36氪Pro", "36氪出海", "硬氪"},
    "zero2ipo": {"清科研究", "投资界"},
    "bytedance": {"火山引擎", "字节即梦", "扣子Coze", "字节跳动招聘"},
    "alibaba": {"阿里云", "阿里战略投资", "阿里招聘"},
    "baidu": {"百度智能云", "百度风投", "百度文心智能体平台"},
    "tencent": {"腾讯云", "腾讯投资", "腾讯招聘"},
    "zhipu": {"智谱AI", "智谱清影"},
    "sensetime": {"商汤科技", "商汤国香资本"},
}

LIMITS = {
    "investor_stakeholder": "可确认该机构宣布的投资、融资顾问参与及其观点；融资完成、金额、估值和经营指标需独立交叉核验。",
    "primary_company": "可确认公司主动披露，客户效果、收入和市场份额仍需独立来源验证。",
    "customer_proxy": "主要用于发现行业采用线索；媒体案例不能自动等同于采购合同、续费或规模化收入。",
    "counter_evidence": "可提供安全、法律与合规线索；事件责任和影响范围仍需一手文件确认。",
    "talent_signal": "招聘与人才流动只代表计划或组织信号，不能写成已经形成产品或收入。",
    "research_primary": "可确认机构发布的政策或研究判断，政策目标和研究预测不能直接等同于产业收入。",
    "market_context": "用于融资与市场线索；金额、估值和交易状态需回到原始披露核验。",
    "industry_media": "用于发现与媒体核验；关键经营数字和投资结论需一手或独立来源支持。",
}

TRACK_BY_ROLE = {
    "primary_company": "company_regulatory",
    "primary_regulatory": "company_regulatory",
    "independent_media": "media_business_verification",
    "industry_media": "media_business_verification",
    "customer_proxy": "media_business_verification",
    "counter_evidence": "media_business_verification",
    "research_primary": "builder_technical",
    "builder": "builder_technical",
    "market_context": "capital_market",
    "investor_stakeholder": "capital_market",
    "talent_signal": "media_business_verification",
}

PRIORITY_FREQUENCY = {"C1": "weekly", "C2": "weekly", "C3": "event_driven"}
PRIORITY_DISCOVERY_MODE = {"C1": "full", "C2": "lightweight", "C3": "event_driven"}
ITEM_RE = re.compile(r"^-\s+(.+?)\s+(?:`?\[(C[123])\]`?)\s*$")


class ImportValidationError(ValueError):
    """Raised when catalog input is unsafe or ambiguous."""


def _norm(value: str) -> str:
    return re.sub(r"[\s`_\-·•]+", "", (value or "").strip()).casefold()


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
    """Parse a complete catalog; reject partial or ambiguous input."""
    if not text or not text.strip():
        raise ImportValidationError("公众号名单为空")

    section = ""
    section_heading = ""
    priority = ""
    result: list[dict[str, Any]] = []
    seen: dict[str, str] = {}

    for line_no, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if line.startswith("## "):
            section_heading = line[3:].strip()
            section = section_heading if section_heading in SECTION_CONFIG else ""
            priority = ""
            continue
        if line.startswith("### "):
            match = re.search(r"\b(C[123])\b", line)
            priority = match.group(1) if match else ""
            continue
        if not line.startswith("- "):
            continue

        match = ITEM_RE.match(line)
        if not match:
            continue
        if not section:
            raise ImportValidationError(
                f"第 {line_no} 行来源位于未知分类 {section_heading!r}: {line}"
            )
        if not priority:
            raise ImportValidationError(f"第 {line_no} 行缺少有效的 C1/C2/C3 小节")

        name, marked_priority = match.group(1).strip(), match.group(2)
        if marked_priority != priority:
            raise ImportValidationError(
                f"第 {line_no} 行等级冲突: 小节={priority}, 条目={marked_priority}"
            )
        key = _norm(name)
        if key in seen:
            raise ImportValidationError(f"公众号名称重复: {seen[key]} / {name}")
        seen[key] = name

        role, dimensions = SECTION_CONFIG[section]
        group = group_for(name)
        result.append({
            "source_id": source_id(name),
            "name": name,
            "aliases": [],
            "channel": "wechat_official_account",
            "url": "",
            "wechat_id": "",
            "fallback_url": "",
            "operator": "",
            "operator_verified": False,
            "role": role,
            "priority": marked_priority,
            "hard_required": False,
            "check_frequency": PRIORITY_FREQUENCY[marked_priority],
            "discovery_mode": PRIORITY_DISCOVERY_MODE[marked_priority],
            "coverage_dimensions": dimensions,
            "parent_group": group,
            "independence_group": group,
            "access": {"mode": "wechat_search", "paywall": False},
            "status": "unverified",
            "last_verified_at": "",
            "evidence_limit": LIMITS[role],
            "catalog_section": section,
            "primary_track": TRACK_BY_ROLE[role],
            "secondary_tracks": [],
            "endpoints": [{
                "endpoint_id": f"{source_id(name)}-wechat-machine-1",
                "type": "wechat_machine",
                "status": "unconfigured",
                "purpose": ["discovery"],
                "officiality": "unknown",
                "provider_group": "wechat-platform",
                "url": "",
                "base_url": "",
                "route": "",
                "account_id": "",
                "feed_id": "",
                "auth_required": False,
                "credential_ref": "",
                "browser_required": True,
                "date_filterable": False,
                "list_enumerable": False,
                "content_scope": "metadata",
                "last_verified_at": "",
                "limitations": "账号身份与稳定入口待人工核验",
            }],
        })

    if not result:
        raise ImportValidationError("未解析到任何公众号条目；拒绝写入")
    return result


def _build_existing_index(sources: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for source in sources:
        if source.get("channel") != "wechat_official_account":
            continue
        keys = [source.get("name", ""), source.get("source_id", "")]
        keys.extend(source.get("aliases") or [])
        for key in keys:
            if key:
                index[_norm(str(key))] = source
    return index


def merge_wechat_sources(
    registry: dict[str, Any], imported: list[dict[str, Any]], *, replace_wechat: bool = False
) -> dict[str, Any]:
    """Merge imported catalog while preserving verified identities and endpoint metadata."""
    if registry.get("schema_version") not in {"2.0", "3.0"} or not isinstance(registry.get("sources"), list):
        raise ImportValidationError("现有注册表不是合法的 source-registry 2.0/3.0")

    current: list[dict[str, Any]] = registry["sources"]
    non_wechat = [dict(s) for s in current if s.get("channel") != "wechat_official_account"]
    old_wechat = [dict(s) for s in current if s.get("channel") == "wechat_official_account"]
    index = _build_existing_index(old_wechat)
    merged: list[dict[str, Any]] = []
    matched_ids: set[str] = set()

    for fresh in imported:
        old = index.get(_norm(fresh["source_id"])) or index.get(_norm(fresh["name"]))
        if old is None:
            # Search aliases against incoming canonical name.
            old = next(
                (s for s in old_wechat if _norm(fresh["name"]) in {_norm(a) for a in s.get("aliases", [])}),
                None,
            )
        if old is None:
            merged.append(fresh)
            continue

        record = dict(old)
        old_name = str(old.get("name") or "")
        # Catalog-owned fields are refreshed; verified access metadata remains intact.
        for field in (
            "name", "role", "priority", "hard_required", "check_frequency",
            "discovery_mode", "coverage_dimensions", "catalog_section",
            "primary_track",
        ):
            record[field] = fresh[field]
        if not old.get("operator_verified"):
            record["parent_group"] = fresh["parent_group"]
            record["independence_group"] = fresh["independence_group"]
            record["evidence_limit"] = fresh["evidence_limit"]
        aliases = list(dict.fromkeys([*(old.get("aliases") or []), *(fresh.get("aliases") or [])]))
        if old_name and old_name != fresh["name"] and old_name not in aliases:
            aliases.append(old_name)
        record["aliases"] = aliases
        merged.append(record)
        matched_ids.add(str(old.get("source_id") or ""))

    if not replace_wechat:
        merged.extend(s for s in old_wechat if str(s.get("source_id") or "") not in matched_ids)

    result = dict(registry)
    result["sources"] = non_wechat + merged
    ids = [str(s.get("source_id") or "") for s in result["sources"]]
    if not all(ids) or len(ids) != len(set(ids)):
        raise ImportValidationError("合并后 source_id 为空或重复；拒绝写入")
    return result


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        json.loads(Path(tmp_name).read_text(encoding="utf-8"))
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown")
    parser.add_argument("--registry", required=True, help="现有 2.0/3.0 注册表")
    parser.add_argument("--output", "-o", required=True)
    parser.add_argument(
        "--replace-wechat", action="store_true",
        help="显式使用输入名单替换完整微信池；默认保留输入中未出现的旧微信来源",
    )
    args = parser.parse_args()

    try:
        registry = json.loads(Path(args.registry).expanduser().read_text(encoding="utf-8"))
        imported = parse_markdown(Path(args.markdown).expanduser().read_text(encoding="utf-8"))
        result = merge_wechat_sources(registry, imported, replace_wechat=args.replace_wechat)
        _atomic_write_json(Path(args.output).expanduser(), result)
    except (OSError, json.JSONDecodeError, ImportValidationError) as exc:
        print(f"导入失败: {exc}", file=os.sys.stderr)
        return 2

    print(f"已解析 {len(imported)} 个公众号；注册表共 {len(result['sources'])} 个来源")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
