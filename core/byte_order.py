"""N64 ROM byte-order detection and conversion.

Nintendo 64 ROM dumps exist in several byte orders depending on the dumping
hardware that produced them.  Everything inside this application works on the
*big endian* (``.z64``) representation, which is the order the console itself
sees.  Files in any other order are converted on load and may be converted
back on save.

Orders
------
``Z64`` (big endian, ABCD)
    Native order.  Header magic ``80 37 12 40``.
``V64`` (byte swapped, BADC)
    Every 16-bit halfword has its two bytes swapped.  Magic ``37 80 40 12``.
``N64`` (little endian, DCBA)
    Every 32-bit word is fully reversed.  Magic ``40 12 37 80``.
``WORDSWAPPED`` (CDAB)
    Rare; the two halfwords of each 32-bit word are swapped.
    Magic ``12 40 80 37``.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

#: The first four bytes of a correctly ordered N64 ROM (PI BSD DOM1 config).
Z64_MAGIC = b"\x80\x37\x12\x40"


class ByteOrder(Enum):
    """Supported N64 ROM byte orders."""

    Z64 = "z64"
    V64 = "v64"
    N64 = "n64"
    WORDSWAPPED = "wordswapped"

    @property
    def label(self) -> str:
        return {
            ByteOrder.Z64: "Big endian (.z64, ABCD)",
            ByteOrder.V64: "Byte swapped (.v64, BADC)",
            ByteOrder.N64: "Little endian (.n64, DCBA)",
            ByteOrder.WORDSWAPPED: "Word swapped (CDAB)",
        }[self]

    @property
    def extension(self) -> str:
        return {
            ByteOrder.Z64: ".z64",
            ByteOrder.V64: ".v64",
            ByteOrder.N64: ".n64",
            ByteOrder.WORDSWAPPED: ".z64",
        }[self]


#: Magic number as it appears on disk for each order.
_MAGICS = {
    bytes([0x80, 0x37, 0x12, 0x40]): ByteOrder.Z64,
    bytes([0x37, 0x80, 0x40, 0x12]): ByteOrder.V64,
    bytes([0x40, 0x12, 0x37, 0x80]): ByteOrder.N64,
    bytes([0x12, 0x40, 0x80, 0x37]): ByteOrder.WORDSWAPPED,
}


class ByteOrderConverter:
    """Detects and converts between N64 ROM byte orders.

    All methods are static; the class exists to keep the operations grouped
    and to match the component naming used across the suite.
    """

    @staticmethod
    def detect(data: bytes) -> Optional[ByteOrder]:
        """Return the byte order of ``data``, or ``None`` if unrecognised."""
        if len(data) < 4:
            return None
        return _MAGICS.get(bytes(data[:4]))

    @staticmethod
    def detect_from_extension(filename: str) -> Optional[ByteOrder]:
        """Guess an order from a file extension.

        Only used as a hint when the header magic is unreadable; extensions
        are frequently wrong in the wild, so detection from the magic always
        wins.
        """
        lowered = filename.lower()
        for order in (ByteOrder.Z64, ByteOrder.V64, ByteOrder.N64):
            if lowered.endswith(order.extension):
                return order
        return None

    @staticmethod
    def swap16(data: bytes | bytearray) -> bytearray:
        """ABCD -> BADC (swap the bytes inside every halfword)."""
        out = bytearray(data)
        out[0 : len(out) - len(out) % 2 : 2], out[1 : len(out) : 2] = (
            out[1 : len(out) : 2],
            out[0 : len(out) - len(out) % 2 : 2],
        )
        return out

    @staticmethod
    def swap32(data: bytes | bytearray) -> bytearray:
        """ABCD -> DCBA (fully reverse every 32-bit word)."""
        out = bytearray(data)
        usable = len(out) - len(out) % 4
        for i in range(0, usable, 4):
            out[i : i + 4] = out[i : i + 4][::-1]
        return out

    @staticmethod
    def swap_words(data: bytes | bytearray) -> bytearray:
        """ABCD -> CDAB (swap the halfwords inside every 32-bit word)."""
        out = bytearray(data)
        usable = len(out) - len(out) % 4
        for i in range(0, usable, 4):
            out[i : i + 2], out[i + 2 : i + 4] = out[i + 2 : i + 4], out[i : i + 2]
        return out

    @classmethod
    def to_big_endian(cls, data: bytes | bytearray, order: ByteOrder) -> bytearray:
        """Convert ``data`` from ``order`` into canonical big endian (.z64)."""
        if order is ByteOrder.Z64:
            return bytearray(data)
        if order is ByteOrder.V64:
            return cls.swap16(data)
        if order is ByteOrder.N64:
            return cls.swap32(data)
        if order is ByteOrder.WORDSWAPPED:
            return cls.swap_words(data)
        raise ValueError(f"unsupported byte order: {order!r}")

    @classmethod
    def from_big_endian(cls, data: bytes | bytearray, order: ByteOrder) -> bytearray:
        """Convert canonical big endian ``data`` into ``order``.

        Every supported transform is its own inverse, so this mirrors
        :meth:`to_big_endian`.
        """
        return cls.to_big_endian(data, order)
