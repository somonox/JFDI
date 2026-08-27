"""Backward-compatible loading and atomic persistence for JFDI task JSON."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

CURRENT_SCHEMA_VERSION = 2


def migrate_task_document(raw: Any) -> tuple[dict[str, Any], bool]:
    source = raw if isinstance(raw, dict) else {}
    document = dict(source)
    changed = source.get("schema_version", 1) < CURRENT_SCHEMA_VERSION

    raw_tasks = source.get("tasks", {})
    tasks: dict[int, dict[str, Any]] = {}
    if isinstance(raw_tasks, dict):
        for raw_id, raw_task in raw_tasks.items():
            try:
                task_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if isinstance(raw_task, dict):
                tasks[task_id] = dict(raw_task)

    highest_id = max(tasks, default=0)
    try:
        counter = int(source.get("counter", 1))
    except (TypeError, ValueError):
        counter = 1
    counter = max(counter, highest_id + 1)

    document["schema_version"] = CURRENT_SCHEMA_VERSION
    document["counter"] = counter
    document["tasks"] = tasks
    if not isinstance(document.get("user_dnd"), dict):
        document["user_dnd"] = {}
        changed = True
    return document, changed


def load_task_document(path: str | Path) -> tuple[dict[str, Any], bool]:
    source_path = Path(path)
    if not source_path.exists():
        return migrate_task_document({})
    with source_path.open("r", encoding="utf-8") as handle:
        return migrate_task_document(json.load(handle))


def save_json_atomic(
    path: str | Path,
    document: dict[str, Any],
    *,
    file_mode: int | None = None,
) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        file_mode if file_mode is not None else 0o666,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=4)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, destination)
    if file_mode is not None:
        os.chmod(destination, file_mode)


def backup_legacy_file(path: str | Path) -> Path | None:
    source = Path(path)
    backup = source.with_name(f"{source.stem}.v1.backup{source.suffix}")
    if not source.exists() or backup.exists():
        return None
    shutil.copy2(source, backup)
    return backup
