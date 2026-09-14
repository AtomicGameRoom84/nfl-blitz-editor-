"""A structural survey of a ROM.

The scanner makes no claims about what any particular region *is*.  It
reports measurable facts -- where the printable text clusters, where the
large runs of identical filler are, how the data is distributed -- because
those are the places worth looking first when nothing about a ROM is known
yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from core import crc as crc_mod
from core.rom_header import ROMHeader


@dataclass
class Cluster:
    """A run of interesting bytes."""

    start: int
    end: int
    detail: str = ""

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass
class ScanReport:
    """What the scanner found."""

    size: int
    header: Optional[ROMHeader] = None
    cic: Optional[int] = None
    stored_crc: Tuple[int, int] = (0, 0)
    calculated_crc: Optional[Tuple[int, int]] = None
    text_clusters: List[Cluster] = field(default_factory=list)
    filler_regions: List[Cluster] = field(default_factory=list)
    total_strings: int = 0
    printable_bytes: int = 0
    zero_bytes: int = 0

    @property
    def checksum_ok(self) -> Optional[bool]:
        if self.calculated_crc is None:
            return None
        return self.calculated_crc == self.stored_crc

    def lines(self) -> List[str]:
        """Human readable report, one fact per line."""
        out = [f"ROM size: {self.size:,} bytes ({self.size / 1024 / 1024:.2f} MiB)"]
        if self.header is not None:
            out += [
                f"Internal name: {self.header.image_name!r}",
                f"Game code: {self.header.game_code}   revision {self.header.revision}",
                f"Region: {self.header.region}",
                f"Media: {self.header.media}",
            ]
        out.append(
            f"CIC chip: {self.cic if self.cic else 'not recognised'}"
        )
        out.append(
            f"Boot checksum: stored {self.stored_crc[0]:08X}/{self.stored_crc[1]:08X}"
            + (
                "  — cannot verify"
                if self.calculated_crc is None
                else ("  — matches" if self.checksum_ok else
                      f"  — contents give {self.calculated_crc[0]:08X}/{self.calculated_crc[1]:08X}")
            )
        )
        out.append("")
        out.append(
            f"Printable ASCII: {self.printable_bytes:,} bytes "
            f"({self.printable_bytes / max(1, self.size):.1%} of the ROM), "
            f"in {self.total_strings:,} runs of 4+ characters"
        )
        out.append(
            f"Zero bytes: {self.zero_bytes:,} "
            f"({self.zero_bytes / max(1, self.size):.1%})"
        )
        out.append("")
        out.append("Densest text regions (likely name or menu tables):")
        if self.text_clusters:
            for cluster in self.text_clusters:
                out.append(
                    f"  0x{cluster.start:08X}–0x{cluster.end:08X}  "
                    f"{cluster.length:,} bytes   {cluster.detail}"
                )
        else:
            out.append("  (none found)")
        out.append("")
        out.append("Largest filler runs (unused space, or padding between assets):")
        if self.filler_regions:
            for cluster in self.filler_regions:
                out.append(
                    f"  0x{cluster.start:08X}–0x{cluster.end:08X}  "
                    f"{cluster.length:,} bytes   {cluster.detail}"
                )
        else:
            out.append("  (none found)")
        out.append("")
        out.append(
            "Nothing above identifies game data. It points at places worth "
            "opening in the Hex/Data Explorer."
        )
        return out


class ROMScanner:
    """Produces a :class:`ScanReport` for a ROM buffer."""

    def __init__(
        self,
        minimum_string: int = 4,
        cluster_gap: int = 256,
        top_clusters: int = 12,
        minimum_filler: int = 4096,
    ) -> None:
        self.minimum_string = minimum_string
        self.cluster_gap = cluster_gap
        self.top_clusters = top_clusters
        self.minimum_filler = minimum_filler

    def scan(self, data: bytes) -> ScanReport:
        import re

        data = bytes(data)
        report = ScanReport(size=len(data))
        if len(data) >= 0x40:
            report.header = ROMHeader.parse(data)
            report.stored_crc = (report.header.crc1, report.header.crc2)
        report.cic = crc_mod.detect_cic(data)
        try:
            report.calculated_crc = crc_mod.calculate_checksum(data, report.cic)
        except ValueError:
            report.calculated_crc = None

        array = np.frombuffer(data, dtype=np.uint8)
        printable = (array >= 0x20) & (array < 0x7F)
        report.printable_bytes = int(printable.sum())
        report.zero_bytes = int((array == 0).sum())

        # Text clusters: group nearby printable runs so a name table reads as
        # one finding instead of two hundred.
        pattern = re.compile(rb"[\x20-\x7E]{%d,}" % self.minimum_string)
        spans: List[Tuple[int, int]] = []
        for match in pattern.finditer(data):
            spans.append((match.start(), match.end()))
        report.total_strings = len(spans)

        clusters: List[Cluster] = []
        for start, end in spans:
            if clusters and start - clusters[-1].end <= self.cluster_gap:
                clusters[-1] = Cluster(clusters[-1].start, end)
            else:
                clusters.append(Cluster(start, end))
        for cluster in clusters:
            chunk = data[cluster.start : cluster.end]
            sample = "".join(
                chr(b) if 0x20 <= b < 0x7F else " " for b in chunk[:48]
            ).strip()
            cluster.detail = f'e.g. "{sample}"'
        clusters.sort(key=lambda c: c.length, reverse=True)
        report.text_clusters = clusters[: self.top_clusters]

        report.filler_regions = self._filler_runs(array)[: self.top_clusters]
        return report

    def _filler_runs(self, array: np.ndarray) -> List[Cluster]:
        """Long runs of a single repeated byte."""
        if array.size == 0:
            return []
        changes = np.flatnonzero(array[1:] != array[:-1]) + 1
        starts = np.concatenate(([0], changes))
        ends = np.concatenate((changes, [array.size]))
        lengths = ends - starts
        keep = np.flatnonzero(lengths >= self.minimum_filler)
        runs = [
            Cluster(
                int(starts[i]),
                int(ends[i]),
                f"byte 0x{int(array[starts[i]]):02X} repeated",
            )
            for i in keep
        ]
        runs.sort(key=lambda c: c.length, reverse=True)
        return runs
