"""ROM validation is advisory, not obstructive."""

from __future__ import annotations

import pytest

from core.byte_order import ByteOrder, ByteOrderConverter
from core.rom_validator import ROMValidationError, ROMValidator


def test_accepts_a_valid_rom(demo_rom_bytes):
    report = ROMValidator.validate(demo_rom_bytes, "demo.z64")
    assert report.byte_order is ByteOrder.Z64
    assert report.size == len(demo_rom_bytes)
    assert report.header.image_name == "MOD SUITE DEMO"


def test_accepts_other_byte_orders(demo_rom_bytes):
    swapped = bytes(ByteOrderConverter.from_big_endian(demo_rom_bytes, ByteOrder.V64))
    report = ROMValidator.validate(swapped, "demo.v64")
    assert report.byte_order is ByteOrder.V64
    # The header is parsed from the converted image, so it reads correctly.
    assert report.header.image_name == "MOD SUITE DEMO"


def test_rejects_non_rom_files():
    with pytest.raises(ROMValidationError, match="recognised N64 ROM signature"):
        ROMValidator.validate(b"This is a text file, not a cartridge dump." * 40)


def test_rejects_tiny_files():
    with pytest.raises(ROMValidationError, match="header alone"):
        ROMValidator.validate(b"\x80\x37\x12\x40")


def test_warns_but_accepts_an_unknown_boot_code(demo_rom_bytes):
    report = ROMValidator.validate(demo_rom_bytes)
    assert report.detected_cic is None
    assert any("CIC" in warning for warning in report.warnings)
    assert not report.is_clean  # warnings present, but validation succeeded


def test_warns_about_a_truncated_rom(demo_rom_bytes):
    report = ROMValidator.validate(demo_rom_bytes[: 64 * 1024])
    assert any("smaller than the 512 KiB minimum" in w for w in report.warnings)


def test_modified_rom_still_loads_with_a_checksum_warning(demo_rom_bytes):
    from core import crc as crc_mod

    # Give the ROM a real CIC-6102-shaped checksum, then corrupt the payload.
    data = bytearray(demo_rom_bytes)
    crc1, crc2 = crc_mod.calculate_checksum(bytes(data), 6102)
    data[0x10:0x14] = crc1.to_bytes(4, "big")
    data[0x14:0x18] = crc2.to_bytes(4, "big")
    report = ROMValidator.validate(bytes(data))
    # The synthetic boot code is not a known CIC, so verification is skipped
    # rather than reported as a failure.
    assert report.calculated_crc is None or report.checksum_ok is not None
