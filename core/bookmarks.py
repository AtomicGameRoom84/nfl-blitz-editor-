"""The address bookmark database.

Bookmarks are how a discovery stops being a line in a diff and becomes
knowledge: a name, an address, a type, a default value and notes.  They are
stored as plain JSON in the user data directory so they can be shared,
diffed and version controlled, and they are the source material for new
game-definition entries.

Nothing here knows about Qt or about NFL Blitz specifically.
"""

from __future__ import annotations

import csv
import json
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from core import paths
from core.datatypes import DataType, Endian

#: Suggested categories.  Free-form strings are accepted too; these just
#: populate the drop-down and the grouping in the UI.
DEFAULT_CATEGORIES = (
    "Movement",
    "Passing",
    "Physics",
    "Teams",
    "Rosters",
    "Graphics",
    "Audio",
    "Menus",
    "Text",
    "Uncategorised",
)

#: How sure the user is that the address does what the name says.
CONFIDENCE_LEVELS = ("unknown", "suspected", "tested", "confirmed")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Bookmark:
    """A named, typed pointer into a ROM."""

    name: str
    address: int
    data_type: DataType = DataType.U8
    endian: Endian = Endian.BIG
    category: str = "Uncategorised"
    notes: str = ""
    default_value: Optional[float] = None
    #: Suggested edit bounds for the Gameplay Values sliders.
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    confidence: str = "unknown"
    #: :attr:`core.identity.ROMIdentity.short` of the ROM it was found in.
    rom_key: str = ""
    rom_label: str = ""
    tags: List[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created: str = field(default_factory=_now)
    updated: str = field(default_factory=_now)

    # -- serialisation -----------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "address": self.address,
            "data_type": self.data_type.value,
            "endian": self.endian.value,
            "category": self.category,
            "notes": self.notes,
            "default_value": self.default_value,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "confidence": self.confidence,
            "rom_key": self.rom_key,
            "rom_label": self.rom_label,
            "tags": list(self.tags),
            "created": self.created,
            "updated": self.updated,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Bookmark":
        address = payload["address"]
        if isinstance(address, str):
            address = int(address, 0)
        return cls(
            name=payload.get("name", "Unnamed"),
            address=int(address),
            data_type=DataType.from_string(payload.get("data_type", "u8")),
            endian=Endian(payload.get("endian", "big")),
            category=payload.get("category", "Uncategorised"),
            notes=payload.get("notes", ""),
            default_value=payload.get("default_value"),
            minimum=payload.get("minimum"),
            maximum=payload.get("maximum"),
            confidence=payload.get("confidence", "unknown"),
            rom_key=payload.get("rom_key", ""),
            rom_label=payload.get("rom_label", ""),
            tags=list(payload.get("tags", [])),
            id=payload.get("id") or uuid.uuid4().hex[:12],
            created=payload.get("created", _now()),
            updated=payload.get("updated", _now()),
        )

    # -- helpers -----------------------------------------------------------

    @property
    def size(self) -> int:
        return self.data_type.size

    @property
    def end(self) -> int:
        return self.address + self.size

    @property
    def address_hex(self) -> str:
        return f"0x{self.address:08X}"

    def touched(self) -> "Bookmark":
        """Return a copy with a refreshed ``updated`` timestamp."""
        return replace(self, updated=_now())

    def read_from(self, data: bytes) -> Any:
        """Decode this bookmark's value out of a ROM buffer."""
        if self.end > len(data):
            raise IndexError(
                f"bookmark {self.name!r} at {self.address_hex} lies past the "
                f"end of a {len(data)} byte ROM"
            )
        return self.data_type.decode(data[self.address : self.end], self.endian)


class BookmarkDatabase:
    """A collection of :class:`Bookmark` objects backed by a JSON file."""

    FILE_FORMAT = "nfl-blitz-mod-suite/bookmarks"
    FILE_VERSION = 1

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else paths.bookmarks_dir() / "bookmarks.json"
        self._bookmarks: Dict[str, Bookmark] = {}
        self._listeners: List[Any] = []

    # -- notification ------------------------------------------------------

    def add_listener(self, callback) -> None:
        self._listeners.append(callback)

    def _notify(self) -> None:
        for callback in list(self._listeners):
            callback()

    # -- persistence -------------------------------------------------------

    def load(self) -> "BookmarkDatabase":
        """Load from :attr:`path`; a missing file simply yields an empty set."""
        if not self.path.exists():
            return self
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self._bookmarks = {}
        for entry in payload.get("bookmarks", []):
            try:
                bookmark = Bookmark.from_dict(entry)
            except (KeyError, ValueError):
                # Skip malformed rows rather than losing the whole file.
                continue
            self._bookmarks[bookmark.id] = bookmark
        self._notify()
        return self

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": self.FILE_FORMAT,
            "version": self.FILE_VERSION,
            "saved": _now(),
            "bookmarks": [b.to_dict() for b in self.sorted()],
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return self.path

    # -- mutation ----------------------------------------------------------

    def add(self, bookmark: Bookmark) -> Bookmark:
        self._bookmarks[bookmark.id] = bookmark
        self._notify()
        return bookmark

    def update(self, bookmark: Bookmark) -> Bookmark:
        bookmark = bookmark.touched()
        self._bookmarks[bookmark.id] = bookmark
        self._notify()
        return bookmark

    def remove(self, bookmark_id: str) -> bool:
        removed = self._bookmarks.pop(bookmark_id, None) is not None
        if removed:
            self._notify()
        return removed

    def clear(self) -> None:
        self._bookmarks.clear()
        self._notify()

    # -- queries -----------------------------------------------------------

    def get(self, bookmark_id: str) -> Optional[Bookmark]:
        return self._bookmarks.get(bookmark_id)

    def __len__(self) -> int:
        return len(self._bookmarks)

    def __iter__(self):
        return iter(self.sorted())

    def sorted(self) -> List[Bookmark]:
        """All bookmarks ordered by address then name."""
        return sorted(self._bookmarks.values(), key=lambda b: (b.address, b.name))

    def categories(self) -> List[str]:
        found = {b.category for b in self._bookmarks.values() if b.category}
        return sorted(found | set(DEFAULT_CATEGORIES))

    def query(
        self,
        text: str = "",
        category: Optional[str] = None,
        rom_key: Optional[str] = None,
        include_unscoped: bool = True,
    ) -> List[Bookmark]:
        """Filter bookmarks.

        ``rom_key`` restricts results to one ROM build.  Bookmarks saved
        without a key (``include_unscoped``) are always shown, since they are
        typically hand-entered notes that the user has not tied to a dump.
        """
        needle = text.strip().lower()
        results = []
        for bookmark in self.sorted():
            if category and bookmark.category != category:
                continue
            if rom_key is not None:
                if bookmark.rom_key and bookmark.rom_key != rom_key:
                    continue
                if not bookmark.rom_key and not include_unscoped:
                    continue
            if needle:
                haystack = " ".join(
                    [
                        bookmark.name,
                        bookmark.notes,
                        bookmark.category,
                        bookmark.address_hex,
                        " ".join(bookmark.tags),
                    ]
                ).lower()
                if needle not in haystack:
                    continue
            results.append(bookmark)
        return results

    def at_address(self, address: int) -> List[Bookmark]:
        """Bookmarks whose value range covers ``address``."""
        return [b for b in self.sorted() if b.address <= address < b.end]

    # -- import / export ---------------------------------------------------

    def export_json(self, path: str | Path, bookmarks: Optional[Iterable[Bookmark]] = None) -> Path:
        path = Path(path)
        chosen = list(bookmarks) if bookmarks is not None else self.sorted()
        payload = {
            "format": self.FILE_FORMAT,
            "version": self.FILE_VERSION,
            "saved": _now(),
            "bookmarks": [b.to_dict() for b in chosen],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def import_json(self, path: str | Path, replace_existing: bool = False) -> int:
        """Merge bookmarks from a file.  Returns how many were added.

        Entries whose ``id`` already exists are skipped unless
        ``replace_existing`` is set, which makes sharing a bookmark file
        idempotent.
        """
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        added = 0
        for entry in payload.get("bookmarks", []):
            try:
                bookmark = Bookmark.from_dict(entry)
            except (KeyError, ValueError):
                continue
            if bookmark.id in self._bookmarks and not replace_existing:
                continue
            self._bookmarks[bookmark.id] = bookmark
            added += 1
        if added:
            self._notify()
        return added

    def export_csv(self, path: str | Path) -> Path:
        path = Path(path)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "Name", "Address", "Type", "Endian", "Category",
                    "Default", "Min", "Max", "Confidence", "ROM", "Notes",
                ]
            )
            for b in self.sorted():
                writer.writerow(
                    [
                        b.name, b.address_hex, b.data_type.value, b.endian.value,
                        b.category, b.default_value, b.minimum, b.maximum,
                        b.confidence, b.rom_label or b.rom_key, b.notes,
                    ]
                )
        return path
