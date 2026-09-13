"""Undo/redo built on a command stack.

Every mutation of the working ROM goes through a :class:`Command`, which
knows how to apply and revert itself.  Editors never touch ROM bytes
directly -- they build a command and hand it to
:class:`UndoRedoManager`, which is what makes "every modification should
support undo" true by construction rather than by convention.

This module is deliberately free of any Qt import so it stays unit
testable; the UI subscribes with plain callables.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, List, Protocol, Sequence

#: Default number of commands kept on the stack.  Each ``WriteBytesCommand``
#: stores both the old and new bytes, so a large limit on huge edits could
#: use real memory; 500 is generous for hand editing.
DEFAULT_HISTORY_LIMIT = 500


class ByteTarget(Protocol):
    """Minimal interface a command needs from the object it edits."""

    def _raw_write(self, offset: int, data: bytes) -> None: ...
    def read_bytes(self, offset: int, length: int) -> bytes: ...


class Command(ABC):
    """A single reversible modification."""

    #: Short human readable description, shown in the History panel.
    description: str = "Edit"

    @abstractmethod
    def apply(self, target: ByteTarget) -> None:
        """Perform the modification."""

    @abstractmethod
    def revert(self, target: ByteTarget) -> None:
        """Undo the modification, restoring the previous state exactly."""

    @property
    def affected_ranges(self) -> Sequence[tuple[int, int]]:
        """``(offset, length)`` pairs this command touches, for UI refresh."""
        return ()


class WriteBytesCommand(Command):
    """Replace a run of bytes at ``offset``.

    ``old_data`` is captured at construction time so the command can be
    reverted even after later edits elsewhere in the ROM.
    """

    def __init__(
        self,
        offset: int,
        new_data: bytes,
        old_data: bytes,
        description: str = "",
    ) -> None:
        if len(new_data) != len(old_data):
            raise ValueError(
                "WriteBytesCommand cannot change the ROM length: "
                f"{len(old_data)} old bytes vs {len(new_data)} new bytes"
            )
        self.offset = offset
        self.new_data = bytes(new_data)
        self.old_data = bytes(old_data)
        self.description = description or (
            f"Write {len(self.new_data)} byte(s) at 0x{offset:06X}"
        )

    def apply(self, target: ByteTarget) -> None:
        target._raw_write(self.offset, self.new_data)

    def revert(self, target: ByteTarget) -> None:
        target._raw_write(self.offset, self.old_data)

    @property
    def affected_ranges(self) -> Sequence[tuple[int, int]]:
        return ((self.offset, len(self.new_data)),)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<WriteBytesCommand 0x{self.offset:X} +{len(self.new_data)}>"


class CompositeCommand(Command):
    """Groups several commands so they undo and redo as one step.

    Used for bulk operations -- importing a roster CSV, applying a patch,
    replacing a whole table -- where undoing one row at a time would be
    infuriating.
    """

    def __init__(self, commands: Sequence[Command], description: str = "") -> None:
        self.commands: List[Command] = list(commands)
        self.description = description or f"{len(self.commands)} change(s)"

    def apply(self, target: ByteTarget) -> None:
        for command in self.commands:
            command.apply(target)

    def revert(self, target: ByteTarget) -> None:
        # Reverse order so overlapping writes restore correctly.
        for command in reversed(self.commands):
            command.revert(target)

    @property
    def affected_ranges(self) -> Sequence[tuple[int, int]]:
        ranges: List[tuple[int, int]] = []
        for command in self.commands:
            ranges.extend(command.affected_ranges)
        return ranges

    def __len__(self) -> int:
        return len(self.commands)


class UndoRedoManager:
    """Two-stack undo history over a :class:`ByteTarget`."""

    def __init__(
        self,
        target: ByteTarget,
        history_limit: int = DEFAULT_HISTORY_LIMIT,
    ) -> None:
        self._target = target
        self._undo_stack: List[Command] = []
        self._redo_stack: List[Command] = []
        self._history_limit = history_limit
        self._listeners: List[Callable[[], None]] = []
        #: Depth counter for :meth:`transaction`.
        self._pending: List[Command] | None = None
        self._pending_description = ""
        #: Index in the undo stack that was current at the last save.
        self._clean_index = 0

    # -- notification ------------------------------------------------------

    def add_listener(self, callback: Callable[[], None]) -> None:
        """Register a zero-argument callback fired after any history change."""
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self) -> None:
        for callback in list(self._listeners):
            callback()

    # -- execution ---------------------------------------------------------

    def execute(self, command: Command) -> None:
        """Apply ``command`` and push it onto the undo stack.

        Inside a :meth:`transaction` the command is applied immediately but
        buffered, so the whole block becomes one undo step.
        """
        command.apply(self._target)
        if self._pending is not None:
            self._pending.append(command)
            return
        self._push(command)

    def _push(self, command: Command) -> None:
        self._undo_stack.append(command)
        self._redo_stack.clear()
        if len(self._undo_stack) > self._history_limit:
            overflow = len(self._undo_stack) - self._history_limit
            del self._undo_stack[:overflow]
            self._clean_index = max(0, self._clean_index - overflow)
        self._notify()

    class _Transaction:
        def __init__(self, manager: "UndoRedoManager", description: str) -> None:
            self._manager = manager
            self._description = description

        def __enter__(self) -> "UndoRedoManager":
            return self._manager

        def __exit__(self, exc_type, exc, tb) -> bool:
            return self._manager._end_transaction(self._description, failed=exc is not None)

    def transaction(self, description: str = "") -> "_Transaction":
        """Context manager grouping every command inside it into one step.

        If the block raises, the commands already applied are rolled back so
        a failed bulk import cannot leave the ROM half-edited.
        """
        if self._pending is not None:
            raise RuntimeError("nested undo transactions are not supported")
        self._pending = []
        self._pending_description = description
        return UndoRedoManager._Transaction(self, description)

    def _end_transaction(self, description: str, failed: bool) -> bool:
        pending = self._pending or []
        self._pending = None
        if failed:
            for command in reversed(pending):
                command.revert(self._target)
            self._notify()
            return False  # let the exception propagate
        if not pending:
            return False
        if len(pending) == 1 and not description:
            self._push(pending[0])
        else:
            self._push(CompositeCommand(pending, description))
        return False

    # -- history -----------------------------------------------------------

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    @property
    def undo_description(self) -> str:
        return self._undo_stack[-1].description if self._undo_stack else ""

    @property
    def redo_description(self) -> str:
        return self._redo_stack[-1].description if self._redo_stack else ""

    def undo(self) -> Command | None:
        if not self._undo_stack:
            return None
        command = self._undo_stack.pop()
        command.revert(self._target)
        self._redo_stack.append(command)
        self._notify()
        return command

    def redo(self) -> Command | None:
        if not self._redo_stack:
            return None
        command = self._redo_stack.pop()
        command.apply(self._target)
        self._undo_stack.append(command)
        self._notify()
        return command

    def clear(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._clean_index = 0
        self._notify()

    @property
    def history(self) -> Sequence[Command]:
        """The applied commands, oldest first."""
        return tuple(self._undo_stack)

    @property
    def undone(self) -> Sequence[Command]:
        """Commands available to redo, most recently undone first."""
        return tuple(reversed(self._redo_stack))

    # -- dirty tracking ----------------------------------------------------

    def mark_clean(self) -> None:
        """Record the current position as "saved"."""
        self._clean_index = len(self._undo_stack)
        self._notify()

    @property
    def is_clean(self) -> bool:
        """``True`` when no un-saved commands stand between here and the mark."""
        return len(self._undo_stack) == self._clean_index
