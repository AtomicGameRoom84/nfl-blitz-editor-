"""Identifying which exact ROM image is loaded.

Bookmarks, research notes and address definitions are only meaningful for
the build they were discovered on: the same address in NFL Blitz and NFL
Blitz 2000 means nothing in common.  Everything the user records is
therefore stamped with a :class:`ROMIdentity`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

from core import crc as crc_mod
from core.rom_header import ROMHeader


@dataclass(frozen=True)
class ROMIdentity:
    """A fingerprint of one specific ROM image (always big endian)."""

    image_name: str
    game_code: str
    crc1: int
    crc2: int
    size: int
    file_crc32: int
    sha1: str

    @classmethod
    def from_bytes(cls, data: bytes) -> "ROMIdentity":
        header = ROMHeader.parse(data)
        return cls(
            image_name=header.image_name,
            game_code=header.game_code,
            crc1=header.crc1,
            crc2=header.crc2,
            size=len(data),
            file_crc32=crc_mod.file_crc32(data),
            sha1=hashlib.sha1(bytes(data)).hexdigest(),
        )

    @property
    def short(self) -> str:
        """Compact key used to scope bookmarks and notes to a ROM."""
        return f"{self.game_code}-{self.crc1:08X}{self.crc2:08X}"

    @property
    def display(self) -> str:
        return f"{self.image_name or '(unnamed)'} [{self.game_code}] CRC {self.crc1:08X}/{self.crc2:08X}"

    def to_dict(self) -> dict:
        return {
            "image_name": self.image_name,
            "game_code": self.game_code,
            "crc1": f"0x{self.crc1:08X}",
            "crc2": f"0x{self.crc2:08X}",
            "size": self.size,
            "file_crc32": f"0x{self.file_crc32:08X}",
            "sha1": self.sha1,
        }

    def matches(self, other: Optional["ROMIdentity"], strict: bool = False) -> bool:
        """Compare two identities.

        ``strict`` requires the exact same file (SHA-1).  The default compares
        the header fingerprint, so a ROM you have already edited still counts
        as the same build -- otherwise your own bookmarks would stop applying
        the moment you changed a byte.
        """
        if other is None:
            return False
        if strict:
            return self.sha1 == other.sha1
        return (
            self.game_code == other.game_code
            and self.crc1 == other.crc1
            and self.crc2 == other.crc2
            and self.size == other.size
        )
