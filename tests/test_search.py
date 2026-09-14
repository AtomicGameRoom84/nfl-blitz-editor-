"""Value, text and pattern searching."""

from __future__ import annotations

import struct

import pytest

from core.datatypes import DataType, Endian
from tools.search import ValueSearcher


@pytest.fixture
def buffer() -> bytes:
    data = bytearray(0x1000)
    data[0x100:0x102] = (100).to_bytes(2, "big")     # aligned
    data[0x201:0x203] = (100).to_bytes(2, "big")     # deliberately unaligned
    data[0x300:0x304] = struct.pack(">f", 1.5)
    data[0x400:0x410] = b"RANDALL CUNNINGH"
    data[0x500:0x504] = (5000).to_bytes(4, "big")
    return bytes(data)


def test_value_search_respects_alignment(buffer):
    searcher = ValueSearcher(buffer)
    aligned = searcher.search_value(100, DataType.U16)
    assert aligned.addresses() == [0x100]

    unaligned = searcher.search_value(100, DataType.U16, alignment=1)
    assert unaligned.addresses() == [0x100, 0x201]


def test_value_search_is_endian_aware(buffer):
    searcher = ValueSearcher(buffer)
    assert searcher.search_value(100, DataType.U16, Endian.LITTLE).addresses() != [0x100]


def test_float_search(buffer):
    searcher = ValueSearcher(buffer)
    assert searcher.search_value(1.5, DataType.F32).addresses() == [0x300]


def test_range_search(buffer):
    searcher = ValueSearcher(buffer)
    result = searcher.search_range(4000, 6000, DataType.U32, start=0x400)
    assert 0x500 in result.addresses()


def test_text_search(buffer):
    searcher = ValueSearcher(buffer)
    assert searcher.search_text("RANDALL").addresses() == [0x400]
    assert searcher.search_text("randall").addresses() == []
    assert searcher.search_text("randall", case_sensitive=False).addresses() == [0x400]


def test_find_strings(buffer):
    searcher = ValueSearcher(buffer)
    hits = searcher.find_strings(8).hits
    assert any(hit.value.startswith("RANDALL") for hit in hits)


def test_byte_pattern_search(buffer):
    searcher = ValueSearcher(buffer)
    assert searcher.search_bytes(b"\x00\x64", 0x100, 0x110).addresses() == [0x100]


def test_masked_search(buffer):
    searcher = ValueSearcher(buffer)
    # "RA?D" - matches RANDALL's first four characters with the N wildcarded.
    result = searcher.search_masked_bytes(b"RA\x00D", [True, True, False, True])
    assert 0x400 in result.addresses()


def test_masked_search_validates_input(buffer):
    searcher = ValueSearcher(buffer)
    with pytest.raises(ValueError, match="same length"):
        searcher.search_masked_bytes(b"\x01\x02", [True])
    with pytest.raises(ValueError, match="at least one byte"):
        searcher.search_masked_bytes(b"\x01", [False])


def test_search_window(buffer):
    searcher = ValueSearcher(buffer)
    assert searcher.search_value(100, DataType.U16, start=0x200).addresses() == []
    assert searcher.search_value(
        100, DataType.U16, start=0x200, alignment=1
    ).addresses() == [0x201]


def test_result_limit_marks_truncation():
    searcher = ValueSearcher(bytes(0x1000), limit=10)
    result = searcher.search_value(0, DataType.U8)
    assert len(result.hits) == 10
    assert result.truncated


def test_refine_narrows_candidates(buffer):
    first = ValueSearcher(buffer).search_value(100, DataType.U16, alignment=1)
    assert len(first) == 2

    changed = bytearray(buffer)
    changed[0x100:0x102] = (150).to_bytes(2, "big")
    second = ValueSearcher(bytes(changed))
    increased = second.refine(first, lambda value: value > 100, "increased")
    assert increased.addresses() == [0x100]

    unchanged = second.refine(first, lambda value: value == 100, "unchanged")
    assert unchanged.addresses() == [0x201]


def test_empty_pattern_is_rejected(buffer):
    with pytest.raises(ValueError, match="empty"):
        ValueSearcher(buffer).search_bytes(b"")


def test_search_finds_demo_rom_content(rom):
    searcher = ValueSearcher(rom.data)
    assert searcher.search_text("MOD SUITE DEMO CARTRIDGE").addresses()
    # The demo definition puts the running speed default (100) at 0x8000.
    assert 0x8000 in searcher.search_value(100, DataType.U16).addresses()
