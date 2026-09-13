"""Game definitions: the separation between "what the ROM contains" and "the UI".

No editor in this suite hardcodes a ROM address.  Every address lives in a
JSON definition file under ``games/`` (shipped) or in the user's data
directory (discovered), and the editors render whatever the definition
for the loaded ROM declares.  Adding support for a new NFL Blitz build is
therefore a data change, not a code change.

A definition may -- and for an un-reverse-engineered game *should* --
declare entries whose address is ``null``.  Those describe a value the
project wants to find but has not located yet.  They render in the UI as
greyed-out "not discovered" rows instead of quietly pretending to work.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core import paths
from core.datatypes import DataType, Endian
from core.identity import ROMIdentity

SCHEMA_VERSION = 1

#: Vocabulary for how well established an entry is.  Anything other than
#: ``confirmed`` is surfaced to the user with a warning badge.
CONFIDENCE_LEVELS = ("undiscovered", "guess", "experimental", "tested", "confirmed")

#: Categories that map onto the sidebar sections of the Gameplay editors.
KNOWN_CATEGORIES = (
    "movement",
    "passing",
    "physics",
    "teams",
    "rosters",
    "graphics",
    "audio",
    "menus",
    "misc",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ValueEntry:
    """One editable scalar described by a game definition."""

    id: str
    name: str
    category: str = "misc"
    group: str = ""
    address: Optional[int] = None
    data_type: DataType = DataType.U16
    endian: Endian = Endian.BIG
    default: Optional[float] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    step: float = 1.0
    #: Displayed value = raw * scale.  Lets a definition present a fixed-point
    #: raw value in game units without the UI knowing anything about it.
    scale: float = 1.0
    unit: str = ""
    confidence: str = "undiscovered"
    source: str = ""
    notes: str = ""

    @property
    def is_discovered(self) -> bool:
        """Whether this entry actually points somewhere in the ROM."""
        return self.address is not None

    @property
    def is_verified(self) -> bool:
        return self.confidence in ("tested", "confirmed")

    @property
    def address_hex(self) -> str:
        return f"0x{self.address:08X}" if self.address is not None else "-"

    def effective_bounds(self) -> tuple[float, float]:
        """Slider bounds: the declared ones, else the data type's full range."""
        low = self.minimum
        high = self.maximum
        if low is None:
            low = self.data_type.minimum if self.data_type.minimum is not None else -1e9
        if high is None:
            high = self.data_type.maximum if self.data_type.maximum is not None else 1e9
        return float(low), float(high)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "group": self.group,
            "address": self.address,
            "data_type": self.data_type.value,
            "endian": self.endian.value,
            "default": self.default,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "step": self.step,
            "scale": self.scale,
            "unit": self.unit,
            "confidence": self.confidence,
            "source": self.source,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ValueEntry":
        address = payload.get("address")
        if isinstance(address, str):
            address = int(address, 0)
        return cls(
            id=payload["id"],
            name=payload.get("name", payload["id"]),
            category=payload.get("category", "misc"),
            group=payload.get("group", ""),
            address=address,
            data_type=DataType.from_string(payload.get("data_type", "u16")),
            endian=Endian(payload.get("endian", "big")),
            default=payload.get("default"),
            minimum=payload.get("minimum"),
            maximum=payload.get("maximum"),
            step=float(payload.get("step", 1.0)),
            scale=float(payload.get("scale", 1.0)),
            unit=payload.get("unit", ""),
            confidence=payload.get("confidence", "undiscovered"),
            source=payload.get("source", ""),
            notes=payload.get("notes", ""),
        )


@dataclass
class FieldDefinition:
    """One column of a record inside a table (a player, a team, ...)."""

    id: str
    name: str
    offset: int
    data_type: DataType = DataType.U8
    endian: Endian = Endian.BIG
    #: ``text`` fields use ``length`` instead of the data type's size.
    length: Optional[int] = None
    kind: str = "number"  # number | text | enum | color
    options: Dict[str, Any] = field(default_factory=dict)
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    notes: str = ""

    @property
    def size(self) -> int:
        return self.length if self.length is not None else self.data_type.size

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "id": self.id,
            "name": self.name,
            "offset": self.offset,
            "data_type": self.data_type.value,
            "endian": self.endian.value,
            "kind": self.kind,
            "notes": self.notes,
        }
        if self.length is not None:
            payload["length"] = self.length
        if self.options:
            payload["options"] = self.options
        if self.minimum is not None:
            payload["minimum"] = self.minimum
        if self.maximum is not None:
            payload["maximum"] = self.maximum
        return payload

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "FieldDefinition":
        offset = payload.get("offset", 0)
        if isinstance(offset, str):
            offset = int(offset, 0)
        return cls(
            id=payload["id"],
            name=payload.get("name", payload["id"]),
            offset=int(offset),
            data_type=DataType.from_string(payload.get("data_type", "u8")),
            endian=Endian(payload.get("endian", "big")),
            length=payload.get("length"),
            kind=payload.get("kind", "number"),
            options=payload.get("options", {}) or {},
            minimum=payload.get("minimum"),
            maximum=payload.get("maximum"),
            notes=payload.get("notes", ""),
        )


@dataclass
class TableDefinition:
    """A fixed-stride array of records -- the shape rosters and teams take.

    ``base_address`` of ``None`` means the table's location has not been
    found yet; the corresponding editor then reports itself unavailable for
    this ROM rather than showing invented data.
    """

    id: str
    name: str
    base_address: Optional[int] = None
    record_size: int = 0
    record_count: int = 0
    fields: List[FieldDefinition] = field(default_factory=list)
    confidence: str = "undiscovered"
    notes: str = ""

    @property
    def is_discovered(self) -> bool:
        return (
            self.base_address is not None
            and self.record_size > 0
            and self.record_count > 0
            and bool(self.fields)
        )

    def record_offset(self, index: int) -> int:
        if self.base_address is None:
            raise ValueError(f"table {self.id!r} has no base address")
        if not 0 <= index < self.record_count:
            raise IndexError(f"record {index} out of range for table {self.id!r}")
        return self.base_address + index * self.record_size

    def field(self, field_id: str) -> Optional[FieldDefinition]:
        for item in self.fields:
            if item.id == field_id:
                return item
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "base_address": self.base_address,
            "record_size": self.record_size,
            "record_count": self.record_count,
            "confidence": self.confidence,
            "notes": self.notes,
            "fields": [f.to_dict() for f in self.fields],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "TableDefinition":
        base = payload.get("base_address")
        if isinstance(base, str):
            base = int(base, 0)
        return cls(
            id=payload["id"],
            name=payload.get("name", payload["id"]),
            base_address=base,
            record_size=int(payload.get("record_size", 0)),
            record_count=int(payload.get("record_count", 0)),
            fields=[FieldDefinition.from_dict(f) for f in payload.get("fields", [])],
            confidence=payload.get("confidence", "undiscovered"),
            notes=payload.get("notes", ""),
        )


@dataclass
class Identification:
    """Rules for deciding whether a definition applies to a loaded ROM."""

    sha1: List[str] = field(default_factory=list)
    crc_pairs: List[List[int]] = field(default_factory=list)
    cartridge_ids: List[str] = field(default_factory=list)
    region_codes: List[str] = field(default_factory=list)
    internal_name_matches: List[str] = field(default_factory=list)
    rom_sizes: List[int] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Identification":
        def as_int(value: Any) -> int:
            return int(value, 0) if isinstance(value, str) else int(value)

        return cls(
            sha1=[s.lower() for s in payload.get("sha1", [])],
            crc_pairs=[[as_int(a), as_int(b)] for a, b in payload.get("crc_pairs", [])],
            cartridge_ids=list(payload.get("cartridge_ids", [])),
            region_codes=list(payload.get("region_codes", [])),
            internal_name_matches=list(payload.get("internal_name_matches", [])),
            rom_sizes=[as_int(v) for v in payload.get("rom_sizes", [])],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sha1": self.sha1,
            "crc_pairs": [[f"0x{a:08X}", f"0x{b:08X}"] for a, b in self.crc_pairs],
            "cartridge_ids": self.cartridge_ids,
            "region_codes": self.region_codes,
            "internal_name_matches": self.internal_name_matches,
            "rom_sizes": self.rom_sizes,
        }


@dataclass
class MatchResult:
    """How well a definition fits the loaded ROM."""

    definition: "GameDefinition"
    score: int
    reasons: List[str]

    @property
    def exact(self) -> bool:
        """``True`` only when a SHA-1 or CRC pair matched."""
        return self.score >= 100


@dataclass
class GameDefinition:
    """Everything the suite knows about one build of one game."""

    id: str
    game: str
    version_label: str = ""
    platform: str = "N64"
    schema_version: int = SCHEMA_VERSION
    notes: str = ""
    identification: Identification = field(default_factory=Identification)
    entries: List[ValueEntry] = field(default_factory=list)
    tables: List[TableDefinition] = field(default_factory=list)
    source_path: Optional[Path] = None
    #: True when the file came from the user data directory.
    user_defined: bool = False

    # -- queries -----------------------------------------------------------

    @property
    def display_name(self) -> str:
        return f"{self.game} ({self.version_label})" if self.version_label else self.game

    def entry(self, entry_id: str) -> Optional[ValueEntry]:
        for item in self.entries:
            if item.id == entry_id:
                return item
        return None

    def table(self, table_id: str) -> Optional[TableDefinition]:
        for item in self.tables:
            if item.id == table_id:
                return item
        return None

    def entries_in(self, category: str, discovered_only: bool = False) -> List[ValueEntry]:
        items = [e for e in self.entries if e.category == category]
        if discovered_only:
            items = [e for e in items if e.is_discovered]
        return items

    def groups_in(self, category: str) -> List[str]:
        """Ordered, de-duplicated group names inside a category."""
        seen: List[str] = []
        for entry in self.entries_in(category):
            label = entry.group or "General"
            if label not in seen:
                seen.append(label)
        return seen

    @property
    def discovered_count(self) -> int:
        return sum(1 for e in self.entries if e.is_discovered)

    def stats(self) -> Dict[str, int]:
        return {
            "entries": len(self.entries),
            "discovered": self.discovered_count,
            "undiscovered": len(self.entries) - self.discovered_count,
            "tables": len(self.tables),
            "tables_discovered": sum(1 for t in self.tables if t.is_discovered),
        }

    # -- matching ----------------------------------------------------------

    def match(self, identity: ROMIdentity) -> Optional[MatchResult]:
        """Score this definition against a loaded ROM.

        Scoring is additive so a weak signal (the internal name contains
        "BLITZ") still produces a usable match while a fingerprint match
        always outranks it.
        """
        ident = self.identification
        score = 0
        reasons: List[str] = []

        if identity.sha1.lower() in ident.sha1:
            score += 120
            reasons.append("SHA-1 fingerprint matches")
        if [identity.crc1, identity.crc2] in ident.crc_pairs:
            score += 100
            reasons.append(
                f"Boot CRC {identity.crc1:08X}/{identity.crc2:08X} matches"
            )
        if ident.cartridge_ids and identity.game_code[1:3] in ident.cartridge_ids:
            score += 30
            reasons.append(f"Cartridge ID {identity.game_code[1:3]!r} matches")
        if ident.region_codes and identity.game_code[-1:] in ident.region_codes:
            score += 10
            reasons.append(f"Region {identity.game_code[-1:]!r} matches")
        # Earlier patterns are more specific by convention, so they score
        # higher. That is what keeps a ROM named "NFL BLITZ 2000" matching the
        # 2000 definition rather than tying with the base game's catch-all.
        for index, pattern in enumerate(ident.internal_name_matches):
            try:
                if re.search(pattern, identity.image_name):
                    score += max(25 - 10 * index, 5)
                    reasons.append(
                        f"Internal name {identity.image_name!r} matches /{pattern}/"
                    )
                    break
            except re.error:
                continue
        if ident.rom_sizes and identity.size in ident.rom_sizes:
            score += 5
            reasons.append(f"ROM size {identity.size} matches")

        if score == 0:
            return None
        return MatchResult(definition=self, score=score, reasons=reasons)

    # -- serialisation -----------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "game": self.game,
            "version_label": self.version_label,
            "platform": self.platform,
            "notes": self.notes,
            "identification": self.identification.to_dict(),
            "entries": [e.to_dict() for e in self.entries],
            "tables": [t.to_dict() for t in self.tables],
            "updated": _now(),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any], source: Optional[Path] = None) -> "GameDefinition":
        version = int(payload.get("schema_version", SCHEMA_VERSION))
        if version > SCHEMA_VERSION:
            raise ValueError(
                f"definition {payload.get('id')!r} uses schema version "
                f"{version}; this build understands up to {SCHEMA_VERSION}"
            )
        return cls(
            id=payload["id"],
            game=payload.get("game", payload["id"]),
            version_label=payload.get("version_label", ""),
            platform=payload.get("platform", "N64"),
            schema_version=version,
            notes=payload.get("notes", ""),
            identification=Identification.from_dict(payload.get("identification", {})),
            entries=[ValueEntry.from_dict(e) for e in payload.get("entries", [])],
            tables=[TableDefinition.from_dict(t) for t in payload.get("tables", [])],
            source_path=source,
        )

    @classmethod
    def load(cls, path: str | Path) -> "GameDefinition":
        path = Path(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(payload, source=path)

    def save(self, path: Optional[str | Path] = None) -> Path:
        target = Path(path) if path else (self.source_path or (paths.user_games_dir() / f"{self.id}.json"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        self.source_path = target
        return target


class AddressDatabase:
    """Loads every game definition and picks the one matching a loaded ROM."""

    def __init__(
        self,
        builtin_dir: Optional[Path] = None,
        user_dir: Optional[Path] = None,
    ) -> None:
        self.builtin_dir = Path(builtin_dir) if builtin_dir else paths.BUILTIN_GAMES_DIR
        self._user_dir_override = Path(user_dir) if user_dir else None
        self.definitions: Dict[str, GameDefinition] = {}
        self.load_errors: List[str] = []

    @property
    def user_dir(self) -> Path:
        return self._user_dir_override or paths.user_games_dir()

    # -- loading -----------------------------------------------------------

    def load_all(self) -> "AddressDatabase":
        """(Re)load definitions.  User files override built-ins with the same id."""
        self.definitions = {}
        self.load_errors = []
        for directory, is_user in ((self.builtin_dir, False), (self.user_dir, True)):
            if not directory or not Path(directory).is_dir():
                continue
            for path in sorted(Path(directory).glob("*.json")):
                try:
                    definition = GameDefinition.load(path)
                except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                    self.load_errors.append(f"{path.name}: {exc}")
                    continue
                definition.user_defined = is_user
                self.definitions[definition.id] = definition
        return self

    def get(self, definition_id: str) -> Optional[GameDefinition]:
        return self.definitions.get(definition_id)

    def all(self) -> List[GameDefinition]:
        return sorted(self.definitions.values(), key=lambda d: d.display_name)

    # -- identification ----------------------------------------------------

    def identify(self, identity: ROMIdentity) -> List[MatchResult]:
        """All matching definitions, best first."""
        matches = []
        for definition in self.definitions.values():
            result = definition.match(identity)
            if result is not None:
                matches.append(result)
        matches.sort(key=lambda m: (-m.score, m.definition.display_name))
        return matches

    def best_match(self, identity: ROMIdentity) -> Optional[MatchResult]:
        matches = self.identify(identity)
        return matches[0] if matches else None

    # -- authoring ---------------------------------------------------------

    def user_copy(self, definition: GameDefinition) -> GameDefinition:
        """Return an editable copy of a definition stored in the user directory.

        Built-in files ship read-only; the first time a user adds a
        discovered address the definition is forked into their data
        directory, where it shadows the built-in one on the next load.
        """
        if definition.user_defined:
            return definition
        forked = GameDefinition.from_dict(definition.to_dict())
        forked.user_defined = True
        forked.source_path = self.user_dir / f"{definition.id}.json"
        forked.notes = (
            definition.notes
            + ("\n\n" if definition.notes else "")
            + f"Forked into the user data directory on {_now()}."
        ).strip()
        self.definitions[forked.id] = forked
        return forked

    def register_fingerprint(
        self, definition: GameDefinition, identity: ROMIdentity
    ) -> GameDefinition:
        """Record the loaded ROM's fingerprint so it matches exactly next time.

        This is how an unverified definition becomes verified for *your* dump
        without anyone shipping a CRC value they cannot check.
        """
        target = self.user_copy(definition)
        pair = [identity.crc1, identity.crc2]
        if pair not in target.identification.crc_pairs:
            target.identification.crc_pairs.append(pair)
        if identity.sha1.lower() not in target.identification.sha1:
            target.identification.sha1.append(identity.sha1.lower())
        if identity.size not in target.identification.rom_sizes:
            target.identification.rom_sizes.append(identity.size)
        target.save()
        return target

    def add_entry(self, definition: GameDefinition, entry: ValueEntry) -> GameDefinition:
        """Add or replace an entry and persist to the user directory."""
        target = self.user_copy(definition)
        # Replace in place when the id already exists, otherwise append, so a
        # hand-authored file keeps the order its author chose.
        replaced = False
        for index, existing in enumerate(target.entries):
            if existing.id == entry.id:
                target.entries[index] = entry
                replaced = True
                break
        if not replaced:
            target.entries.append(entry)
        target.save()
        return target

    def remove_entry(self, definition: GameDefinition, entry_id: str) -> GameDefinition:
        target = self.user_copy(definition)
        target.entries = [e for e in target.entries if e.id != entry_id]
        target.save()
        return target


def entry_from_bookmark(bookmark, category: Optional[str] = None) -> ValueEntry:
    """Convert a :class:`core.bookmarks.Bookmark` into a definition entry.

    This is the bridge that turns a discovery into a permanent, shareable
    part of the game definition, and therefore into a control in the
    Gameplay Values editor.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", bookmark.name.strip().lower()).strip("_")
    confidence = {
        "unknown": "guess",
        "suspected": "experimental",
        "tested": "tested",
        "confirmed": "confirmed",
    }.get(bookmark.confidence, "experimental")
    return ValueEntry(
        id=slug or f"bookmark_{bookmark.id}",
        name=bookmark.name,
        category=(category or bookmark.category or "misc").lower(),
        group="",
        address=bookmark.address,
        data_type=bookmark.data_type,
        endian=bookmark.endian,
        default=bookmark.default_value,
        minimum=bookmark.minimum,
        maximum=bookmark.maximum,
        confidence=confidence,
        source=f"Bookmark {bookmark.id} ({bookmark.rom_label or bookmark.rom_key})",
        notes=bookmark.notes,
    )
