"""Binary comparison between two ROM images.

This is the backbone of the discovery workflow.  The intended loop is:

1. Dump a ROM, play it, change one thing in an emulator/editor, dump again.
2. Compare the two files here.
3. Every differing region is a candidate address for whatever you changed.
4. Promote the interesting ones to bookmarks, then to game-definition
   entries.

Because a single logical value (say a 16-bit speed constant) shows up as
one to four differing bytes, regions separated by only a few unchanged bytes
are merged so they read as one finding.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from core.byte_order import ByteOrder, ByteOrderConverter
from core.datatypes import DataType, Endian
from core.rom_header import ROMHeader

#: Unchanged bytes allowed inside one reported region.
DEFAULT_MERGE_GAP = 16


def _as_array(buffer: bytes | bytearray | memoryview) -> np.ndarray:
    return np.frombuffer(bytes(buffer), dtype=np.uint8)


def diff_buffers(
    left: bytes | bytearray,
    right: bytes | bytearray,
    merge_gap: int = DEFAULT_MERGE_GAP,
) -> List[Tuple[int, int]]:
    """Return ``(start, end)`` half-open ranges where the buffers differ.

    Ranges separated by ``merge_gap`` or fewer identical bytes are merged.
    When the buffers have different lengths the trailing surplus is reported
    as one final range.
    """
    if merge_gap < 0:
        raise ValueError("merge_gap must not be negative")

    common = min(len(left), len(right))
    ranges: List[Tuple[int, int]] = []

    if common:
        unequal = _as_array(left[:common]) != _as_array(right[:common])
        indices = np.flatnonzero(unequal)
        if indices.size:
            # Split wherever more than merge_gap identical bytes separate
            # two differing bytes.
            splits = np.flatnonzero(np.diff(indices) > merge_gap + 1)
            starts = np.concatenate(([indices[0]], indices[splits + 1]))
            ends = np.concatenate((indices[splits], [indices[-1]])) + 1
            ranges = [(int(s), int(e)) for s, e in zip(starts, ends)]

    if len(left) != len(right):
        tail = (common, max(len(left), len(right)))
        if ranges and tail[0] - ranges[-1][1] <= merge_gap:
            ranges[-1] = (ranges[-1][0], tail[1])
        else:
            ranges.append(tail)

    return ranges


@dataclass
class DiffRegion:
    """One contiguous difference between two ROMs."""

    offset: int
    length: int
    left_bytes: bytes
    right_bytes: bytes
    #: Filled in by :meth:`ROMComparator.group_by_region`.
    region: str = "Unclassified"

    @property
    def end(self) -> int:
        return self.offset + self.length

    def interpretations(self) -> List[dict]:
        """Plausible typed readings of this region, for the results table.

        A region of 1, 2 or 4 bytes is very likely a single scalar, so its
        before/after values are decoded for every type that fits.  Larger
        regions are more likely text or a table and are left to the hex view.
        """
        results: List[dict] = []
        if self.length > 8:
            return results
        for data_type in (
            DataType.U8, DataType.S8,
            DataType.U16, DataType.S16,
            DataType.U32, DataType.S32,
            DataType.F32,
        ):
            if data_type.size != self.length:
                continue
            for endian in (Endian.BIG, Endian.LITTLE):
                try:
                    before = data_type.decode(self.left_bytes, endian)
                    after = data_type.decode(self.right_bytes, endian)
                except ValueError:
                    continue
                results.append(
                    {
                        "type": data_type.value,
                        "endian": endian.value,
                        "before": before,
                        "after": after,
                        "delta": (after - before) if not isinstance(before, str) else None,
                    }
                )
                if endian is Endian.BIG and data_type.size == 1:
                    break  # endianness is meaningless for a single byte
        return results

    def ascii_preview(self) -> Tuple[str, str]:
        """Printable rendering of both sides, for spotting text changes."""

        def render(raw: bytes) -> str:
            return "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in raw[:64])

        return render(self.left_bytes), render(self.right_bytes)

    def to_dict(self) -> dict:
        return {
            "offset": self.offset,
            "offset_hex": f"0x{self.offset:08X}",
            "length": self.length,
            "region": self.region,
            "before_hex": self.left_bytes[:64].hex(" ").upper(),
            "after_hex": self.right_bytes[:64].hex(" ").upper(),
        }


@dataclass
class ComparisonResult:
    """Everything the UI needs to present one comparison."""

    left_name: str
    right_name: str
    left_size: int
    right_size: int
    regions: List[DiffRegion] = field(default_factory=list)
    left_header: Optional[ROMHeader] = None
    right_header: Optional[ROMHeader] = None
    truncated: bool = False

    @property
    def changed_bytes(self) -> int:
        return sum(r.length for r in self.regions)

    @property
    def identical(self) -> bool:
        return not self.regions and self.left_size == self.right_size

    def summary(self) -> str:
        if self.identical:
            return "The two ROMs are byte-for-byte identical."
        parts = [
            f"{len(self.regions)} differing region(s)",
            f"{self.changed_bytes} byte(s) changed",
        ]
        if self.left_size != self.right_size:
            parts.append(
                f"sizes differ ({self.left_size} vs {self.right_size} bytes)"
            )
        if self.truncated:
            parts.append("results truncated")
        return ", ".join(parts)

    # -- export ------------------------------------------------------------

    def to_csv(self, path: str | Path) -> Path:
        path = Path(path)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                ["Address", "Offset", "Length", "Region", "Before", "After"]
            )
            for region in self.regions:
                writer.writerow(
                    [
                        f"0x{region.offset:08X}",
                        region.offset,
                        region.length,
                        region.region,
                        region.left_bytes[:64].hex(" ").upper(),
                        region.right_bytes[:64].hex(" ").upper(),
                    ]
                )
        return path

    def to_json(self, path: str | Path) -> Path:
        path = Path(path)
        payload = {
            "left": {"name": self.left_name, "size": self.left_size},
            "right": {"name": self.right_name, "size": self.right_size},
            "summary": self.summary(),
            "regions": [r.to_dict() for r in self.regions],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path


class ROMComparator:
    """Compares two ROM images and classifies the differences."""

    #: Rough structural map of an N64 image, used to label findings.  These
    #: boundaries are true for every N64 ROM; anything past the boot code is
    #: game specific and is labelled generically.
    STRUCTURAL_REGIONS: Sequence[Tuple[int, int, str]] = (
        (0x000000, 0x000040, "ROM header"),
        (0x000040, 0x001000, "Boot code (CIC)"),
    )

    def __init__(self, merge_gap: int = DEFAULT_MERGE_GAP, max_regions: int = 50_000):
        self.merge_gap = merge_gap
        self.max_regions = max_regions

    # -- loading -----------------------------------------------------------

    @staticmethod
    def load_normalised(path: str | Path) -> Tuple[bytes, Optional[ROMHeader]]:
        """Read a ROM and convert it to big endian so orders can be mixed.

        Comparing a ``.v64`` against a ``.z64`` byte-for-byte would report
        every word as different; normalising first makes the comparison
        meaningful.
        """
        path = Path(path)
        raw = path.read_bytes()
        order = ByteOrderConverter.detect(raw) or ByteOrder.Z64
        data = bytes(ByteOrderConverter.to_big_endian(raw, order))
        header = ROMHeader.parse(data) if len(data) >= 0x40 else None
        return data, header

    # -- comparison --------------------------------------------------------

    def compare_files(self, left_path: str | Path, right_path: str | Path) -> ComparisonResult:
        left, left_header = self.load_normalised(left_path)
        right, right_header = self.load_normalised(right_path)
        result = self.compare_buffers(
            left, right, Path(left_path).name, Path(right_path).name
        )
        result.left_header = left_header
        result.right_header = right_header
        return result

    def compare_buffers(
        self,
        left: bytes,
        right: bytes,
        left_name: str = "Original",
        right_name: str = "Modified",
    ) -> ComparisonResult:
        ranges = diff_buffers(left, right, self.merge_gap)
        truncated = len(ranges) > self.max_regions
        if truncated:
            ranges = ranges[: self.max_regions]

        regions = [
            DiffRegion(
                offset=start,
                length=end - start,
                left_bytes=bytes(left[start:end]),
                right_bytes=bytes(right[start:end]),
            )
            for start, end in ranges
        ]
        self.classify(regions)
        return ComparisonResult(
            left_name=left_name,
            right_name=right_name,
            left_size=len(left),
            right_size=len(right),
            regions=regions,
            truncated=truncated,
        )

    # -- classification ----------------------------------------------------

    def classify(self, regions: Iterable[DiffRegion]) -> None:
        """Tag each region with a structural label, in place."""
        for region in regions:
            region.region = self.region_name(region.offset)

    def region_name(self, offset: int) -> str:
        for start, end, name in self.STRUCTURAL_REGIONS:
            if start <= offset < end:
                return name
        # Beyond the boot code everything is game data; bucket by megabyte so
        # findings cluster usefully in the results list.
        return f"Game data (0x{offset & ~0xFFFFF:06X}-0x{(offset & ~0xFFFFF) + 0xFFFFF:06X})"

    @staticmethod
    def group_by_region(result: ComparisonResult) -> Dict[str, List[DiffRegion]]:
        """Bucket regions by their label, preserving address order."""
        grouped: Dict[str, List[DiffRegion]] = {}
        for region in result.regions:
            grouped.setdefault(region.region, []).append(region)
        return grouped
