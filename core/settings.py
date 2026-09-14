"""Persistent application settings (a small JSON document)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from core import paths

DEFAULTS: Dict[str, Any] = {
    # ROM handling
    "auto_backup_on_load": True,
    "backup_directory": "",          # empty -> paths.backups_dir()
    "confirm_before_save": True,
    "recalculate_crc_on_save": True,
    "default_save_byte_order": "z64",
    # Hex explorer
    "hex_bytes_per_row": 16,
    "hex_font_size": 12,
    "hex_uppercase": True,
    # History
    "undo_history_limit": 500,
    # UI
    "recent_roms": [],
    "max_recent_roms": 10,
    "window_geometry": "",
    "last_directory": "",
}


class Settings:
    """Dictionary-like settings store backed by a JSON file."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else paths.settings_file()
        self._data: Dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # A corrupt settings file must never stop the app from starting.
            return
        if isinstance(loaded, dict):
            self._data.update(loaded)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, indent=2, sort_keys=True), encoding="utf-8"
        )

    # -- access ------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    def reset(self) -> None:
        self._data = dict(DEFAULTS)

    def as_dict(self) -> Dict[str, Any]:
        return dict(self._data)

    # -- recent files ------------------------------------------------------

    def push_recent_rom(self, path: str | Path) -> None:
        entry = str(Path(path).resolve())
        recent = [p for p in self.get("recent_roms", []) if p != entry]
        recent.insert(0, entry)
        del recent[self.get("max_recent_roms", 10):]
        self.set("recent_roms", recent)

    def backup_path(self) -> Path:
        configured = self.get("backup_directory") or ""
        if configured:
            path = Path(configured).expanduser()
            path.mkdir(parents=True, exist_ok=True)
            return path
        return paths.backups_dir()
