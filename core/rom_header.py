"""Parsing of the 64-byte N64 cartridge header.

Layout (all multi-byte fields big endian, offsets relative to ROM start)::

    0x00  1   PI BSD DOM1 latency  (0x80 on retail carts)
    0x01  3   PI BSD DOM1 pulse / page size / release
    0x04  4   clock rate override (0 = default)
    0x08  4   boot address (entry point)
    0x0C  4   libultra release
    0x10  4   CRC1  (boot checksum, see core.crc)
    0x14  4   CRC2
    0x18  8   reserved
    0x20  20  internal image name, space padded ASCII
    0x34  7   reserved
    0x3B  1   media format ('N' cartridge, 'D' 64DD disk, ...)
    0x3C  2   cartridge ID
    0x3E  1   region / country code
    0x3F  1   revision
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

HEADER_SIZE = 0x40

#: Country code byte -> human readable region.
REGION_CODES = {
    0x00: "Demo",
    0x37: "Beta",
    0x41: "Asia (NTSC)",
    0x42: "Brazil",
    0x43: "China",
    0x44: "Germany",
    0x45: "USA",
    0x46: "France",
    0x47: "Gateway 64 (NTSC)",
    0x48: "Netherlands",
    0x49: "Italy",
    0x4A: "Japan",
    0x4B: "Korea",
    0x4C: "Gateway 64 (PAL)",
    0x4E: "Canada",
    0x50: "Europe",
    0x53: "Spain",
    0x55: "Australia",
    0x57: "Scandinavia",
    0x58: "Europe (alt)",
    0x59: "Europe (alt)",
}

#: Media format byte -> description.
MEDIA_FORMATS = {
    0x4E: "Cartridge",
    0x44: "64DD Disk",
    0x43: "Cartridge + Expansion",
    0x45: "64DD Expansion",
    0x5A: "Aleck64 Cartridge",
}


@dataclass(frozen=True)
class ROMHeader:
    """Decoded N64 header fields.

    Always constructed from a big endian (.z64) image; see
    :class:`core.byte_order.ByteOrderConverter`.
    """

    pi_config: int
    clock_rate: int
    boot_address: int
    libultra_release: int
    crc1: int
    crc2: int
    image_name: str
    media_format: int
    cartridge_id: str
    region_code: int
    revision: int

    @classmethod
    def parse(cls, data: bytes) -> "ROMHeader":
        if len(data) < HEADER_SIZE:
            raise ValueError(
                f"need at least {HEADER_SIZE} bytes to parse an N64 header, "
                f"got {len(data)}"
            )
        raw_name = bytes(data[0x20:0x34])
        # Names are space padded ASCII but a handful of ROMs pad with NULs or
        # contain stray high bytes, so decode defensively.
        name = raw_name.decode("ascii", errors="replace").replace("\x00", " ").strip()
        cart_id = bytes(data[0x3C:0x3E]).decode("ascii", errors="replace")
        return cls(
            pi_config=int.from_bytes(data[0x00:0x04], "big"),
            clock_rate=int.from_bytes(data[0x04:0x08], "big"),
            boot_address=int.from_bytes(data[0x08:0x0C], "big"),
            libultra_release=int.from_bytes(data[0x0C:0x10], "big"),
            crc1=int.from_bytes(data[0x10:0x14], "big"),
            crc2=int.from_bytes(data[0x14:0x18], "big"),
            image_name=name,
            media_format=data[0x3B],
            cartridge_id=cart_id,
            region_code=data[0x3E],
            revision=data[0x3F],
        )

    # -- convenience views -------------------------------------------------

    @property
    def region(self) -> str:
        return REGION_CODES.get(self.region_code, f"Unknown (0x{self.region_code:02X})")

    @property
    def region_letter(self) -> str:
        if 0x20 <= self.region_code < 0x7F:
            return chr(self.region_code)
        return "?"

    @property
    def media(self) -> str:
        return MEDIA_FORMATS.get(self.media_format, f"Unknown (0x{self.media_format:02X})")

    @property
    def game_code(self) -> str:
        """The four character product code, e.g. ``NSME``."""
        media = chr(self.media_format) if 0x20 <= self.media_format < 0x7F else "?"
        return f"{media}{self.cartridge_id}{self.region_letter}"

    @property
    def version_string(self) -> str:
        return f"1.{self.revision}"

    def to_dict(self) -> dict:
        return {
            "image_name": self.image_name,
            "game_code": self.game_code,
            "cartridge_id": self.cartridge_id,
            "media": self.media,
            "region": self.region,
            "region_code": self.region_code,
            "revision": self.revision,
            "crc1": f"0x{self.crc1:08X}",
            "crc2": f"0x{self.crc2:08X}",
            "boot_address": f"0x{self.boot_address:08X}",
            "clock_rate": f"0x{self.clock_rate:08X}",
            "libultra_release": f"0x{self.libultra_release:08X}",
        }


def guess_region_from_code(code: int) -> Optional[str]:
    return REGION_CODES.get(code)
