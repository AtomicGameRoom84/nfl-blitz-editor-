"""Generate the synthetic demo cartridge.

Run this to get a ROM you can open in the suite without owning anything:

    python tools/make_demo_rom.py demo.z64

The file it writes is **not** NFL Blitz and contains no copyrighted data.
It is a valid N64 image containing the tables and constants described by
``games/demo_rom.json``, which lets the Team, Roster and Gameplay editors --
and the unit tests -- exercise real code paths against real data.

Because the boot code is synthetic it does not match any known CIC chip, so
the suite will (correctly) warn that it cannot verify the boot checksum.
That is a genuine limitation of a made-up ROM, not a bug.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List

if __package__ in (None, ""):  # allow running as a plain script
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.address_db import GameDefinition, TableDefinition
from core.byte_order import Z64_MAGIC

DEFINITION_PATH = Path(__file__).resolve().parent.parent / "games" / "demo_rom.json"

#: 4 MiB: comfortably larger than the 0x1000 + 0x100000 region the N64 boot
#: checksum covers, so checksum code paths are exercised.
ROM_SIZE = 4 * 1024 * 1024

INTERNAL_NAME = "MOD SUITE DEMO"
CARTRIDGE_ID = "DM"
REGION = "E"

CITIES = [
    "Ashford", "Baytown", "Cedar Fls", "Dunmore",
    "Eastvale", "Fairbrook", "Glenmoor", "Harlow",
]
NICKNAMES = [
    "Anchors", "Bandits", "Comets", "Dragons",
    "Eagles", "Foxes", "Giants", "Hawks",
]
COLORS = [
    (0xF8, 0x18, 0x18), (0x18, 0x50, 0xF8), (0x20, 0xC0, 0x40), (0xF8, 0xC0, 0x18),
    (0x90, 0x20, 0xC0), (0x20, 0xC0, 0xC0), (0xF8, 0x80, 0x20), (0x80, 0x80, 0x80),
]
POSITION_COUNT = 9


def _rgba5551(rgb: tuple[int, int, int]) -> int:
    red, green, blue = rgb
    return ((red * 31 // 255) << 11) | ((green * 31 // 255) << 6) | ((blue * 31 // 255) << 1) | 1


def build_header() -> bytes:
    """A structurally valid N64 header for a fictional cartridge."""
    header = bytearray(0x40)
    header[0x00:0x04] = Z64_MAGIC
    header[0x04:0x08] = (0x0000000F).to_bytes(4, "big")   # clock rate
    header[0x08:0x0C] = (0x80000400).to_bytes(4, "big")   # boot address
    header[0x0C:0x10] = (0x0000144C).to_bytes(4, "big")   # libultra release
    header[0x10:0x18] = bytes(8)                          # CRC1/CRC2, filled later
    header[0x20:0x34] = INTERNAL_NAME.ljust(20).encode("ascii")
    header[0x3B] = ord("N")
    header[0x3C:0x3E] = CARTRIDGE_ID.encode("ascii")
    header[0x3E] = ord(REGION)
    header[0x3F] = 0x00
    return bytes(header)


def _write_text(data: bytearray, offset: int, value: str, length: int) -> None:
    encoded = value.encode("ascii")[:length]
    data[offset : offset + length] = encoded.ljust(length, b"\x00")


def _write_number(data: bytearray, offset: int, value: int, size: int) -> None:
    data[offset : offset + size] = int(value).to_bytes(size, "big")


def fill_teams(data: bytearray, table: TableDefinition) -> None:
    for index in range(table.record_count):
        base = table.record_offset(index)
        city = CITIES[index % len(CITIES)]
        nickname = NICKNAMES[index % len(NICKNAMES)]
        abbreviation = (city[:1] + nickname[:2]).upper()
        primary = COLORS[index % len(COLORS)]
        secondary = COLORS[(index + 4) % len(COLORS)]
        for field in table.fields:
            offset = base + field.offset
            if field.id == "city":
                _write_text(data, offset, city, field.size)
            elif field.id == "nickname":
                _write_text(data, offset, nickname, field.size)
            elif field.id == "abbreviation":
                _write_text(data, offset, abbreviation, field.size)
            elif field.id == "primary_color":
                _write_number(data, offset, _rgba5551(primary), field.size)
            elif field.id == "secondary_color":
                _write_number(data, offset, _rgba5551(secondary), field.size)


def fill_players(data: bytearray, table: TableDefinition, team_count: int) -> None:
    # Deterministic pseudo-random ratings: reproducible builds make diffing
    # two generated ROMs meaningful.
    def rating(seed: int, low: int = 40, high: int = 99) -> int:
        return low + (seed * 37 + 11) % (high - low + 1)

    per_team = max(1, table.record_count // max(1, team_count))
    for index in range(table.record_count):
        base = table.record_offset(index)
        team = min(team_count - 1, index // per_team)
        position = index % POSITION_COUNT
        values: Dict[str, int | str] = {
            "name": f"PLAYER {index:02d}",
            "number": (index * 7) % 100,
            "position": position,
            "team": team,
            "speed": rating(index * 3),
            "strength": rating(index * 5),
            "agility": rating(index * 7),
            "tackling": rating(index * 11),
            "blocking": rating(index * 13),
        }
        for field in table.fields:
            offset = base + field.offset
            value = values.get(field.id, 0)
            if field.kind == "text":
                _write_text(data, offset, str(value), field.size)
            else:
                _write_number(data, offset, int(value), field.size)


def fill_entries(data: bytearray, definition: GameDefinition) -> None:
    for entry in definition.entries:
        if entry.address is None or entry.default is None:
            continue
        encoded = entry.data_type.encode(entry.default, entry.endian)
        data[entry.address : entry.address + len(encoded)] = encoded


def build_rom(definition: GameDefinition, size: int = ROM_SIZE) -> bytes:
    data = bytearray(size)
    data[0:0x40] = build_header()

    # Synthetic "boot code": recognisable filler so the region is not blank.
    for offset in range(0x40, 0x1000, 4):
        data[offset : offset + 4] = (offset ^ 0x5A5A5A5A).to_bytes(4, "big")

    teams = definition.table("teams")
    players = definition.table("players")
    if teams:
        fill_teams(data, teams)
    if players:
        fill_players(data, players, teams.record_count if teams else 1)
    fill_entries(data, definition)

    # Some plain text elsewhere so the string finder has something to locate.
    _write_text(data, 0x9000, "MOD SUITE DEMO CARTRIDGE - NOT A REAL GAME", 64)
    return bytes(data)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output",
        nargs="?",
        default="demo.z64",
        help="where to write the demo ROM (default: demo.z64)",
    )
    parser.add_argument(
        "--size",
        type=lambda v: int(v, 0),
        default=ROM_SIZE,
        help="ROM size in bytes (default: 4 MiB)",
    )
    args = parser.parse_args(argv)

    definition = GameDefinition.load(DEFINITION_PATH)
    payload = build_rom(definition, args.size)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(f"Wrote {output} ({len(payload)} bytes)")
    print(f"Matching definition: {definition.display_name} [{definition.id}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
