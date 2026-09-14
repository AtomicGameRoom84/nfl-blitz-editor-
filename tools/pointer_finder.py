"""Find 32-bit words that could be references to an address.

Once a table is located, the next question is what points at it -- that is
how the code that uses the data gets found, and how neighbouring tables get
discovered.

N64 games address data in several ways, so this checks all of them:

* the raw ROM offset,
* a KSEG0 virtual address (``0x80000000 | offset``), which is what a ROM
  loaded to the start of RDRAM looks like,
* and the same two shifted by a user-supplied load base, for data the game
  DMAs to an arbitrary RAM address.

Everything it returns is a *candidate*. A 32-bit value equal to an address
is not proof of a reference, and the tool does not claim otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from core.datatypes import DataType, Endian
from tools.search import ValueSearcher

#: Physical RAM mapped through KSEG0 (cached, unmapped).
KSEG0_BASE = 0x80000000


@dataclass(frozen=True)
class PointerHit:
    """A 32-bit word that matches one of the candidate encodings."""

    address: int
    value: int
    interpretation: str

    @property
    def address_hex(self) -> str:
        return f"0x{self.address:08X}"

    @property
    def value_hex(self) -> str:
        return f"0x{self.value:08X}"


class PointerFinder:
    """Searches a ROM for words that look like references to a target."""

    def __init__(self, data: bytes, limit: int = 20_000) -> None:
        self.searcher = ValueSearcher(data, limit=limit)

    def candidates_for(
        self,
        target: int,
        load_base: Optional[int] = None,
        alignment: int = 4,
        endian: Endian = Endian.BIG,
    ) -> List[PointerHit]:
        """Every word equal to one of the plausible encodings of ``target``."""
        encodings = [
            (target, "raw ROM offset"),
            ((KSEG0_BASE | target) & 0xFFFFFFFF, "KSEG0 virtual address (0x80000000 | offset)"),
        ]
        if load_base is not None:
            encodings.append(
                ((load_base + target) & 0xFFFFFFFF, f"offset from load base 0x{load_base:08X}")
            )
            encodings.append(
                ((KSEG0_BASE | (load_base + target)) & 0xFFFFFFFF,
                 f"KSEG0 address of load base 0x{load_base:08X} + offset")
            )

        hits: List[PointerHit] = []
        seen = set()
        for value, description in encodings:
            if value in seen:
                continue
            seen.add(value)
            result = self.searcher.search_value(
                value, DataType.U32, endian, alignment=alignment
            )
            for hit in result.hits:
                hits.append(PointerHit(hit.address, value, description))
        hits.sort(key=lambda h: h.address)
        return hits
