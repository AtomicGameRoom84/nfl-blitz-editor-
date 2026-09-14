"""The working ROM image and every operation performed on it.

:class:`ROMManager` owns three things:

* ``original`` -- an immutable copy of the ROM exactly as it was loaded
  (converted to big endian).  It is the reference for diffing and patch
  generation and is never written to.
* ``data`` -- the mutable working copy every editor modifies.
* an :class:`~core.undo.UndoRedoManager` through which *all* modifications
  must pass.

The file on disk is opened read-only and closed immediately.  Nothing in the
suite ever writes back to the path a ROM was loaded from; saving always goes
through :meth:`ROMManager.save_as`, which refuses to overwrite the source.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence, Tuple

from core import crc as crc_mod
from core.byte_order import ByteOrder, ByteOrderConverter
from core.datatypes import DataType, Endian
from core.rom_header import ROMHeader
from core.rom_validator import ROMValidator, ValidationReport
from core.undo import Command, UndoRedoManager, WriteBytesCommand


class ROMNotLoadedError(RuntimeError):
    """Raised when an operation needs a ROM and none is loaded."""


@dataclass(frozen=True)
class ChangedRange:
    """A contiguous run of bytes that differs from the original ROM."""

    offset: int
    length: int
    original: bytes
    modified: bytes

    @property
    def end(self) -> int:
        return self.offset + self.length


class ROMManager:
    """Loads, edits and saves a single N64 ROM image."""

    def __init__(self, history_limit: int = 500) -> None:
        self._data: bytearray = bytearray()
        self._original: bytes = b""
        self._path: Optional[Path] = None
        self._report: Optional[ValidationReport] = None
        self._source_order: ByteOrder = ByteOrder.Z64
        self._loaded = False
        self.undo = UndoRedoManager(self, history_limit=history_limit)
        self._listeners: List[Callable[[Sequence[Tuple[int, int]]], None]] = []

    # -- notification ------------------------------------------------------

    def add_change_listener(
        self, callback: Callable[[Sequence[Tuple[int, int]]], None]
    ) -> None:
        """Register a callback receiving the ``(offset, length)`` ranges edited."""
        self._listeners.append(callback)

    def remove_change_listener(
        self, callback: Callable[[Sequence[Tuple[int, int]]], None]
    ) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _emit_changed(self, ranges: Sequence[Tuple[int, int]]) -> None:
        for callback in list(self._listeners):
            callback(ranges)

    # -- loading -----------------------------------------------------------

    def load_file(self, path: str | Path) -> ValidationReport:
        """Read and validate a ROM from disk, replacing anything loaded.

        The original file is opened read-only and is never modified.

        Raises
        ------
        ROMValidationError
            If the file is not recognisable as an N64 ROM.
        OSError
            If the file cannot be read.
        """
        path = Path(path).expanduser().resolve()
        raw = path.read_bytes()
        report = ROMValidator.validate(raw, path.name)
        big_endian = ByteOrderConverter.to_big_endian(raw, report.byte_order)

        self._data = bytearray(big_endian)
        self._original = bytes(big_endian)
        self._path = path
        self._report = report
        self._source_order = report.byte_order
        self._loaded = True
        self.undo.clear()
        self.undo.mark_clean()
        self._emit_changed(((0, len(self._data)),))
        return report

    def load_bytes(
        self,
        raw: bytes,
        name: str = "<memory>",
        validate: bool = True,
    ) -> Optional[ValidationReport]:
        """Load a ROM from a buffer.  Used by tests and by patch application."""
        report: Optional[ValidationReport] = None
        order = ByteOrder.Z64
        if validate:
            report = ROMValidator.validate(raw, name)
            order = report.byte_order
        else:
            order = ByteOrderConverter.detect(raw) or ByteOrder.Z64
        big_endian = ByteOrderConverter.to_big_endian(raw, order)
        self._data = bytearray(big_endian)
        self._original = bytes(big_endian)
        self._path = None
        self._report = report
        self._source_order = order
        self._loaded = True
        self.undo.clear()
        self.undo.mark_clean()
        self._emit_changed(((0, len(self._data)),))
        return report

    def close(self) -> None:
        """Discard the working copy and reset to the unloaded state."""
        self._data = bytearray()
        self._original = b""
        self._path = None
        self._report = None
        self._loaded = False
        self.undo.clear()
        self._emit_changed(())

    # -- state -------------------------------------------------------------

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def data(self) -> bytearray:
        """The mutable working image (big endian).

        Read freely; write only through :meth:`write_bytes` so the change is
        undoable.
        """
        return self._data

    @property
    def original(self) -> bytes:
        """The pristine image as loaded, for diffing and patch generation."""
        return self._original

    @property
    def path(self) -> Optional[Path]:
        return self._path

    @property
    def size(self) -> int:
        return len(self._data)

    @property
    def report(self) -> Optional[ValidationReport]:
        return self._report

    @property
    def source_byte_order(self) -> ByteOrder:
        return self._source_order

    @property
    def header(self) -> Optional[ROMHeader]:
        if not self._loaded:
            return None
        return ROMHeader.parse(self._data)

    @property
    def is_modified(self) -> bool:
        """``True`` when the working copy differs from the loaded image."""
        return self._data != self._original

    @property
    def is_dirty(self) -> bool:
        """``True`` when there are changes not yet written to a file."""
        return not self.undo.is_clean or self.is_modified

    def _require_loaded(self) -> None:
        if not self._loaded:
            raise ROMNotLoadedError("no ROM is loaded")

    # -- reading -----------------------------------------------------------

    def read_bytes(self, offset: int, length: int) -> bytes:
        """Read ``length`` bytes; raises ``IndexError`` past the end of the ROM."""
        self._require_loaded()
        if offset < 0 or length < 0:
            raise IndexError(f"negative read: offset={offset} length={length}")
        if offset + length > len(self._data):
            raise IndexError(
                f"read of {length} bytes at 0x{offset:X} runs past the end of "
                f"the ROM (size 0x{len(self._data):X})"
            )
        return bytes(self._data[offset : offset + length])

    def read_value(
        self,
        offset: int,
        data_type: DataType,
        endian: Endian = Endian.BIG,
    ) -> Any:
        """Read a typed value at ``offset``."""
        return data_type.decode(self.read_bytes(offset, data_type.size), endian)

    def read_original_value(
        self,
        offset: int,
        data_type: DataType,
        endian: Endian = Endian.BIG,
    ) -> Any:
        """Read a typed value from the *unmodified* image."""
        self._require_loaded()
        chunk = self._original[offset : offset + data_type.size]
        return data_type.decode(chunk, endian)

    def read_text(self, offset: int, length: int, encoding: str = "ascii") -> str:
        """Read a fixed-length string, trimming NUL and space padding."""
        raw = self.read_bytes(offset, length)
        return raw.decode(encoding, errors="replace").split("\x00")[0].rstrip()

    # -- writing -----------------------------------------------------------

    def _raw_write(self, offset: int, data: bytes) -> None:
        """Unchecked write used by commands.  Never call this directly."""
        self._data[offset : offset + len(data)] = data

    def write_bytes(
        self,
        offset: int,
        data: bytes,
        description: str = "",
    ) -> Optional[Command]:
        """Write bytes through the undo stack.

        Returns the command that was executed, or ``None`` if the write was a
        no-op (the bytes were already there), so callers can avoid cluttering
        the history.
        """
        self._require_loaded()
        data = bytes(data)
        if offset < 0:
            raise IndexError(f"negative offset {offset}")
        if offset + len(data) > len(self._data):
            raise IndexError(
                f"write of {len(data)} bytes at 0x{offset:X} runs past the end "
                f"of the ROM (size 0x{len(self._data):X})"
            )
        old = bytes(self._data[offset : offset + len(data)])
        if old == data:
            return None
        command = WriteBytesCommand(offset, data, old, description)
        self.undo.execute(command)
        self._emit_changed(command.affected_ranges)
        return command

    def write_value(
        self,
        offset: int,
        value: Any,
        data_type: DataType,
        endian: Endian = Endian.BIG,
        description: str = "",
    ) -> Optional[Command]:
        """Encode and write a typed value at ``offset``."""
        encoded = data_type.encode(value, endian)
        if not description:
            description = f"Set {data_type.value} at 0x{offset:06X} = {value}"
        return self.write_bytes(offset, encoded, description)

    def write_text(
        self,
        offset: int,
        text: str,
        length: int,
        encoding: str = "ascii",
        pad: bytes = b"\x00",
        description: str = "",
    ) -> Optional[Command]:
        """Write a fixed-length, padded string.

        Refuses to write a string that does not fit, rather than silently
        truncating data the user believes they entered.
        """
        encoded = text.encode(encoding, errors="strict")
        if len(encoded) > length:
            raise ValueError(
                f"{text!r} is {len(encoded)} bytes but the field holds {length}"
            )
        encoded = encoded + pad * (length - len(encoded))
        if not description:
            description = f"Set text at 0x{offset:06X} = {text!r}"
        return self.write_bytes(offset, encoded, description)

    def revert_range(self, offset: int, length: int) -> Optional[Command]:
        """Restore a range from the originally loaded image."""
        self._require_loaded()
        return self.write_bytes(
            offset,
            self._original[offset : offset + length],
            f"Revert 0x{offset:06X}..0x{offset + length:06X} to original",
        )

    def revert_all(self) -> Optional[Command]:
        """Undo every change in one step, without clearing the history."""
        self._require_loaded()
        if not self.is_modified:
            return None
        with self.undo.transaction("Revert all changes to original ROM"):
            for change in self.changed_ranges():
                self.write_bytes(change.offset, change.original)
        self._emit_changed(((0, len(self._data)),))
        return self.undo.history[-1] if self.undo.history else None

    def apply_command(self, command: Command) -> Command:
        """Execute a pre-built command through the undo stack.

        Used by callers that construct their own command -- applying a patch,
        for instance -- so they still get undo and change notification.
        """
        self._require_loaded()
        self.undo.execute(command)
        self._emit_changed(command.affected_ranges)
        return command

    # -- undo passthrough --------------------------------------------------

    def undo_last(self) -> Optional[Command]:
        command = self.undo.undo()
        if command is not None:
            self._emit_changed(command.affected_ranges)
        return command

    def redo_last(self) -> Optional[Command]:
        command = self.undo.redo()
        if command is not None:
            self._emit_changed(command.affected_ranges)
        return command

    # -- difference tracking ----------------------------------------------

    def changed_ranges(self, merge_gap: int = 16) -> List[ChangedRange]:
        """Runs of bytes that differ from the loaded image.

        ``merge_gap`` joins runs separated by fewer than that many unchanged
        bytes, which keeps a 3-byte-apart pair of edits from reading as two
        unrelated findings.
        """
        self._require_loaded()
        from tools.comparator import diff_buffers  # local import: avoids a cycle

        return [
            ChangedRange(
                offset=start,
                length=end - start,
                original=bytes(self._original[start:end]),
                modified=bytes(self._data[start:end]),
            )
            for start, end in diff_buffers(self._original, self._data, merge_gap)
        ]

    def changed_byte_count(self) -> int:
        """How many individual bytes differ from the loaded image.

        Vectorised deliberately: this runs on every edit to keep the status
        bar current, and a Python loop over a 16 MiB ROM took seconds, which
        made every keystroke feel like a freeze.
        """
        self._require_loaded()
        import numpy as np

        limit = min(len(self._original), len(self._data))
        if limit:
            # memoryview slices, so neither buffer is copied: taking a bytes()
            # copy of a 16 MiB working image on every edit was itself the cost.
            original = np.frombuffer(memoryview(self._original)[:limit], dtype=np.uint8)
            current = np.frombuffer(memoryview(self._data)[:limit], dtype=np.uint8)
            count = int(np.count_nonzero(original != current))
        else:
            count = 0
        return count + abs(len(self._data) - len(self._original))

    # -- checksum ----------------------------------------------------------

    def detected_cic(self) -> Optional[int]:
        self._require_loaded()
        return crc_mod.detect_cic(self._data)

    def calculate_boot_checksum(self) -> Optional[Tuple[int, int]]:
        """Recompute CRC1/CRC2 for the working copy, or ``None`` if impossible."""
        self._require_loaded()
        try:
            return crc_mod.calculate_checksum(self._data, self.detected_cic())
        except ValueError:
            return None

    def stored_boot_checksum(self) -> Tuple[int, int]:
        self._require_loaded()
        return (
            int.from_bytes(self._data[0x10:0x14], "big"),
            int.from_bytes(self._data[0x14:0x18], "big"),
        )

    def fix_boot_checksum(self) -> Optional[Command]:
        """Write a freshly calculated CRC1/CRC2 into the working copy."""
        self._require_loaded()
        calculated = self.calculate_boot_checksum()
        if calculated is None:
            return None
        payload = calculated[0].to_bytes(4, "big") + calculated[1].to_bytes(4, "big")
        return self.write_bytes(0x10, payload, "Recalculate boot checksum")

    # -- saving ------------------------------------------------------------

    def to_bytes(self, byte_order: ByteOrder = ByteOrder.Z64) -> bytes:
        """Serialise the working copy in the requested byte order."""
        self._require_loaded()
        return bytes(ByteOrderConverter.from_big_endian(self._data, byte_order))

    def save_as(
        self,
        path: str | Path,
        byte_order: ByteOrder = ByteOrder.Z64,
        fix_checksum: bool = True,
        allow_overwrite_source: bool = False,
    ) -> Path:
        """Write the working copy to a new file.

        Refuses to write over the file the ROM was loaded from unless
        ``allow_overwrite_source`` is explicitly set -- the application never
        passes it, which is how "never overwrite the original ROM" is
        enforced at the lowest level rather than in the UI.
        """
        self._require_loaded()
        path = Path(path).expanduser().resolve()
        if (
            not allow_overwrite_source
            and self._path is not None
            and path == self._path
        ):
            raise ValueError(
                "Refusing to overwrite the ROM that was loaded "
                f"({self._path}). Choose a different filename."
            )
        if fix_checksum:
            self.fix_boot_checksum()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.to_bytes(byte_order))
        self.undo.mark_clean()
        return path

    # -- summary -----------------------------------------------------------

    def modification_summary(self) -> dict:
        """Counts shown in the confirmation dialog before saving."""
        self._require_loaded()
        ranges = self.changed_ranges()
        return {
            "changed_regions": len(ranges),
            "changed_bytes": self.changed_byte_count(),
            "history_steps": len(self.undo.history),
            "first_change": ranges[0].offset if ranges else None,
            "last_change": ranges[-1].end if ranges else None,
        }
