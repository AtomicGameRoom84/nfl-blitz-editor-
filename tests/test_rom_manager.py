"""ROMManager: the original file is sacred, everything else is undoable."""

from __future__ import annotations

import pytest

from core.byte_order import ByteOrder, ByteOrderConverter
from core.datatypes import DataType, Endian
from core.rom_manager import ROMManager, ROMNotLoadedError
from core.rom_validator import ROMValidationError


def test_loading_leaves_the_source_file_untouched(rom, demo_rom_path, demo_rom_bytes):
    rom.write_bytes(0x2000, b"\xff" * 16)
    assert demo_rom_path.read_bytes() == demo_rom_bytes


def test_original_is_preserved_across_edits(rom):
    before = rom.original[0x2000:0x2010]
    rom.write_bytes(0x2000, b"\xff" * 16)
    assert rom.original[0x2000:0x2010] == before
    assert bytes(rom.data[0x2000:0x2010]) == b"\xff" * 16


def test_operations_require_a_loaded_rom():
    manager = ROMManager()
    assert not manager.is_loaded
    with pytest.raises(ROMNotLoadedError):
        manager.read_bytes(0, 4)
    with pytest.raises(ROMNotLoadedError):
        manager.write_bytes(0, b"\x00")


def test_reads_are_bounds_checked(rom):
    with pytest.raises(IndexError):
        rom.read_bytes(rom.size - 2, 8)
    with pytest.raises(IndexError):
        rom.read_bytes(-1, 1)


def test_writes_are_bounds_checked(rom):
    with pytest.raises(IndexError):
        rom.write_bytes(rom.size - 2, b"\x00" * 8)


def test_typed_read_and_write(rom):
    rom.write_value(0x8000, 1234, DataType.U16)
    assert rom.read_value(0x8000, DataType.U16) == 1234
    assert rom.read_value(0x8000, DataType.U16, Endian.LITTLE) != 1234


def test_write_text_refuses_to_truncate(rom):
    with pytest.raises(ValueError, match="field holds"):
        rom.write_text(0x2000, "a name far too long for this field", 12)


def test_no_op_writes_do_not_pollute_history(rom):
    existing = rom.read_bytes(0x2000, 4)
    assert rom.write_bytes(0x2000, existing) is None
    assert not rom.undo.can_undo


def test_undo_and_redo(rom):
    before = rom.read_bytes(0x2000, 4)
    rom.write_bytes(0x2000, b"\xde\xad\xbe\xef")
    assert rom.read_bytes(0x2000, 4) == b"\xde\xad\xbe\xef"

    rom.undo_last()
    assert rom.read_bytes(0x2000, 4) == before
    rom.redo_last()
    assert rom.read_bytes(0x2000, 4) == b"\xde\xad\xbe\xef"


def test_changed_ranges_merge_nearby_edits(rom):
    rom.write_bytes(0x3000, b"\x01")
    rom.write_bytes(0x3004, b"\x02")
    rom.write_bytes(0x9000, b"\x03")
    ranges = rom.changed_ranges(merge_gap=16)
    assert [(r.offset, r.length) for r in ranges] == [(0x3000, 5), (0x9000, 1)]
    assert rom.changed_byte_count() == 3


def test_revert_range_and_revert_all(rom):
    original = rom.read_bytes(0x2000, 8)
    rom.write_bytes(0x2000, b"\xff" * 8)
    rom.revert_range(0x2000, 8)
    assert rom.read_bytes(0x2000, 8) == original

    rom.write_bytes(0x2000, b"\xff" * 8)
    rom.write_bytes(0x5000, b"\xee" * 4)
    rom.revert_all()
    assert not rom.is_modified
    # revert_all is one undo step.
    rom.undo_last()
    assert rom.is_modified


def test_save_as_refuses_to_overwrite_the_source(rom, demo_rom_path):
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        rom.save_as(demo_rom_path)


def test_save_as_writes_a_new_file(rom, tmp_path):
    rom.write_bytes(0x2000, b"\xff" * 4)
    target = tmp_path / "out.z64"
    rom.save_as(target, fix_checksum=False)
    assert target.read_bytes() == bytes(rom.data)
    assert rom.undo.is_clean


def test_save_as_can_change_byte_order(rom, tmp_path):
    target = tmp_path / "out.v64"
    rom.save_as(target, ByteOrder.V64, fix_checksum=False)
    written = target.read_bytes()
    assert ByteOrderConverter.detect(written) is ByteOrder.V64
    assert bytes(ByteOrderConverter.to_big_endian(written, ByteOrder.V64)) == bytes(rom.data)


def test_dirty_tracking(rom, tmp_path):
    assert not rom.is_dirty
    rom.write_bytes(0x2000, b"\xff")
    assert rom.is_dirty
    rom.save_as(tmp_path / "out.z64", fix_checksum=False)
    # Saving marks the history clean; the working copy still differs from the
    # image that was loaded, which is what is_modified reports.
    assert rom.undo.is_clean
    assert rom.is_modified


def test_change_listeners_fire(rom):
    seen = []
    rom.add_change_listener(lambda ranges: seen.append(list(ranges)))
    rom.write_bytes(0x2000, b"\xff")
    assert seen == [[(0x2000, 1)]]


def test_load_bytes_rejects_rubbish():
    manager = ROMManager()
    with pytest.raises(ROMValidationError):
        manager.load_bytes(b"not a rom" * 100)


def test_modification_summary(rom):
    rom.write_bytes(0x4000, b"\x01\x02")
    summary = rom.modification_summary()
    assert summary["changed_bytes"] == 2
    assert summary["changed_regions"] == 1
    assert summary["history_steps"] == 1
    assert summary["first_change"] == 0x4000


def test_close_resets_everything(rom):
    rom.write_bytes(0x2000, b"\xff")
    rom.close()
    assert not rom.is_loaded
    assert rom.size == 0
    assert not rom.undo.can_undo


def test_changed_byte_count_is_fast_on_a_large_rom(rom):
    """This runs on every edit to keep the status bar current.

    A Python loop over the bytes took seconds on a 16 MiB ROM, which made
    every keystroke in the roster editor feel like a freeze.
    """
    import time

    rom.write_bytes(0x2000, b"\xff" * 8)
    started = time.monotonic()
    for _ in range(20):
        rom.changed_byte_count()
    elapsed = time.monotonic() - started
    assert rom.changed_byte_count() == 8
    assert elapsed < 2.0, f"20 counts over {rom.size} bytes took {elapsed:.2f}s"
