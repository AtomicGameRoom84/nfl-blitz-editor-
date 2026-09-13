"""Validation of candidate N64 ROM files.

Validation is deliberately *advisory*: the suite refuses to load something
that clearly is not an N64 image, but merely warns about anything that is
only unusual (odd size, unknown CIC, bad boot checksum).  Modified ROMs
routinely trip the warnings, and a research tool that refused to open them
would be useless.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from core import crc as crc_mod
from core.byte_order import ByteOrder, ByteOrderConverter
from core.rom_header import HEADER_SIZE, ROMHeader

#: Smallest cartridge Nintendo shipped was 4 Mbit = 512 KiB.
MIN_ROM_SIZE = 512 * 1024
#: Largest retail cartridge was 512 Mbit = 64 MiB.
MAX_ROM_SIZE = 64 * 1024 * 1024


class ROMValidationError(Exception):
    """Raised when a file cannot be treated as an N64 ROM at all."""


@dataclass
class ValidationReport:
    """Outcome of validating a ROM image."""

    byte_order: ByteOrder
    header: ROMHeader
    size: int
    detected_cic: Optional[int] = None
    stored_crc: tuple[int, int] = (0, 0)
    calculated_crc: Optional[tuple[int, int]] = None
    warnings: List[str] = field(default_factory=list)

    @property
    def checksum_ok(self) -> Optional[bool]:
        """``True``/``False`` when the checksum could be computed, else ``None``."""
        if self.calculated_crc is None:
            return None
        return self.calculated_crc == self.stored_crc

    @property
    def is_clean(self) -> bool:
        return not self.warnings


class ROMValidator:
    """Checks that a byte buffer looks like an N64 ROM and describes it."""

    @staticmethod
    def sniff_byte_order(data: bytes, filename: str = "") -> ByteOrder:
        """Determine the byte order of ``data``.

        Raises :class:`ROMValidationError` when the header magic matches none
        of the known orders, since every other guess would be unreliable.
        """
        order = ByteOrderConverter.detect(data)
        if order is not None:
            return order
        hint = ByteOrderConverter.detect_from_extension(filename)
        magic = bytes(data[:4]).hex(" ").upper() if len(data) >= 4 else "<empty>"
        raise ROMValidationError(
            "This file does not start with a recognised N64 ROM signature "
            f"(first four bytes: {magic}). Expected one of 80 37 12 40 (.z64), "
            "37 80 40 12 (.v64), 40 12 37 80 (.n64) or 12 40 80 37 (word "
            "swapped)."
            + (f" The .{hint.value} extension suggests it should be {hint.label}."
               if hint else "")
        )

    @classmethod
    def validate(cls, data: bytes, filename: str = "") -> ValidationReport:
        """Validate a raw (on-disk order) buffer and return a report.

        The returned report's header is parsed from the *converted* big
        endian image, so callers should convert with the reported byte order.
        """
        if len(data) < HEADER_SIZE:
            raise ROMValidationError(
                f"File is only {len(data)} bytes; an N64 header alone is "
                f"{HEADER_SIZE} bytes."
            )

        order = cls.sniff_byte_order(data, filename)
        big_endian = ByteOrderConverter.to_big_endian(data, order)
        header = ROMHeader.parse(big_endian)

        report = ValidationReport(
            byte_order=order,
            header=header,
            size=len(big_endian),
            stored_crc=(header.crc1, header.crc2),
        )

        if len(big_endian) < MIN_ROM_SIZE:
            report.warnings.append(
                f"ROM is {len(big_endian)} bytes, smaller than the 512 KiB "
                "minimum for a retail cartridge. It may be truncated."
            )
        if len(big_endian) > MAX_ROM_SIZE:
            report.warnings.append(
                f"ROM is {len(big_endian) // (1024 * 1024)} MiB, larger than "
                "the 64 MiB retail maximum. It may have appended data."
            )
        if len(big_endian) % 4:
            report.warnings.append(
                "ROM length is not a multiple of 4 bytes; byte-order "
                "conversion will leave a partial trailing word."
            )

        report.detected_cic = crc_mod.detect_cic(big_endian)
        if report.detected_cic is None:
            report.warnings.append(
                "Boot code does not match any known CIC chip. The boot "
                "checksum cannot be recalculated automatically."
            )
        else:
            try:
                report.calculated_crc = crc_mod.calculate_checksum(
                    big_endian, report.detected_cic
                )
            except ValueError as exc:  # ROM shorter than the checksummed region
                report.warnings.append(f"Boot checksum not computed: {exc}")
            else:
                if report.calculated_crc != report.stored_crc:
                    report.warnings.append(
                        "Stored boot checksum does not match the ROM contents. "
                        "This is expected for an already-modified ROM."
                    )

        if header.media_format != 0x4E:
            report.warnings.append(
                f"Media format byte is {header.media!r}, not a plain cartridge."
            )
        if header.region_code not in (0x45, 0x50, 0x4A, 0x41):
            report.warnings.append(
                f"Unusual region code 0x{header.region_code:02X} ({header.region})."
            )

        return report
