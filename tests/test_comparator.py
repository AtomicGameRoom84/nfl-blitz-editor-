"""ROM comparison."""

from __future__ import annotations

import pytest

from core.byte_order import ByteOrder, ByteOrderConverter
from tools.comparator import DiffRegion, ROMComparator, diff_buffers


def test_identical_buffers_have_no_differences():
    assert diff_buffers(b"\x00" * 100, b"\x00" * 100) == []


def test_merge_gap_controls_grouping():
    left = bytearray(64)
    right = bytearray(64)
    right[10] = 1
    right[12] = 2
    right[40] = 3

    assert diff_buffers(left, right, merge_gap=0) == [(10, 11), (12, 13), (40, 41)]
    assert diff_buffers(left, right, merge_gap=16) == [(10, 13), (40, 41)]
    assert diff_buffers(left, right, merge_gap=64) == [(10, 41)]


def test_negative_merge_gap_is_rejected():
    with pytest.raises(ValueError):
        diff_buffers(b"\x00", b"\x01", merge_gap=-1)


def test_size_difference_is_reported_as_a_trailing_region():
    ranges = diff_buffers(b"\x00" * 32, b"\x00" * 40)
    assert ranges == [(32, 40)]


def test_comparison_summary_and_regions():
    left = bytearray(0x2000)
    right = bytearray(0x2000)
    right[0x1000:0x1002] = (999).to_bytes(2, "big")

    result = ROMComparator().compare_buffers(bytes(left), bytes(right))
    assert not result.identical
    assert len(result.regions) == 1
    assert result.changed_bytes == 2
    assert "1 differing region" in result.summary()


def test_regions_are_decoded_into_candidate_values():
    region = DiffRegion(
        offset=0x100,
        length=2,
        left_bytes=(100).to_bytes(2, "big"),
        right_bytes=(150).to_bytes(2, "big"),
    )
    readings = region.interpretations()
    big_endian_u16 = next(
        r for r in readings if r["type"] == "u16" and r["endian"] == "big"
    )
    assert big_endian_u16["before"] == 100
    assert big_endian_u16["after"] == 150
    assert big_endian_u16["delta"] == 50


def test_large_regions_are_not_decoded_as_scalars():
    region = DiffRegion(0, 32, b"\x00" * 32, b"\x01" * 32)
    assert region.interpretations() == []


def test_regions_are_labelled_by_structure():
    comparator = ROMComparator()
    assert comparator.region_name(0x10) == "ROM header"
    assert comparator.region_name(0x400) == "Boot code (CIC)"
    assert "Game data" in comparator.region_name(0x200000)


def test_different_byte_orders_normalise_before_comparing(tmp_path, demo_rom_bytes):
    z64 = tmp_path / "a.z64"
    v64 = tmp_path / "b.v64"
    z64.write_bytes(demo_rom_bytes)
    v64.write_bytes(bytes(ByteOrderConverter.from_big_endian(demo_rom_bytes, ByteOrder.V64)))

    result = ROMComparator().compare_files(z64, v64)
    assert result.identical, "the same cartridge in two byte orders must compare equal"


def test_export_csv_and_json(tmp_path):
    left = bytearray(0x100)
    right = bytearray(0x100)
    right[0x10] = 0xFF
    result = ROMComparator().compare_buffers(bytes(left), bytes(right))

    csv_path = result.to_csv(tmp_path / "diff.csv")
    assert "0x00000010" in csv_path.read_text()

    json_path = result.to_json(tmp_path / "diff.json")
    assert '"offset": 16' in json_path.read_text()


def test_working_copy_comparison_against_the_loaded_rom(rom):
    # 100 -> 1024 changes both bytes; a value sharing the high byte would
    # legitimately report a one-byte region starting at 0x8001.
    rom.write_bytes(0x8000, (1024).to_bytes(2, "big"))
    result = ROMComparator().compare_buffers(rom.original, bytes(rom.data))
    assert [(r.offset, r.length) for r in result.regions] == [(0x8000, 2)]
