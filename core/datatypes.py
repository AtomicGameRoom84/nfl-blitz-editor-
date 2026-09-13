"""Typed views over raw ROM bytes.

Every editor, bookmark and address-database entry describes the value it
points at with a :class:`DataType` plus an :class:`Endian`.  Encoding and
decoding lives here so there is exactly one implementation of "what does
``u16 big endian`` mean" in the whole application.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class Endian(Enum):
    BIG = "big"
    LITTLE = "little"

    @property
    def struct_prefix(self) -> str:
        return ">" if self is Endian.BIG else "<"

    @property
    def label(self) -> str:
        return "Big endian" if self is Endian.BIG else "Little endian"

    @property
    def short(self) -> str:
        """Two-letter form used in dense tables: ``BE`` or ``LE``."""
        return "BE" if self is Endian.BIG else "LE"


@dataclass(frozen=True)
class _TypeInfo:
    size: int
    struct_code: str
    signed: bool
    is_float: bool
    minimum: Optional[float]
    maximum: Optional[float]
    label: str


class DataType(Enum):
    """Value types the suite can read and write inside a ROM."""

    U8 = "u8"
    S8 = "s8"
    U16 = "u16"
    S16 = "s16"
    U32 = "u32"
    S32 = "s32"
    U64 = "u64"
    S64 = "s64"
    F32 = "f32"
    F64 = "f64"

    @property
    def info(self) -> _TypeInfo:
        return _TYPE_INFO[self]

    @property
    def size(self) -> int:
        return self.info.size

    @property
    def is_float(self) -> bool:
        return self.info.is_float

    @property
    def label(self) -> str:
        return self.info.label

    @property
    def minimum(self) -> Optional[float]:
        return self.info.minimum

    @property
    def maximum(self) -> Optional[float]:
        return self.info.maximum

    # -- codec -------------------------------------------------------------

    def decode(self, data: bytes, endian: Endian = Endian.BIG) -> Any:
        """Decode exactly ``self.size`` bytes into a Python value."""
        if len(data) < self.size:
            raise ValueError(
                f"{self.value} needs {self.size} bytes, got {len(data)}"
            )
        fmt = endian.struct_prefix + self.info.struct_code
        return struct.unpack(fmt, bytes(data[: self.size]))[0]

    def encode(self, value: Any, endian: Endian = Endian.BIG) -> bytes:
        """Encode a Python value into ``self.size`` bytes.

        Raises ``ValueError`` when the value does not fit the type, so an
        out-of-range edit is reported to the user instead of silently
        wrapping around.
        """
        fmt = endian.struct_prefix + self.info.struct_code
        if self.is_float:
            value = float(value)
        else:
            value = int(value)
            lo, hi = self.info.minimum, self.info.maximum
            if lo is not None and not (lo <= value <= hi):
                raise ValueError(
                    f"{value} is outside the range of {self.value} "
                    f"({int(lo)}..{int(hi)})"
                )
        try:
            return struct.pack(fmt, value)
        except struct.error as exc:
            raise ValueError(f"cannot encode {value!r} as {self.value}: {exc}") from exc

    @classmethod
    def from_string(cls, name: str) -> "DataType":
        """Parse a type name, accepting a few friendly aliases."""
        key = name.strip().lower().replace("-", "").replace("_", "").replace(" ", "")
        aliases = {
            "byte": cls.U8, "uint8": cls.U8, "u8": cls.U8,
            "sbyte": cls.S8, "int8": cls.S8, "s8": cls.S8,
            "short": cls.U16, "uint16": cls.U16, "u16": cls.U16, "word": cls.U16,
            "int16": cls.S16, "s16": cls.S16,
            "uint32": cls.U32, "u32": cls.U32, "dword": cls.U32, "long": cls.U32,
            "int32": cls.S32, "s32": cls.S32, "int": cls.S32,
            "uint64": cls.U64, "u64": cls.U64,
            "int64": cls.S64, "s64": cls.S64,
            "float": cls.F32, "f32": cls.F32, "single": cls.F32,
            "double": cls.F64, "f64": cls.F64,
        }
        if key in aliases:
            return aliases[key]
        raise ValueError(f"unknown data type: {name!r}")


_TYPE_INFO = {
    DataType.U8: _TypeInfo(1, "B", False, False, 0, 0xFF, "8-bit unsigned"),
    DataType.S8: _TypeInfo(1, "b", True, False, -0x80, 0x7F, "8-bit signed"),
    DataType.U16: _TypeInfo(2, "H", False, False, 0, 0xFFFF, "16-bit unsigned"),
    DataType.S16: _TypeInfo(2, "h", True, False, -0x8000, 0x7FFF, "16-bit signed"),
    DataType.U32: _TypeInfo(4, "I", False, False, 0, 0xFFFFFFFF, "32-bit unsigned"),
    DataType.S32: _TypeInfo(4, "i", True, False, -0x80000000, 0x7FFFFFFF, "32-bit signed"),
    DataType.U64: _TypeInfo(8, "Q", False, False, 0, 0xFFFFFFFFFFFFFFFF, "64-bit unsigned"),
    DataType.S64: _TypeInfo(8, "q", True, False, -(2 ** 63), 2 ** 63 - 1, "64-bit signed"),
    DataType.F32: _TypeInfo(4, "f", True, True, None, None, "32-bit float"),
    DataType.F64: _TypeInfo(8, "d", True, True, None, None, "64-bit float"),
}

#: Types offered in UI drop-downs, in a sensible order.
COMMON_TYPES = (
    DataType.U8, DataType.S8,
    DataType.U16, DataType.S16,
    DataType.U32, DataType.S32,
    DataType.F32,
)


def parse_number(text: str) -> int:
    """Parse a user-entered integer in decimal, hex (``0x``/``$``) or binary.

    Underscores and surrounding whitespace are ignored, so ``0x00_12_34`` and
    ``$123456`` both work.
    """
    raw = text.strip().replace("_", "").replace(" ", "")
    if not raw:
        raise ValueError("empty number")
    negative = raw.startswith("-")
    if negative:
        raw = raw[1:]
    if raw.startswith(("0x", "0X")):
        value = int(raw[2:], 16)
    elif raw.startswith("$"):
        value = int(raw[1:], 16)
    elif raw.startswith(("0b", "0B")):
        value = int(raw[2:], 2)
    else:
        value = int(raw, 10)
    return -value if negative else value


def parse_hex_bytes(text: str) -> bytes:
    """Parse a loose hex byte string such as ``"DE AD  be:ef"``."""
    cleaned = "".join(
        ch for ch in text if ch not in " \t\r\n,:-" and ch.lower() not in ("x",)
    )
    if cleaned.lower().startswith("0") and text.strip().lower().startswith("0x"):
        cleaned = cleaned[1:]
    if len(cleaned) % 2:
        raise ValueError("hex byte string must have an even number of digits")
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise ValueError(f"not a valid hex byte string: {text!r}") from exc
