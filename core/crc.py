"""N64 boot checksum (CRC1/CRC2) calculation and CIC chip detection.

The two 32-bit values at header offsets ``0x10`` and ``0x14`` are not a plain
CRC of the file.  They are produced by the boot code with an algorithm that
depends on which CIC lockout chip the cartridge used, over the first megabyte
of the ROM starting at ``0x1000``.

Emulators generally do not verify these values, but real hardware and some
flash carts do, so the suite can recalculate them when saving a modified ROM.

The algorithm is the long-standing public implementation (``n64crc.c`` by
Parasyte), reimplemented here in Python.
"""

from __future__ import annotations

import zlib
from typing import Optional, Tuple

#: The checksum is computed over ROM[0x1000 : 0x1000 + 0x100000].
CHECKSUM_START = 0x1000
CHECKSUM_LENGTH = 0x100000
HEADER_SIZE = 0x40

#: Seed value per CIC family.
_SEEDS = {
    6101: 0xF8CA4DDC,
    6102: 0xF8CA4DDC,
    6103: 0xA3886759,
    6105: 0xDF26F436,
    6106: 0x1FEA617A,
    7102: 0xF8CA4DDC,
}

#: CRC32 of the 4032-byte boot code (ROM[0x40:0x1000]) for each known CIC.
_BOOTCODE_CRC32 = {
    0x6170A4A1: 6101,
    0x90BB6CB5: 6102,
    0x0B050EE0: 6103,
    0x98BC2C86: 6105,
    0xACC8580A: 6106,
    0x009E9EA3: 7102,
}

_MASK = 0xFFFFFFFF


def _rol(value: int, bits: int) -> int:
    bits &= 0x1F
    if bits == 0:
        return value & _MASK
    return ((value << bits) | (value >> (32 - bits))) & _MASK


def _u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "big")


def detect_cic(data: bytes) -> Optional[int]:
    """Identify the CIC chip from the ROM's boot code.

    ``data`` must be in big endian (.z64) order.  Returns the CIC number
    (e.g. ``6102``) or ``None`` when the boot code is not one of the known
    retail variants -- which is normal for homebrew and heavily modified ROMs.
    """
    if len(data) < CHECKSUM_START:
        return None
    crc = zlib.crc32(bytes(data[HEADER_SIZE:CHECKSUM_START])) & _MASK
    return _BOOTCODE_CRC32.get(crc)


def calculate_checksum(data: bytes, cic: Optional[int] = None) -> Tuple[int, int]:
    """Return the ``(crc1, crc2)`` pair the boot code expects for ``data``.

    Parameters
    ----------
    data:
        Whole ROM image in big endian order.
    cic:
        CIC number to assume.  When omitted it is detected from the boot code
        and falls back to 6102, by far the most common chip.

    Raises
    ------
    ValueError
        If the ROM is shorter than the region the checksum covers.
    """
    if len(data) < CHECKSUM_START + CHECKSUM_LENGTH:
        raise ValueError(
            "ROM is too small to checksum: needs at least "
            f"{CHECKSUM_START + CHECKSUM_LENGTH} bytes, got {len(data)}"
        )

    if cic is None:
        cic = detect_cic(data) or 6102
    seed = _SEEDS.get(cic)
    if seed is None:
        raise ValueError(f"unsupported CIC: {cic}")

    data = bytes(data)
    t1 = t2 = t3 = t4 = t5 = t6 = seed

    for i in range(CHECKSUM_START, CHECKSUM_START + CHECKSUM_LENGTH, 4):
        d = _u32(data, i)
        if ((t6 + d) & _MASK) < t6:
            t4 = (t4 + 1) & _MASK
        t6 = (t6 + d) & _MASK
        t3 ^= d
        r = _rol(d, d & 0x1F)
        t5 = (t5 + r) & _MASK
        if t2 > d:
            t2 ^= r
        else:
            t2 ^= t6 ^ d

        if cic == 6105:
            t1 = (t1 + (_u32(data, HEADER_SIZE + 0x0710 + (i & 0xFF)) ^ d)) & _MASK
        else:
            t1 = (t1 + (t5 ^ d)) & _MASK

    if cic == 6103:
        crc1 = ((t6 ^ t4) + t3) & _MASK
        crc2 = ((t5 ^ t2) + t1) & _MASK
    elif cic == 6106:
        crc1 = ((t6 * t4) + t3) & _MASK
        crc2 = ((t5 * t2) + t1) & _MASK
    else:
        crc1 = t6 ^ t4 ^ t3
        crc2 = t5 ^ t2 ^ t1

    return crc1 & _MASK, crc2 & _MASK


def file_crc32(data: bytes) -> int:
    """CRC32 of the whole image -- used for ROM fingerprinting, not booting."""
    return zlib.crc32(bytes(data)) & _MASK
