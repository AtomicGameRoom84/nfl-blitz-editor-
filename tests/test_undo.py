"""The undo stack, including transaction rollback."""

from __future__ import annotations

import pytest

from core.undo import CompositeCommand, UndoRedoManager, WriteBytesCommand


class FakeTarget:
    """Minimal ByteTarget for testing the manager in isolation."""

    def __init__(self, size: int = 64) -> None:
        self.data = bytearray(size)

    def _raw_write(self, offset: int, data: bytes) -> None:
        self.data[offset : offset + len(data)] = data

    def read_bytes(self, offset: int, length: int) -> bytes:
        return bytes(self.data[offset : offset + length])


@pytest.fixture
def target() -> FakeTarget:
    return FakeTarget()


@pytest.fixture
def manager(target) -> UndoRedoManager:
    return UndoRedoManager(target)


def write(offset: int, new: bytes, old: bytes) -> WriteBytesCommand:
    return WriteBytesCommand(offset, new, old)


def test_write_command_requires_equal_lengths():
    with pytest.raises(ValueError, match="cannot change the ROM length"):
        WriteBytesCommand(0, b"\x01\x02", b"\x01")


def test_execute_undo_redo(manager, target):
    manager.execute(write(0, b"\x01\x02", b"\x00\x00"))
    assert target.data[:2] == b"\x01\x02"
    assert manager.can_undo and not manager.can_redo

    manager.undo()
    assert target.data[:2] == b"\x00\x00"
    assert manager.can_redo

    manager.redo()
    assert target.data[:2] == b"\x01\x02"


def test_new_command_clears_the_redo_stack(manager, target):
    manager.execute(write(0, b"\x01", b"\x00"))
    manager.undo()
    assert manager.can_redo
    manager.execute(write(4, b"\x02", b"\x00"))
    assert not manager.can_redo


def test_transaction_groups_into_one_step(manager, target):
    with manager.transaction("bulk edit"):
        manager.execute(write(0, b"\x01", b"\x00"))
        manager.execute(write(1, b"\x02", b"\x00"))
        manager.execute(write(2, b"\x03", b"\x00"))

    assert len(manager.history) == 1
    assert manager.undo_description == "bulk edit"
    manager.undo()
    assert target.data[:3] == b"\x00\x00\x00"


def test_failed_transaction_rolls_back(manager, target):
    with pytest.raises(RuntimeError):
        with manager.transaction("doomed"):
            manager.execute(write(0, b"\x01", b"\x00"))
            manager.execute(write(1, b"\x02", b"\x00"))
            raise RuntimeError("something went wrong halfway through")

    assert target.data[:2] == b"\x00\x00"
    assert not manager.can_undo


def test_nested_transactions_are_refused(manager):
    with manager.transaction("outer"):
        with pytest.raises(RuntimeError, match="nested"):
            manager.transaction("inner")


def test_composite_reverts_in_reverse_order(target):
    manager = UndoRedoManager(target)
    commands = [write(0, b"\x01", b"\x00"), write(0, b"\x02", b"\x01")]
    manager.execute(CompositeCommand(commands, "two writes to one byte"))
    assert target.data[0] == 0x02
    manager.undo()
    assert target.data[0] == 0x00


def test_history_limit_discards_the_oldest(target):
    manager = UndoRedoManager(target, history_limit=3)
    for i in range(5):
        manager.execute(write(i, bytes([i + 1]), b"\x00"))
    assert len(manager.history) == 3


def test_clean_marker(manager):
    assert manager.is_clean
    manager.execute(write(0, b"\x01", b"\x00"))
    assert not manager.is_clean
    manager.mark_clean()
    assert manager.is_clean
    manager.undo()
    assert not manager.is_clean


def test_listeners_fire_on_change(manager):
    calls = []
    manager.add_listener(lambda: calls.append(1))
    manager.execute(write(0, b"\x01", b"\x00"))
    manager.undo()
    manager.redo()
    assert len(calls) == 3
