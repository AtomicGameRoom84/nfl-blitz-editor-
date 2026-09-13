"""Backups of the user's original ROM files.

The suite never writes to a loaded ROM, so a backup is strictly belt and
braces -- but the cost of losing an irreplaceable personal dump is high
enough that it is made automatically on load by default.

Backups are byte-for-byte copies of the file *as it was on disk*, including
its original byte order, so restoring one gives back exactly the file the
user had.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from core import paths

INDEX_FILENAME = "backup_index.json"


@dataclass(frozen=True)
class BackupRecord:
    """One stored backup."""

    path: Path
    source_path: str
    created: str
    size: int
    sha1: str
    note: str = ""

    @property
    def created_display(self) -> str:
        try:
            return datetime.fromisoformat(self.created).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return self.created

    @property
    def exists(self) -> bool:
        return self.path.exists()

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "source_path": self.source_path,
            "created": self.created,
            "size": self.size,
            "sha1": self.sha1,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "BackupRecord":
        return cls(
            path=Path(payload["path"]),
            source_path=payload.get("source_path", ""),
            created=payload.get("created", ""),
            size=int(payload.get("size", 0)),
            sha1=payload.get("sha1", ""),
            note=payload.get("note", ""),
        )


class BackupManager:
    """Creates, indexes and restores ROM backups."""

    def __init__(self, directory: Optional[Path] = None) -> None:
        self.directory = Path(directory) if directory else paths.backups_dir()
        self.directory.mkdir(parents=True, exist_ok=True)
        self._records: List[BackupRecord] = []
        self.load_index()

    # -- index -------------------------------------------------------------

    @property
    def index_path(self) -> Path:
        return self.directory / INDEX_FILENAME

    def load_index(self) -> None:
        if not self.index_path.exists():
            self._records = []
            return
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._records = []
            return
        self._records = [BackupRecord.from_dict(r) for r in payload.get("backups", [])]

    def save_index(self) -> None:
        self.index_path.write_text(
            json.dumps(
                {"backups": [r.to_dict() for r in self._records]}, indent=2
            ),
            encoding="utf-8",
        )

    # -- operations --------------------------------------------------------

    @staticmethod
    def _sha1_of(path: Path) -> str:
        digest = hashlib.sha1()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def has_backup_of(self, source: str | Path) -> bool:
        """Whether an intact backup of this exact file content already exists."""
        source = Path(source)
        if not source.exists():
            return False
        digest = self._sha1_of(source)
        return any(r.sha1 == digest and r.exists for r in self._records)

    def create_backup(
        self,
        source: str | Path,
        note: str = "",
        skip_if_duplicate: bool = True,
    ) -> Optional[BackupRecord]:
        """Copy ``source`` into the backup directory.

        Returns ``None`` when ``skip_if_duplicate`` is set and an identical
        backup already exists, so loading the same ROM ten times does not
        produce ten copies.
        """
        source = Path(source).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(f"cannot back up missing file: {source}")
        digest = self._sha1_of(source)
        if skip_if_duplicate:
            for record in self._records:
                if record.sha1 == digest and record.exists:
                    return None

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        destination = self.directory / f"{source.stem}_{stamp}{source.suffix}"
        counter = 1
        while destination.exists():
            destination = self.directory / f"{source.stem}_{stamp}_{counter}{source.suffix}"
            counter += 1

        shutil.copy2(source, destination)
        record = BackupRecord(
            path=destination,
            source_path=str(source),
            created=datetime.now().isoformat(timespec="seconds"),
            size=destination.stat().st_size,
            sha1=digest,
            note=note,
        )
        self._records.insert(0, record)
        self.save_index()
        return record

    def backups(self, source: Optional[str | Path] = None) -> List[BackupRecord]:
        """All backups, newest first, optionally filtered by source path."""
        records = sorted(self._records, key=lambda r: r.created, reverse=True)
        if source is None:
            return records
        wanted = str(Path(source).expanduser().resolve())
        return [r for r in records if r.source_path == wanted]

    def restore(self, record: BackupRecord, destination: str | Path) -> Path:
        """Copy a backup back out to ``destination``.

        The caller chooses the destination; this never silently writes over
        the path the backup came from.
        """
        destination = Path(destination).expanduser().resolve()
        if not record.path.exists():
            raise FileNotFoundError(f"backup file is missing: {record.path}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(record.path, destination)
        return destination

    def delete(self, record: BackupRecord) -> bool:
        """Remove a backup file and its index entry."""
        removed = False
        if record.path.exists():
            record.path.unlink()
            removed = True
        self._records = [r for r in self._records if r.path != record.path]
        self.save_index()
        return removed

    def prune(self, keep: int = 20) -> int:
        """Delete all but the ``keep`` most recent backups.  Returns the count."""
        records = sorted(self._records, key=lambda r: r.created, reverse=True)
        doomed = records[keep:]
        for record in doomed:
            if record.path.exists():
                record.path.unlink()
        self._records = records[:keep]
        self.save_index()
        return len(doomed)

    def total_size(self) -> int:
        return sum(r.size for r in self._records if r.exists)
