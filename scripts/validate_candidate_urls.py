#!/usr/bin/env python3
"""Audit candidate URL shape and optionally demote invalid/navigation URLs."""

from __future__ import annotations

import argparse
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from _candidate_io import read_json_items, wrap_items, write_json

NAV_PATHS = {
    "", "/", "/index", "/index.html", "/home", "/news", "/news/", "/blog", "/blog/",
    "/articles", "/articles/", "/papers", "/papers/", "/posts", "/posts/", "/feed", "/rss",
    "/about", "/contact", "/category", "/tags", "/topics",
}
ARTICLE_PATTERNS = (
    re.compile(r"^/item\?id=\d+"), re.compile(r"^/abs/\d+\.\d+"),
    re.compile(r"^/papers/\d+\.\d+"), re.compile(r"^/p/[\w-]+"),
    re.compile(r"/status/\d+"), re.compile(r"/(article|articles|news|posts|blog)/[^/]{4,}"),
    re.compile(r"/\d{4}/\d{1,2}/\d{1,2}/"), re.compile(r"/[^/]{6,}\.(html?|shtml)$"),
)


def classify_url(url: Any) -> tuple[str, str]:
    text = str(url or "").strip()
    if not text:
        return "missing", "URL 为空"
    if not text.startswith(("http://", "https://")):
        return "invalid_scheme", "必须使用 http 或 https"
    try:
        parsed = urlparse(text)
    except ValueError as exc:
        return "invalid_format", f"解析失败: {exc}"
    if not parsed.netloc or "." not in parsed.netloc:
        return "invalid_host", "域名无效"
    path = parsed.path or "/"
    path_query = path + (("?" + parsed.query) if parsed.query else "")
    if path.lower() in NAV_PATHS:
        return "navigation_page", f"疑似首页或导航页: {path}"
    if parsed.netloc.lower() == "github.com" and re.fullmatch(r"/[^/]+/[^/]+/?", path):
        return "likely_article", "GitHub 仓库页"
    if any(pattern.search(path_query) for pattern in ARTICLE_PATTERNS):
        return "likely_article", "命中具体内容页模式"
    if re.search(r"\b(id|p|story|article)=\d+", parsed.query):
        return "likely_article", "查询参数包含内容 ID"
    segments = [segment for segment in path.split("/") if segment]
    if segments and ((segments[-1].isdigit() and len(segments[-1]) >= 4) or len(segments[-1]) >= 6):
        return "likely_article", "路径包含较明确的内容 slug"
    return "uncertain", "无法仅根据 URL 结构确认是否为原文页"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="标准化候选 JSON/JSONL")
    parser.add_argument("--output", "-o", help="写入带 url_status 的候选文件")
    parser.add_argument("--report", required=True, help="URL 审计报告路径")
    parser.add_argument("--fix", action="store_true", help="清空无效/首页型 URL，并保留 original_url")
    parser.add_argument("--strict", action="store_true", help="将 uncertain 也计为失败")
    parser.add_argument("--threshold", type=float, default=0.10, help="失败比例阈值，默认 0.10")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        items, metadata = read_json_items(Path(args.input).expanduser())
    except (OSError, ValueError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    output_items: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    fail_statuses = {"invalid_scheme", "invalid_format", "invalid_host", "navigation_page"}
    if args.strict:
        fail_statuses.add("uncertain")
    for index, original in enumerate(items):
        item = deepcopy(original)
        status, reason = classify_url(item.get("url") or item.get("link"))
        item["url_status"] = status
        item["url_reason"] = reason
        counts[status] = counts.get(status, 0) + 1
        if status in fail_statuses:
            issues.append({"index": index, "id": item.get("id", ""), "title": item.get("title", "")[:120], "url": item.get("url", ""), "status": status, "reason": reason})
            if args.fix and item.get("url"):
                item["original_url"] = item["url"]
                item["url"] = ""
                item["url_demoted"] = True
                if isinstance(item.get("sources"), list):
                    for source in item["sources"]:
                        if isinstance(source, dict) and source.get("url") == item["original_url"]:
                            source["original_url"] = source["url"]
                            source["url"] = ""
                            source["url_status"] = status
        output_items.append(item)

    total = len(items)
    bad_ratio = len(issues) / total if total else 0.0
    verdict = "FAIL" if bad_ratio > args.threshold else "PASS"
    report = {
        "input": str(Path(args.input).expanduser()), "total": total, "counts": counts,
        "strict": args.strict, "threshold": args.threshold, "bad_count": len(issues),
        "bad_ratio": round(bad_ratio, 4), "verdict": verdict, "issues": issues,
        "note": "本脚本只检查 URL 结构，不证明网页真实存在或内容与标题一致。",
    }
    write_json(Path(args.report).expanduser(), report)
    if args.output:
        clean_meta = {k: v for k, v in metadata.items() if k not in {"items", "schema_version"}}
        write_json(Path(args.output).expanduser(), wrap_items(output_items, **clean_meta, url_audit=args.report))
    print(f"URL 审计: {verdict}，问题 {len(issues)}/{total} -> {args.report}", file=sys.stderr)
    return 1 if verdict == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
