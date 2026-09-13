"""N64 header parsing and boot checksum behaviour."""

from __future__ import annotations

import pytest

from core import crc as crc_mod
from core.rom_header import HEADER_SIZE, ROMHeader


def test_header_fields(demo_rom_bytes):
    header = ROMHeader.parse(demo_rom_bytes)
    assert header.image_name == "MOD SUITE DEMO"
    assert header.cartridge_id == "DM"
    assert header.region == "USA"
    assert header.region_letter == "E"
    assert header.media == "Cartridge"
    assert header.game_code == "NDME"
    assert header.version_string == "1.0"


def test_header_needs_enough_bytes():
    with pytest.raises(ValueError, match="64 bytes"):
        ROMHeader.parse(b"\x80\x37\x12\x40")


def test_header_survives_non_ascii_names():
    raw = bytearray(HEADER_SIZE)
    raw[0x20:0x34] = bytes([0xFF] * 20)
    # Must not raise; the name is decoded with replacement characters.
    assert ROMHeader.parse(bytes(raw)).image_name


def test_checksum_is_deterministic_and_content_sensitive(demo_rom_bytes):
    first = crc_mod.calculate_checksum(demo_rom_bytes, 6102)
    assert crc_mod.calculate_checksum(demo_rom_bytes, 6102) == first

    changed = bytearray(demo_rom_bytes)
    changed[0x2000] ^= 0xFF
    assert crc_mod.calculate_checksum(bytes(changed), 6102) != first


def test_checksum_differs_per_cic(demo_rom_bytes):
    assert crc_mod.calculate_checksum(demo_rom_bytes, 6102) != crc_mod.calculate_checksum(
        demo_rom_bytes, 6103
    )


def test_checksum_requires_a_full_megabyte():
    with pytest.raises(ValueError, match="too small"):
        crc_mod.calculate_checksum(b"\x00" * 0x2000)


def test_unknown_cic_is_reported_not_guessed(demo_rom_bytes):
    # The demo ROM's boot code is synthetic, so it must not be claimed as a
    # known retail CIC.
    assert crc_mod.detect_cic(demo_rom_bytes) is None


def test_unsupported_cic_raises(demo_rom_bytes):
    with pytest.raises(ValueError, match="unsupported CIC"):
        crc_mod.calculate_checksum(demo_rom_bytes, 1234)


def test_file_crc32_changes_with_content(demo_rom_bytes):
    changed = bytearray(demo_rom_bytes)
    changed[100] ^= 0x01
    assert crc_mod.file_crc32(demo_rom_bytes) != crc_mod.file_crc32(bytes(changed))
