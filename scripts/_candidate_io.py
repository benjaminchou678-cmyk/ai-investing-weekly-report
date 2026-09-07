#!/usr/bin/env python3
"""Shared JSON/JSONL helpers for the AI investing weekly-report scripts."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

WRAPPER_KEYS = ("items", "news", "results", "articles", "entries", "posts", "tweets", "list")


def read_json_items(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read a JSON array, common wrapper object, single object, or JSONL file."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return [], {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        return [row for row in rows if isinstance(row, dict)], {"format": "jsonl"}

    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)], {}
    if not isinstance(data, dict):
        return [], {}
    for key in WRAPPER_KEYS:
        value = data.get(key)
        if isinstance(value, list):
            meta = {k: v for k, v in data.items() if k != key}
            return [row for row in value if isinstance(row, dict)], meta
    nested = data.get("data")
    if isinstance(nested, list):
        return [row for row in nested if isinstance(row, dict)], {
            k: v for k, v in data.items() if k != "data"
        }
    if isinstance(nested, dict):
        for key in WRAPPER_KEYS:
            value = nested.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)], {
                    k: v for k, v in data.items() if k != "data"
                }
    return [data], {}


def iter_input_files(inputs: Iterable[str]) -> list[Path]:
    files: list[Path] = []
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_dir():
            files.extend(sorted(p for p in path.iterdir() if p.suffix.lower() in {".json", ".jsonl"}))
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(f"输入不存在: {path}")
    return files


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def first_value(item: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def as_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = re.split(r"[,，;/|]", str(value))
    result: list[str] = []
    for entry in values:
        if isinstance(entry, dict):
            entry = first_value(entry, "name", "title", "label")
        text = str(entry).strip()
        if text and text not in result:
            result.append(text)
    return result


def text_value(value: Any) -> str:
    if isinstance(value, dict):
        value = first_value(value, "name", "title", "label", default="")
    if isinstance(value, list):
        return "; ".join(str(v).strip() for v in value if str(v).strip())
    return str(value or "").strip()


def iso_date(value: Any) -> tuple[str, str]:
    """Return (published_at, event_date) without inventing missing dates."""
    text = text_value(value)
    if not text:
        return "", ""
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
        return text, dt.date().isoformat()
    except ValueError:
        match = re.search(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b", text)
        if match:
            return text, f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return text, ""


def stable_id(title: str, url: str) -> str:
    basis = f"{title.strip().lower()}\n{url.strip()}".encode("utf-8")
    return hashlib.sha256(basis).hexdigest()[:16]


def unwrap_payload(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    items, meta = read_json_items(path)
    return items, meta


def wrap_items(items: list[dict[str, Any]], **metadata: Any) -> dict[str, Any]:
    return {"schema_version": "2.0", **metadata, "items": items}
