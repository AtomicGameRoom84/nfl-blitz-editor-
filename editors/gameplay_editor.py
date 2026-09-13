"""Editor for the scalar gameplay constants declared by a game definition.

The Gameplay Values, Physics & Movement and Passing & Ball Physics pages are
all this one class with a different ``category`` -- they differ only in
which entries of the definition they show.  Adding a newly discovered
constant to any of those pages means adding an entry to a JSON file.

Entries whose address is still unknown are returned too, flagged as
undiscovered, so the UI can show what the project is looking for instead of
hiding it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core.address_db import GameDefinition, ValueEntry
from core.rom_manager import ROMManager
from editors.base import AVAILABLE, Availability, EditorModule


@dataclass
class EntryState:
    """An entry plus its live values, ready to render as a slider row."""

    entry: ValueEntry
    current: Optional[float] = None
    original: Optional[float] = None
    error: str = ""

    @property
    def available(self) -> bool:
        return self.entry.is_discovered and not self.error

    @property
    def modified(self) -> bool:
        return (
            self.current is not None
            and self.original is not None
            and self.current != self.original
        )

    @property
    def display_value(self) -> Optional[float]:
        if self.current is None:
            return None
        return self.current * self.entry.scale

    @property
    def default_value(self) -> Optional[float]:
        """The definition's stated default, falling back to the ROM's own value."""
        if self.entry.default is not None:
            return self.entry.default
        return self.original


class GameplayEditor(EditorModule):
    """Reads and writes the scalar entries of one category."""

    module_id = "gameplay"
    title = "Gameplay Values"
    subtitle = "Scalar constants declared by the loaded ROM's definition"

    def __init__(
        self,
        rom: ROMManager,
        definition: Optional[GameDefinition] = None,
        category: str = "misc",
    ) -> None:
        super().__init__(rom, definition)
        self.category = category

    # -- availability ------------------------------------------------------

    def availability(self) -> Availability:
        blocked = self._require_definition()
        if blocked is not None:
            return blocked
        entries = self.definition.entries_in(self.category)
        if not entries:
            return Availability(
                False,
                f"The definition for {self.definition.display_name} declares no "
                f"{self.category} values yet.",
                (f"{self.category} addresses",),
            )
        if not any(e.is_discovered for e in entries):
            return Availability(
                False,
                f"{len(entries)} {self.category} value(s) are declared but none "
                "have been located in this ROM yet. Use ROM Comparison and the "
                "value search to find them, then promote a bookmark to a "
                "definition entry.",
                tuple(e.name for e in entries),
            )
        return AVAILABLE

    # -- reading -----------------------------------------------------------

    def entries(self, discovered_only: bool = False) -> List[ValueEntry]:
        if self.definition is None:
            return []
        return self.definition.entries_in(self.category, discovered_only)

    def groups(self) -> List[str]:
        if self.definition is None:
            return []
        return self.definition.groups_in(self.category)

    def state_for(self, entry: ValueEntry) -> EntryState:
        """Read an entry's current and original values out of the ROM."""
        if not entry.is_discovered:
            return EntryState(entry=entry)
        if not self.rom.is_loaded:
            return EntryState(entry=entry, error="No ROM is loaded.")
        if entry.address + entry.data_type.size > self.rom.size:
            return EntryState(
                entry=entry,
                error=(
                    f"{entry.address_hex} is past the end of this "
                    f"{self.rom.size} byte ROM."
                ),
            )
        return EntryState(
            entry=entry,
            current=self.rom.read_value(entry.address, entry.data_type, entry.endian),
            original=self.rom.read_original_value(
                entry.address, entry.data_type, entry.endian
            ),
        )

    def states(self, discovered_only: bool = False) -> List[EntryState]:
        return [self.state_for(e) for e in self.entries(discovered_only)]

    def states_by_group(self) -> Dict[str, List[EntryState]]:
        grouped: Dict[str, List[EntryState]] = {}
        for state in self.states():
            grouped.setdefault(state.entry.group or "General", []).append(state)
        return grouped

    # -- writing -----------------------------------------------------------

    def set_value(self, entry: ValueEntry, value: Any) -> None:
        """Write a raw (unscaled) value for ``entry``."""
        if not entry.is_discovered:
            raise ValueError(
                f"{entry.name!r} has no known address, so it cannot be edited."
            )
        low, high = entry.effective_bounds()
        if not (low <= float(value) <= high):
            raise ValueError(
                f"{value} is outside the allowed range for {entry.name} "
                f"({low:g}..{high:g})."
            )
        self.rom.write_value(
            entry.address,
            value,
            entry.data_type,
            entry.endian,
            description=f"{entry.name} = {value}",
        )

    def set_display_value(self, entry: ValueEntry, display_value: float) -> None:
        """Write a value the user typed in display units (raw = value / scale)."""
        raw = display_value / entry.scale if entry.scale else display_value
        if not entry.data_type.is_float:
            raw = round(raw)
        self.set_value(entry, raw)

    def restore_default(self, entry: ValueEntry) -> None:
        """Reset an entry to its declared default, or to the ROM's original value."""
        state = self.state_for(entry)
        target = state.default_value
        if target is None:
            raise ValueError(f"No default value is known for {entry.name!r}.")
        self.set_value(entry, target)

    def restore_all_defaults(self) -> int:
        """Reset every discovered entry in this category.  Returns the count."""
        changed = 0
        with self.rom.undo.transaction(f"Restore {self.category} defaults"):
            for state in self.states(discovered_only=True):
                if state.error or state.default_value is None:
                    continue
                if state.current != state.default_value:
                    self.set_value(state.entry, state.default_value)
                    changed += 1
        return changed

    def modified_count(self) -> int:
        return sum(1 for state in self.states(discovered_only=True) if state.modified)
