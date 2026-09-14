"""Common contract for every editor module.

An editor is the pairing of a :class:`~core.rom_manager.ROMManager` with a
:class:`~core.address_db.GameDefinition`.  It never contains addresses of
its own: if the definition for the loaded ROM does not describe the data an
editor needs, the editor reports itself unavailable and says exactly what is
missing.  That is what keeps the suite honest about what has actually been
reverse engineered.

Editors live here, away from ``ui/``, so they can be unit tested without a
running Qt application.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from core.address_db import GameDefinition
from core.rom_manager import ROMManager


@dataclass(frozen=True)
class Availability:
    """Whether an editor can operate, and why not when it cannot."""

    available: bool
    reason: str = ""
    #: What a user would have to discover to make this editor work.
    missing: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.available


AVAILABLE = Availability(True)


class EditorModule(ABC):
    """Base class for every data editor."""

    #: Stable identifier, also used as the sidebar page key.
    module_id: str = "editor"
    #: Title shown in the UI.
    title: str = "Editor"
    #: One-line description shown under the title.
    subtitle: str = ""

    def __init__(
        self,
        rom: ROMManager,
        definition: Optional[GameDefinition] = None,
    ) -> None:
        self.rom = rom
        self.definition = definition

    def set_definition(self, definition: Optional[GameDefinition]) -> None:
        self.definition = definition

    @abstractmethod
    def availability(self) -> Availability:
        """Report whether this editor can work with the current ROM."""

    # -- shared helpers ----------------------------------------------------

    # NOTE: these return None when the requirement is *met*. Test them with
    # ``is not None`` -- an Availability is falsey when it reports a problem,
    # so a bare ``if blocked:`` silently does the opposite of what it reads.
    def _require_rom(self) -> Optional[Availability]:
        if not self.rom.is_loaded:
            return Availability(False, "No ROM is loaded.", ("a loaded ROM",))
        return None

    def _require_definition(self) -> Optional[Availability]:
        blocked = self._require_rom()
        if blocked is not None:
            return blocked
        if self.definition is None:
            return Availability(
                False,
                "This ROM version is not yet supported for automatic editing. "
                "The Hex/Data Explorer, search and comparison tools still work.",
                ("a game definition matching this ROM",),
            )
        return None

    def missing_tables(self, *table_ids: str) -> List[str]:
        """Which of the named tables the definition does not describe yet."""
        if self.definition is None:
            return list(table_ids)
        missing = []
        for table_id in table_ids:
            table = self.definition.table(table_id)
            if table is None or not table.is_discovered:
                missing.append(table_id)
        return missing
