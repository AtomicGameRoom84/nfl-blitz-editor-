"""Nintendo 64 GameShark / Action Replay codes.

A GameShark code is a RAM patch: the device writes a value into the console's
memory, usually every frame. That makes the enormous published corpus of N64
codes a research goldmine -- someone has already found the address -- but it
also means a code is **not** automatically a ROM edit:

* A code whose address lies in a region the ROM is copied into can often be
  turned into a permanent ROM patch, provided the game does not recompute the
  value at runtime.
* A code pointing at runtime state -- a score, a per-frame flag, anything in
  the heap or stack -- has no ROM counterpart at all. Writing "the same"
  bytes somewhere in the ROM would be meaningless.

This module parses codes, explains what they do, and converts the ones that
*can* be converted, using an explicit, range-limited RAM to ROM mapping. When
an address falls outside the verified range it says so instead of guessing.

Code type reference: see ``docs/GAMESHARK_N64.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from core.rom_manager import ROMManager
from core.undo import CompositeCommand, WriteBytesCommand

#: KSEG0: cached, unmapped view of RDRAM. GameShark addresses are given as the
#: low 24 bits and are implicitly based here.
KSEG0_BASE = 0x80000000
#: KSEG1: the same memory, uncached. The ``A0``/``A1`` code types use it.
KSEG1_BASE = 0xA0000000


@dataclass(frozen=True)
class CodeType:
    """One GameShark opcode."""

    byte: int
    name: str
    #: Bytes written, or 0 for codes that do not write memory.
    width: int
    #: True when the code writes game memory (and so might map to the ROM).
    writes_memory: bool
    #: True when the write happens once at boot rather than every frame.
    once: bool
    base: int
    description: str


#: The opcodes this module understands. Anything else is reported as
#: unsupported rather than being guessed at -- a mis-applied code would
#: silently corrupt a ROM.
CODE_TYPES: Dict[int, CodeType] = {
    0x80: CodeType(0x80, "8-bit constant write", 1, True, False, KSEG0_BASE,
                   "Writes one byte to the address, repeatedly."),
    0x81: CodeType(0x81, "16-bit constant write", 2, True, False, KSEG0_BASE,
                   "Writes two bytes to the address, repeatedly."),
    0xA0: CodeType(0xA0, "8-bit constant write (uncached)", 1, True, False, KSEG1_BASE,
                   "Writes one byte through the uncached KSEG1 view."),
    0xA1: CodeType(0xA1, "16-bit constant write (uncached)", 2, True, False, KSEG1_BASE,
                   "Writes two bytes through the uncached KSEG1 view."),
    0x88: CodeType(0x88, "8-bit write on GS button", 1, True, False, KSEG0_BASE,
                   "Writes one byte each time the GameShark button is pressed."),
    0x89: CodeType(0x89, "16-bit write on GS button", 2, True, False, KSEG0_BASE,
                   "Writes two bytes each time the GameShark button is pressed."),
    0xF0: CodeType(0xF0, "8-bit boot-time write", 1, True, True, KSEG1_BASE,
                   "Writes one byte once, at boot."),
    0xF1: CodeType(0xF1, "16-bit boot-time write", 2, True, True, KSEG1_BASE,
                   "Writes two bytes once, at boot."),
    0xD0: CodeType(0xD0, "if 8-bit equal", 1, False, False, KSEG0_BASE,
                   "Runs the next code only if the byte at the address matches."),
    0xD1: CodeType(0xD1, "if 16-bit equal", 2, False, False, KSEG0_BASE,
                   "Runs the next code only if the halfword at the address matches."),
    0xD2: CodeType(0xD2, "if 8-bit not equal", 1, False, False, KSEG0_BASE,
                   "Runs the next code only if the byte at the address differs."),
    0xD3: CodeType(0xD3, "if 16-bit not equal", 2, False, False, KSEG0_BASE,
                   "Runs the next code only if the halfword at the address differs."),
    0x50: CodeType(0x50, "serial repeater", 0, False, False, KSEG0_BASE,
                   "Repeats the following write, stepping the address and value."),
    0xEE: CodeType(0xEE, "disable expansion pak", 0, False, False, KSEG0_BASE,
                   "Device directive; affects no game memory."),
    0xDE: CodeType(0xDE, "set entry point", 0, False, False, KSEG0_BASE,
                   "Device directive; affects no game memory."),
    0xFF: CodeType(0xFF, "set code store", 0, False, False, KSEG0_BASE,
                   "Device directive; affects no game memory."),
    0xCC: CodeType(0xCC, "device directive", 0, False, False, KSEG0_BASE,
                   "Device directive; affects no game memory."),
}

_CODE_RE = re.compile(
    r"^\s*([0-9A-Fa-f]{8})\s*[: ]?\s*([0-9A-Fa-f]{4})\s*(?:[;#/]+\s*(.*))?$"
)
#: Some lists write codes without the space, as one 12-digit run.
_CODE_RE_TIGHT = re.compile(r"^\s*([0-9A-Fa-f]{8})([0-9A-Fa-f]{4})\s*(?:[;#/]+\s*(.*))?$")


class GameSharkError(Exception):
    """Raised when a code list cannot be parsed at all."""


@dataclass(frozen=True)
class GameSharkCode:
    """One parsed code line."""

    type_byte: int
    #: The 24-bit operand, already combined with the type's memory base.
    address: int
    value: int
    raw: str
    comment: str = ""

    @property
    def type(self) -> Optional[CodeType]:
        return CODE_TYPES.get(self.type_byte)

    @property
    def supported(self) -> bool:
        return self.type_byte in CODE_TYPES

    @property
    def writes_memory(self) -> bool:
        return bool(self.type and self.type.writes_memory)

    @property
    def width(self) -> int:
        return self.type.width if self.type else 0

    @property
    def payload(self) -> bytes:
        """The bytes this code writes, big endian."""
        if self.width == 1:
            return bytes([self.value & 0xFF])
        if self.width == 2:
            return (self.value & 0xFFFF).to_bytes(2, "big")
        return b""

    @property
    def normalised_address(self) -> int:
        """The address as a KSEG0 (``0x80……``) address, whatever base it used."""
        return (self.address & 0x1FFFFFFF) | KSEG0_BASE

    def format(self) -> str:
        return f"{self.type_byte:02X}{self.address & 0xFFFFFF:06X} {self.value & 0xFFFF:04X}"

    def describe(self) -> str:
        if not self.supported:
            return f"{self.format()}  -- unsupported code type {self.type_byte:02X}"
        return f"{self.format()}  {self.type.name} at 0x{self.normalised_address:08X}"


def parse_line(line: str) -> Optional[GameSharkCode]:
    """Parse one code line, or return ``None`` for a blank/comment line.

    Raises ``GameSharkError`` when a non-blank line is not a code.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith(("#", "//", ";", "[")):
        return None
    match = _CODE_RE.match(stripped) or _CODE_RE_TIGHT.match(stripped)
    if not match:
        raise GameSharkError(f"not a GameShark code: {line.strip()!r}")
    left, right, comment = match.group(1), match.group(2), match.group(3) or ""
    word = int(left, 16)
    type_byte = (word >> 24) & 0xFF
    operand = word & 0xFFFFFF
    entry = CODE_TYPES.get(type_byte)
    base = entry.base if entry else KSEG0_BASE
    return GameSharkCode(
        type_byte=type_byte,
        address=base | operand,
        value=int(right, 16),
        raw=stripped,
        comment=comment.strip(),
    )


def parse_list(text: str) -> Tuple[List[GameSharkCode], List[str]]:
    """Parse a block of codes.

    Returns the codes that parsed and a list of readable problems, so a list
    with one bad line still yields the rest.
    """
    codes: List[GameSharkCode] = []
    problems: List[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        try:
            code = parse_line(line)
        except GameSharkError as exc:
            problems.append(f"line {number}: {exc}")
            continue
        if code is not None:
            codes.append(code)
    return codes, problems


def make_code(address: int, value: int, width: int = 1, gs_button: bool = False) -> GameSharkCode:
    """Build a constant-write code for a RAM address."""
    if width == 1:
        type_byte = 0x88 if gs_button else 0x80
    elif width == 2:
        type_byte = 0x89 if gs_button else 0x81
    else:
        raise ValueError("GameShark constant writes are 1 or 2 bytes wide")
    return GameSharkCode(
        type_byte=type_byte,
        address=(address & 0x1FFFFFFF) | KSEG0_BASE,
        value=value & (0xFF if width == 1 else 0xFFFF),
        raw="",
    )


def float_high_half(value: float) -> int:
    """The top 16 bits of a big endian float, for a ``81`` code.

    Published N64 codes often set a float by writing only its upper halfword
    -- ``42C8`` is the top half of ``100.0`` -- because that is enough to
    change the exponent and leading mantissa bits.
    """
    import struct

    return int.from_bytes(struct.pack(">f", float(value))[:2], "big")


# ---------------------------------------------------------------------------
# RAM -> ROM mapping
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MappedRange:
    """A RAM window known to be a verbatim copy of part of the ROM."""

    ram_start: int
    ram_end: int          # exclusive
    rom_start: int
    note: str = ""

    @property
    def delta(self) -> int:
        return self.ram_start - self.rom_start

    def contains(self, ram_address: int) -> bool:
        return self.ram_start <= ram_address < self.ram_end

    def to_rom(self, ram_address: int) -> int:
        if not self.contains(ram_address):
            raise ValueError(
                f"0x{ram_address:08X} is outside this mapped range "
                f"(0x{self.ram_start:08X}..0x{self.ram_end:08X})"
            )
        return ram_address - self.delta


@dataclass
class RamMap:
    """The verified RAM to ROM mapping for one ROM build.

    Deliberately a list of *ranges* rather than a single delta. An N64 game
    loads several segments to different addresses, and assuming one global
    delta is how a converter starts writing to the wrong place.
    """

    ranges: List[MappedRange] = field(default_factory=list)

    def to_rom(self, ram_address: int) -> Optional[int]:
        """ROM offset for a RAM address, or ``None`` if it is not mapped."""
        for entry in self.ranges:
            if entry.contains(ram_address):
                return entry.to_rom(ram_address)
        return None

    def range_for(self, ram_address: int) -> Optional[MappedRange]:
        for entry in self.ranges:
            if entry.contains(ram_address):
                return entry
        return None

    @classmethod
    def from_definition(cls, definition) -> "RamMap":
        """Read the ``ram_map`` section of a game definition."""
        return cls(
            [
                MappedRange(
                    ram_start=entry.ram_start,
                    ram_end=entry.ram_end,
                    rom_start=entry.rom_start,
                    note=entry.note,
                )
                for entry in (getattr(definition, "ram_map", None) or [])
            ]
        )


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------


#: Why a code could not be turned into a ROM edit.
UNSUPPORTED_TYPE = "unsupported code type"
NOT_A_WRITE = "does not write game memory"
UNMAPPED = "address is not in a verified RAM-to-ROM range"
OUT_OF_ROM = "maps past the end of this ROM"


@dataclass
class ConversionResult:
    """What became of one code."""

    code: GameSharkCode
    rom_offset: Optional[int] = None
    reason: str = ""
    current_bytes: bytes = b""

    @property
    def convertible(self) -> bool:
        return self.rom_offset is not None

    @property
    def changes_anything(self) -> bool:
        return self.convertible and self.current_bytes != self.code.payload

    def describe(self) -> str:
        if self.convertible:
            text = (
                f"0x{self.code.normalised_address:08X} -> ROM 0x{self.rom_offset:06X}"
                f"  {self.current_bytes.hex().upper()} -> {self.code.payload.hex().upper()}"
            )
            return text + ("" if self.changes_anything else "  (already set)")
        return f"0x{self.code.normalised_address:08X}  not converted: {self.reason}"


def convert(
    codes: Iterable[GameSharkCode],
    ram_map: RamMap,
    rom: Optional[ROMManager] = None,
) -> List[ConversionResult]:
    """Work out which codes can become ROM edits, and where."""
    results: List[ConversionResult] = []
    for code in codes:
        if not code.supported:
            results.append(ConversionResult(code, reason=UNSUPPORTED_TYPE))
            continue
        if not code.writes_memory:
            results.append(ConversionResult(code, reason=NOT_A_WRITE))
            continue
        offset = ram_map.to_rom(code.normalised_address)
        if offset is None:
            results.append(ConversionResult(code, reason=UNMAPPED))
            continue
        if rom is not None and offset + code.width > rom.size:
            results.append(ConversionResult(code, reason=OUT_OF_ROM))
            continue
        current = (
            rom.read_bytes(offset, code.width) if rom is not None else b""
        )
        results.append(
            ConversionResult(code, rom_offset=offset, current_bytes=current)
        )
    return results


def apply_to_rom(
    rom: ROMManager,
    results: Sequence[ConversionResult],
    description: str = "Apply GameShark codes",
) -> int:
    """Write every convertible result to the ROM as one undo step.

    Returns the number of codes that actually changed something.
    """
    commands = []
    for result in results:
        if not result.changes_anything:
            continue
        commands.append(
            WriteBytesCommand(
                result.rom_offset,
                result.code.payload,
                result.current_bytes,
                f"GameShark {result.code.format()}",
            )
        )
    if not commands:
        return 0
    rom.apply_command(CompositeCommand(commands, description))
    return len(commands)


def codes_to_text(codes: Iterable[GameSharkCode], with_comments: bool = True) -> str:
    """Render codes back out in the usual ``XXXXXXXX YYYY`` form."""
    lines = []
    for code in codes:
        line = code.format()
        if with_comments and code.comment:
            line += f"  ; {code.comment}"
        lines.append(line)
    return "\n".join(lines)
