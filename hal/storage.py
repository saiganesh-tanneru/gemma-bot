"""JSON config stores: in-memory, and an atomic file used by the sim and a Linux board."""

from __future__ import annotations

import copy
import json
import logging
import os
from pathlib import Path

from hal.interfaces import ConfigStore

logger = logging.getLogger("gemma_bot_hal")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_config_path() -> Path:
    """Host file for sim config. Not created until the first commit."""
    return repo_root() / "data" / "robot-config.json"


def _check_key(key: str) -> str:
    if not isinstance(key, str) or key == "":
        raise ValueError("config key must be a non-empty string")
    return key


def _json_copy(value):
    try:
        return json.loads(json.dumps(value))
    except (TypeError, ValueError) as exc:
        raise TypeError("config values must be JSON-serializable") from exc


class _JsonConfig(ConfigStore):
    """Staged JSON object with commit and rollback. Subclasses persist the commit."""

    def __init__(self):
        self._data = {}
        self._committed = {}

    def get(self, key: str, default=None):
        key = _check_key(key)
        if key not in self._data:
            return default
        return copy.deepcopy(self._data[key])

    def set(self, key: str, value) -> None:
        key = _check_key(key)
        self._data[key] = _json_copy(value)

    def delete(self, key: str) -> None:
        key = _check_key(key)
        if key not in self._data:
            raise KeyError(key)
        del self._data[key]

    def keys(self) -> list:
        return sorted(self._data)

    def commit(self) -> None:
        self._committed = copy.deepcopy(self._data)

    def rollback(self) -> None:
        self._data = copy.deepcopy(self._committed)


class MemoryConfigStore(_JsonConfig):
    """In-memory config. commit only snapshots RAM, for tests."""


class FileConfigStore(_JsonConfig):
    """JSON file. commit writes a temp file, fsyncs it, then renames over the target.

    A crash before the rename leaves the previous file in place. The file is
    not created until the first successful commit.
    """

    def __init__(self, path: Path):
        super().__init__()
        self.path = Path(path)
        if self.path.is_file():
            self._load()
            self._committed = copy.deepcopy(self._data)

    def _load(self) -> None:
        text = self.path.read_text(encoding="utf-8")
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError(f"config file {self.path} must contain a JSON object")
        self._data = parsed

    def commit(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._data, indent=2, sort_keys=True) + "\n"
        tmp = self.path.with_name(self.path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        self._committed = copy.deepcopy(self._data)
        try:
            dir_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError as exc:
            logger.warning("config directory fsync failed after rename: %s", exc)

    def rollback(self) -> None:
        if self.path.is_file():
            self._load()
        else:
            self._data = {}
        self._committed = copy.deepcopy(self._data)
