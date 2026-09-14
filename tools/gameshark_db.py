"""Read the code database built into a GameShark firmware dump.

A GameShark Pro cartridge ships with a database of codes for hundreds of
games. If you own one, that database is a far better source than a fan-site
transcription: it is what the device itself shipped with, so the names and
values have not been through a decade of copy-and-paste.

Record format, reverse engineered from GameShark Pro (USA) v3.3 and
validated by the fact that a misaligned parse immediately produces illegal
code-type bytes::

    <game name> 00 <entry count>
      ( <description> 00 <flags> <entry count * 6 bytes of code> [FF]... )*

    each 6-byte code:  TT AAAAAA VVVV
      TT      GameShark code type (80, 81, D0, ...)
      AAAAAA  24-bit address operand
      VVVV    value

``flags`` holds the number of codes in its low seven bits; the top bit marks
the first entry of a linked group (a Home/Away pair, say). ``FF`` bytes
between entries separate those groups.

The parser stops as soon as a record stops validating, so a wrong starting
point yields nothing rather than nonsense.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.byte_order import ByteOrder, ByteOrderConverter
from tools.gameshark import CODE_TYPES, GameSharkCode

#: A record's codes must all use a type the device actually implements;
#: this is what makes a misaligned parse fail fast.
VALID_TYPES = set(CODE_TYPES)

#: Sanity limits, so a bad offset cannot run away.
MAX_ENTRIES_PER_GAME = 512
MAX_CODES_PER_ENTRY = 32
MAX_DESCRIPTION = 64


@dataclass
class DatabaseEntry:
    """One named cheat from the device database."""

    name: str
    codes: List[GameSharkCode] = field(default_factory=list)
    flags: int = 0

    @property
    def grouped(self) -> bool:
        """True when the device marks this as the head of a linked group."""
        return bool(self.flags & 0x80)

    def format(self) -> str:
        return "\n".join(code.format() for code in self.codes)

    def describe(self) -> str:
        return f"{self.name}: {'  '.join(c.format() for c in self.codes)}"


@dataclass
class DatabaseGame:
    """All entries the device knows for one game."""

    name: str
    offset: int
    declared_count: int
    entries: List[DatabaseEntry] = field(default_factory=list)

    def to_text(self) -> str:
        lines = [f"; {self.name}"]
        for entry in self.entries:
            lines.append(f"; {entry.name}")
            lines.extend(code.format() for code in entry.codes)
        return "\n".join(lines)


def load_firmware(path: str | Path) -> bytes:
    """Read a GameShark dump and normalise it to big endian."""
    raw = Path(path).read_bytes()
    order = ByteOrderConverter.detect(raw) or ByteOrder.Z64
    return bytes(ByteOrderConverter.to_big_endian(raw, order))


def _read_string(data: bytes, offset: int, limit: int = MAX_DESCRIPTION) -> Optional[Tuple[str, int]]:
    end = data.find(b"\x00", offset, offset + limit + 1)
    if end < 0 or end == offset:
        return None
    raw = data[offset:end]
    if not all(0x20 <= byte < 0x7F for byte in raw):
        return None
    return raw.decode("ascii"), end + 1


def parse_entries(data: bytes, offset: int, limit: int = MAX_ENTRIES_PER_GAME) -> Tuple[List[DatabaseEntry], int]:
    """Parse entry records from ``offset`` until one fails to validate."""
    entries: List[DatabaseEntry] = []
    position = offset
    while len(entries) < limit and position < len(data):
        header = _read_string(data, position)
        if header is None:
            break
        name, position = header
        if position >= len(data):
            break
        flags = data[position]
        position += 1
        count = flags & 0x7F
        if count == 0 or count > MAX_CODES_PER_ENTRY:
            break
        if position + count * 6 > len(data):
            break

        codes: List[GameSharkCode] = []
        valid = True
        for _ in range(count):
            type_byte = data[position]
            if type_byte not in VALID_TYPES:
                valid = False
                break
            operand = int.from_bytes(data[position + 1 : position + 4], "big")
            value = int.from_bytes(data[position + 4 : position + 6], "big")
            entry_type = CODE_TYPES[type_byte]
            codes.append(
                GameSharkCode(
                    type_byte=type_byte,
                    address=entry_type.base | operand,
                    value=value,
                    raw="",
                    comment=name,
                )
            )
            position += 6
        if not valid:
            break

        entries.append(DatabaseEntry(name=name, codes=codes, flags=flags))
        while position < len(data) and data[position] == 0xFF:
            position += 1
    return entries, position


def find_game(data: bytes, game_name: str) -> Optional[DatabaseGame]:
    """Find one game's codes by name (case-insensitive, substring)."""
    needle = game_name.lower().encode("ascii", errors="ignore")
    search = 0
    while True:
        index = data.lower().find(needle, search)
        if index < 0:
            return None
        search = index + 1
        # The name must be a complete NUL-terminated record.
        header = _read_string(data, index)
        if header is None:
            continue
        name, after = header
        if after >= len(data):
            continue
        declared = data[after]
        entries, _ = parse_entries(data, after + 1)
        if entries:
            return DatabaseGame(
                name=name, offset=index, declared_count=declared, entries=entries
            )


_GAME_NAME_RE = re.compile(rb"[\x20-\x7E]{4,48}\x00")


def list_games(data: bytes, minimum_entries: int = 3) -> List[DatabaseGame]:
    """Enumerate every game record the parser can validate.

    Heuristic by nature: it walks candidate strings and keeps the ones that
    are followed by a run of records whose code types all check out. That
    test is strict enough that false positives are rare, but this is a
    discovery aid rather than an authoritative index.
    """
    found: Dict[str, DatabaseGame] = {}
    for match in _GAME_NAME_RE.finditer(data):
        start = match.start()
        header = _read_string(data, start)
        if header is None:
            continue
        name, after = header
        if after >= len(data):
            continue
        declared = data[after]
        entries, _ = parse_entries(data, after + 1, limit=MAX_ENTRIES_PER_GAME)
        if len(entries) < minimum_entries:
            continue
        existing = found.get(name)
        if existing is None or len(entries) > len(existing.entries):
            found[name] = DatabaseGame(
                name=name, offset=start, declared_count=declared, entries=entries
            )
    return sorted(found.values(), key=lambda g: g.offset)


def codes_for(game: DatabaseGame) -> List[GameSharkCode]:
    """Flatten a game's entries into a plain code list."""
    out: List[GameSharkCode] = []
    for entry in game.entries:
        out.extend(entry.codes)
    return out
