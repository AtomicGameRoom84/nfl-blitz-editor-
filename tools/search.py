"""Searching a ROM for values, byte patterns and text.

The point of this module is finding *candidates*.  A ROM is megabytes of
data and a value like 100 occurs thousands of times, so the useful workflow
is iterative:

1. Search the whole ROM for a value you believe exists (``search_value``).
2. Change something in game, dump again, and narrow the candidate list with
   :meth:`ValueSearcher.refine` -- exactly the "next scan" idea from memory
   editors, applied to ROM files.
3. Bookmark what survives.

All searches operate on the big endian working image.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from core.datatypes import DataType, Endian

#: Safety valve so a pathological search cannot exhaust memory.
DEFAULT_RESULT_LIMIT = 100_000


@dataclass(frozen=True)
class SearchHit:
    """One match."""

    address: int
    value: Any
    raw: bytes
    data_type: Optional[DataType] = None
    endian: Endian = Endian.BIG

    @property
    def address_hex(self) -> str:
        return f"0x{self.address:08X}"

    @property
    def hex(self) -> str:
        return self.raw.hex(" ").upper()

    @property
    def type_label(self) -> str:
        if self.data_type is None:
            return "bytes"
        if self.data_type.size == 1:
            return self.data_type.value
        return f"{self.data_type.value} {self.endian.short}"


@dataclass
class SearchResult:
    """A completed search."""

    hits: List[SearchHit]
    description: str
    truncated: bool = False
    scanned_bytes: int = 0

    def __len__(self) -> int:
        return len(self.hits)

    def addresses(self) -> List[int]:
        return [hit.address for hit in self.hits]

    def summary(self) -> str:
        text = f"{len(self.hits)} match(es) for {self.description}"
        if self.truncated:
            text += " (list truncated)"
        return text


#: numpy dtype string for each integer type and endianness.
_NUMPY_DTYPES = {
    (DataType.U8, Endian.BIG): "u1", (DataType.U8, Endian.LITTLE): "u1",
    (DataType.S8, Endian.BIG): "i1", (DataType.S8, Endian.LITTLE): "i1",
    (DataType.U16, Endian.BIG): ">u2", (DataType.U16, Endian.LITTLE): "<u2",
    (DataType.S16, Endian.BIG): ">i2", (DataType.S16, Endian.LITTLE): "<i2",
    (DataType.U32, Endian.BIG): ">u4", (DataType.U32, Endian.LITTLE): "<u4",
    (DataType.S32, Endian.BIG): ">i4", (DataType.S32, Endian.LITTLE): "<i4",
    (DataType.U64, Endian.BIG): ">u8", (DataType.U64, Endian.LITTLE): "<u8",
    (DataType.S64, Endian.BIG): ">i8", (DataType.S64, Endian.LITTLE): "<i8",
    (DataType.F32, Endian.BIG): ">f4", (DataType.F32, Endian.LITTLE): "<f4",
    (DataType.F64, Endian.BIG): ">f8", (DataType.F64, Endian.LITTLE): "<f8",
}


class ValueSearcher:
    """Runs searches over a ROM buffer."""

    def __init__(self, data: bytes | bytearray, limit: int = DEFAULT_RESULT_LIMIT) -> None:
        self.data = bytes(data)
        self.limit = limit

    # -- helpers -----------------------------------------------------------

    def _window(self, start: int, end: Optional[int]) -> Tuple[int, int]:
        start = max(0, start)
        end = len(self.data) if end is None else min(end, len(self.data))
        if start > end:
            raise ValueError(f"search range start 0x{start:X} is past end 0x{end:X}")
        return start, end

    # -- byte pattern ------------------------------------------------------

    def search_bytes(
        self,
        pattern: bytes,
        start: int = 0,
        end: Optional[int] = None,
        alignment: int = 1,
    ) -> SearchResult:
        """Find every occurrence of an exact byte sequence."""
        if not pattern:
            raise ValueError("search pattern is empty")
        start, end = self._window(start, end)
        hits: List[SearchHit] = []
        position = start
        truncated = False
        while True:
            found = self.data.find(pattern, position, end)
            if found < 0:
                break
            if alignment <= 1 or found % alignment == 0:
                hits.append(SearchHit(address=found, value=pattern, raw=pattern))
                if len(hits) >= self.limit:
                    truncated = True
                    break
            position = found + 1
        return SearchResult(
            hits=hits,
            description=f"byte pattern {pattern.hex(' ').upper()}",
            truncated=truncated,
            scanned_bytes=end - start,
        )

    def search_masked_bytes(
        self,
        pattern: bytes,
        mask: Sequence[bool],
        start: int = 0,
        end: Optional[int] = None,
    ) -> SearchResult:
        """Find a byte sequence with wildcards.

        ``mask[i]`` is ``True`` where ``pattern[i]`` must match and ``False``
        where any byte is acceptable -- the ``DE ?? BE EF`` style of search
        used when only part of a structure is known.
        """
        if len(pattern) != len(mask):
            raise ValueError("pattern and mask must be the same length")
        if not any(mask):
            raise ValueError("mask must require at least one byte to match")
        start, end = self._window(start, end)
        anchor = next(i for i, required in enumerate(mask) if required)
        anchor_byte = pattern[anchor : anchor + 1]

        hits: List[SearchHit] = []
        truncated = False
        position = start
        while True:
            found = self.data.find(anchor_byte, position, end)
            if found < 0:
                break
            candidate = found - anchor
            position = found + 1
            if candidate < start or candidate + len(pattern) > end:
                continue
            chunk = self.data[candidate : candidate + len(pattern)]
            if all(
                (not required) or chunk[i] == pattern[i]
                for i, required in enumerate(mask)
            ):
                hits.append(SearchHit(address=candidate, value=chunk, raw=chunk))
                if len(hits) >= self.limit:
                    truncated = True
                    break
        rendered = " ".join(
            f"{pattern[i]:02X}" if required else "??"
            for i, required in enumerate(mask)
        )
        return SearchResult(
            hits=hits,
            description=f"masked pattern {rendered}",
            truncated=truncated,
            scanned_bytes=end - start,
        )

    # -- text --------------------------------------------------------------

    def search_text(
        self,
        text: str,
        encoding: str = "ascii",
        case_sensitive: bool = True,
        start: int = 0,
        end: Optional[int] = None,
    ) -> SearchResult:
        """Find a string.

        Case-insensitive search only makes sense for single-byte encodings
        and is implemented by trying both cases of each letter, which is
        cheap for the short strings people actually search for.
        """
        if not text:
            raise ValueError("search text is empty")
        if case_sensitive:
            result = self.search_bytes(text.encode(encoding), start, end)
            return SearchResult(
                hits=[
                    SearchHit(h.address, text, h.raw) for h in result.hits
                ],
                description=f"text {text!r}",
                truncated=result.truncated,
                scanned_bytes=result.scanned_bytes,
            )

        start, end = self._window(start, end)
        pattern = re.compile(
            re.escape(text).encode(encoding), re.IGNORECASE
        )
        hits: List[SearchHit] = []
        truncated = False
        for match in pattern.finditer(self.data, start, end):
            hits.append(
                SearchHit(
                    address=match.start(),
                    value=match.group().decode(encoding, errors="replace"),
                    raw=match.group(),
                )
            )
            if len(hits) >= self.limit:
                truncated = True
                break
        return SearchResult(
            hits=hits,
            description=f"text {text!r} (case insensitive)",
            truncated=truncated,
            scanned_bytes=end - start,
        )

    def find_strings(
        self,
        minimum_length: int = 4,
        start: int = 0,
        end: Optional[int] = None,
    ) -> SearchResult:
        """List printable ASCII runs -- a quick way to locate name tables."""
        start, end = self._window(start, end)
        pattern = re.compile(rb"[\x20-\x7E]{%d,}" % max(1, minimum_length))
        hits: List[SearchHit] = []
        truncated = False
        for match in pattern.finditer(self.data, start, end):
            raw = match.group()
            hits.append(
                SearchHit(
                    address=match.start(),
                    value=raw.decode("ascii"),
                    raw=raw,
                )
            )
            if len(hits) >= self.limit:
                truncated = True
                break
        return SearchResult(
            hits=hits,
            description=f"printable strings of {minimum_length}+ characters",
            truncated=truncated,
            scanned_bytes=end - start,
        )

    # -- typed values ------------------------------------------------------

    def search_value(
        self,
        value: float,
        data_type: DataType,
        endian: Endian = Endian.BIG,
        start: int = 0,
        end: Optional[int] = None,
        alignment: Optional[int] = None,
        tolerance: float = 0.0,
    ) -> SearchResult:
        """Find a single value of a given type.

        ``alignment`` defaults to the type's own size, which is where a
        compiler would have placed it.  Drop it to 1 when hunting for values
        packed inside a structure.
        """
        return self.search_range(
            value - tolerance if data_type.is_float else value,
            value + tolerance if data_type.is_float else value,
            data_type,
            endian,
            start,
            end,
            alignment,
            description=f"{data_type.value} == {value}",
        )

    def search_range(
        self,
        low: float,
        high: float,
        data_type: DataType,
        endian: Endian = Endian.BIG,
        start: int = 0,
        end: Optional[int] = None,
        alignment: Optional[int] = None,
        description: str = "",
    ) -> SearchResult:
        """Find every value of ``data_type`` between ``low`` and ``high``."""
        if low > high:
            low, high = high, low
        size = data_type.size
        alignment = size if alignment is None else max(1, alignment)
        start, end = self._window(start, end)
        dtype = np.dtype(_NUMPY_DTYPES[(data_type, endian)])

        addresses: List[int] = []
        truncated = False
        # One pass per alignment phase: with the default alignment that is a
        # single pass; with alignment 1 it is `size` passes, which is still
        # far quicker than a Python loop over every offset.
        for phase in range(0, size, alignment) if alignment < size else (0,):
            base = start + phase
            if alignment >= size:
                base = start + ((-start) % alignment)
            count = (end - base) // size
            if count <= 0:
                continue
            view = np.frombuffer(self.data, dtype=dtype, count=count, offset=base)
            if data_type.is_float:
                with np.errstate(invalid="ignore"):
                    mask = (view >= low) & (view <= high)
            else:
                mask = (view >= low) & (view <= high)
            found = np.flatnonzero(mask)
            if found.size:
                addresses.extend((base + found * size).tolist())
            if len(addresses) >= self.limit:
                truncated = True
                break

        addresses.sort()
        if len(addresses) > self.limit:
            addresses = addresses[: self.limit]
            truncated = True

        hits = [
            SearchHit(
                address=address,
                value=data_type.decode(self.data[address : address + size], endian),
                raw=self.data[address : address + size],
                data_type=data_type,
                endian=endian,
            )
            for address in addresses
        ]
        if not description:
            description = f"{data_type.value} in [{low}, {high}]"
        return SearchResult(
            hits=hits,
            description=description,
            truncated=truncated,
            scanned_bytes=end - start,
        )

    # -- refinement --------------------------------------------------------

    def refine(
        self,
        previous: SearchResult,
        predicate: Callable[[Any], bool],
        description: str = "narrowed",
    ) -> SearchResult:
        """Re-test previous hits against the current buffer.

        Give this the results of a search on ROM A and a searcher over ROM B
        to keep only the addresses whose value changed the way you expected.
        """
        hits: List[SearchHit] = []
        for hit in previous.hits:
            data_type = hit.data_type
            if data_type is None:
                continue
            size = data_type.size
            if hit.address + size > len(self.data):
                continue
            raw = self.data[hit.address : hit.address + size]
            value = data_type.decode(raw, hit.endian)
            if predicate(value):
                hits.append(
                    SearchHit(hit.address, value, raw, data_type, hit.endian)
                )
        return SearchResult(
            hits=hits,
            description=f"{previous.description} -> {description}",
            scanned_bytes=len(previous.hits),
        )

    def values_at(
        self,
        addresses: Iterable[int],
        data_type: DataType,
        endian: Endian = Endian.BIG,
    ) -> List[SearchHit]:
        """Read the same typed value at a list of addresses."""
        size = data_type.size
        hits = []
        for address in addresses:
            if address + size > len(self.data):
                continue
            raw = self.data[address : address + size]
            hits.append(
                SearchHit(address, data_type.decode(raw, endian), raw, data_type, endian)
            )
        return hits
