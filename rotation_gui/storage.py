"""Project paths, JSON persistence, and nested configuration helpers."""

from __future__ import annotations

import copy
import datetime as dt
import json
import os
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "configs" / "chirp_point_target_test.json"
STATE_DIR = ROOT / ".gui_state"
STATE_PATH = STATE_DIR / "pipeline_gui_state.json"
PREVIEW_DIR = STATE_DIR / "previews"

def read_json(path: Path, fallback):
    if not path.exists():
        return copy.deepcopy(fallback)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} 不是有效 JSON：{exc}") from exc

def write_json(path: Path, payload) -> None:
    """Atomically replace ``path`` so a failed write leaves the previous file."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    handle, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_json_new(path: Path, payload) -> None:
    """Atomically publish a complete JSON file only if its name is unused."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    handle, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(tmp_name, path)  # Fails if another process created path meanwhile.
    finally:
        try:
            os.unlink(tmp_name)
        except OSError:
            # Publishing may already have succeeded; cleanup must not report
            # a failed Save As after the destination file is complete.
            pass

def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def parse_value(raw: str):
    text = raw.strip()
    if text == "":
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Vector components are entered in individual editors.  Accept the
        # conventional thousands separators users naturally type there while
        # retaining JSON parsing for lists, objects, booleans, and null above.
        grouped_number = re.fullmatch(
            r"[+-]?(?:\d{1,3}(?:,\d{3})+)(?:\.\d+)?(?:[eE][+-]?\d+)?",
            text,
        )
        if grouped_number:
            normalized = text.replace(",", "")
            return float(normalized) if any(char in normalized for char in ".eE") else int(normalized)
        return raw

def format_value(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)

def assign_path(payload: dict, dotted_path: str, value) -> None:
    current = payload
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value
