"""Project paths, JSON persistence, and nested configuration helpers."""

from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "configs" / "pipeline_example.json"
STATE_DIR = ROOT / ".gui_state"
STATE_PATH = STATE_DIR / "pipeline_gui_state.json"
HISTORY_PATH = STATE_DIR / "history.json"
PREVIEW_DIR = STATE_DIR / "previews"

def read_json(path: Path, fallback):
    if not path.exists():
        return copy.deepcopy(fallback)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} 不是有效 JSON：{exc}") from exc

def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def parse_value(raw: str):
    text = raw.strip()
    if text == "":
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return raw

def format_value(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)

def flatten(prefix: str, value):
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else key
            yield from flatten(child_prefix, child)
    else:
        yield prefix, value

def assign_path(payload: dict, dotted_path: str, value) -> None:
    current = payload
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value
