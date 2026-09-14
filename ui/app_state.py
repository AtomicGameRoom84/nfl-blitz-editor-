"""Shared application state and the signals pages listen to.

Every page receives the same :class:`AppState`.  It owns the ROM, the
address database, the bookmark database, the research log, the settings and
the backup manager, and turns the plain callbacks used by ``core`` into Qt
signals the UI can connect to.

Keeping this bridge in one place is what lets ``core``, ``tools`` and
``editors`` stay free of any Qt dependency.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import QObject, Signal

from core.address_db import AddressDatabase, GameDefinition, MatchResult
from core.backup import BackupManager
from core.bookmarks import BookmarkDatabase
from core.identity import ROMIdentity
from core.rom_manager import ROMManager
from core.settings import Settings
from tools.research import ResearchLog


class AppState(QObject):
    """The one object every page shares."""

    #: A ROM finished loading (or was closed, in which case ``is_loaded`` is False).
    romLoaded = Signal()
    romClosed = Signal()
    #: Bytes changed.  Carries the affected ``(offset, length)`` ranges.
    romChanged = Signal(list)
    #: The undo history changed (a command was executed, undone or redone).
    historyChanged = Signal()
    #: The bookmark database changed.
    bookmarksChanged = Signal()
    #: The research log changed.
    researchChanged = Signal()
    #: The active game definition changed (new ROM, or a definition edited).
    definitionChanged = Signal()
    #: Ask the main window to show a message in the status bar.
    statusMessage = Signal(str, int)
    #: Ask the main window to switch to a page by key.
    navigateRequested = Signal(str)
    #: Ask the main window to run the Save ROM As flow.
    saveAsRequested = Signal()

    def __init__(self, settings: Optional[Settings] = None) -> None:
        super().__init__()
        self.settings = settings or Settings()
        self.rom = ROMManager(history_limit=int(self.settings.get("undo_history_limit", 500)))
        self.address_db = AddressDatabase().load_all()
        self.bookmarks = BookmarkDatabase().load()
        self.research = ResearchLog().load()
        self.backups = BackupManager(self.settings.backup_path())

        self.definition: Optional[GameDefinition] = None
        self.match: Optional[MatchResult] = None
        self.identity: Optional[ROMIdentity] = None

        self.rom.add_change_listener(self._on_rom_bytes_changed)
        self.rom.undo.add_listener(self.historyChanged.emit)
        self.bookmarks.add_listener(self.bookmarksChanged.emit)
        self.research.add_listener(self.researchChanged.emit)

    # -- ROM lifecycle -----------------------------------------------------

    def _on_rom_bytes_changed(self, ranges: Sequence[Tuple[int, int]]) -> None:
        self.romChanged.emit(list(ranges))

    def load_rom(self, path: str | Path):
        """Load a ROM, identify it and refresh everything downstream."""
        report = self.rom.load_file(path)
        self.identity = ROMIdentity.from_bytes(self.rom.original)
        self.match = self.address_db.best_match(self.identity)
        self.definition = self.match.definition if self.match else None
        self.settings.push_recent_rom(path)
        self.settings.set("last_directory", str(Path(path).parent))
        self.settings.save()
        self.romLoaded.emit()
        self.definitionChanged.emit()
        return report

    def close_rom(self) -> None:
        self.rom.close()
        self.identity = None
        self.match = None
        self.definition = None
        self.romClosed.emit()
        self.definitionChanged.emit()

    def reload_definitions(self) -> None:
        """Re-read the definition files and re-identify the loaded ROM."""
        self.address_db.load_all()
        if self.identity is not None:
            self.match = self.address_db.best_match(self.identity)
            self.definition = self.match.definition if self.match else None
        self.definitionChanged.emit()

    def set_definition(self, definition: Optional[GameDefinition]) -> None:
        """Override the auto-detected definition (the ROM Manager offers this)."""
        self.definition = definition
        self.match = None
        self.definitionChanged.emit()

    # -- convenience -------------------------------------------------------

    @property
    def rom_key(self) -> str:
        return self.identity.short if self.identity else ""

    @property
    def rom_label(self) -> str:
        if self.identity is None:
            return ""
        return self.identity.display

    def matching_definitions(self) -> List[MatchResult]:
        if self.identity is None:
            return []
        return self.address_db.identify(self.identity)

    def status(self, message: str, timeout: int = 4000) -> None:
        self.statusMessage.emit(message, timeout)

    def navigate(self, page_key: str) -> None:
        self.navigateRequested.emit(page_key)

    def save_user_data(self) -> None:
        """Persist bookmarks, research notes and settings."""
        self.bookmarks.save()
        self.research.save()
        self.settings.save()
