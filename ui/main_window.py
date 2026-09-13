"""The main window: sidebar navigation, menus and the save workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QWidget,
)

from core.byte_order import ByteOrder
from ui import theme
from ui.app_state import AppState
from ui.dialogs.common import (
    AboutDialog,
    PointerFinderDialog,
    SaveSummaryDialog,
    ScannerDialog,
    TextReportDialog,
)
from ui.pages.bookmarks_page import BookmarksPage
from ui.pages.compare_page import ComparePage
from ui.pages.gameplay_page import GameplayValuesPage, MovementPage, PassingPage
from ui.pages.graphics_page import GraphicsEditorPage
from ui.pages.hex_explorer_page import HexExplorerPage
from ui.pages.patch_page import PatchPage
from ui.pages.research_page import ResearchPage
from ui.pages.rom_manager_page import ROMManagerPage
from ui.pages.roster_page import RosterEditorPage
from ui.pages.search_page import SearchPage
from ui.pages.settings_page import SettingsPage
from ui.pages.team_page import TeamEditorPage

ROM_FILTER = "N64 ROMs (*.z64 *.v64 *.n64 *.rom *.bin);;All files (*)"

#: Sidebar layout: section heading followed by its page classes.
SECTIONS: Tuple[Tuple[str, Tuple[type, ...]], ...] = (
    ("ROM", (ROMManagerPage,)),
    ("EDITORS", (TeamEditorPage, RosterEditorPage, GraphicsEditorPage)),
    ("GAMEPLAY", (GameplayValuesPage, MovementPage, PassingPage)),
    ("RESEARCH", (HexExplorerPage, SearchPage, BookmarksPage, ComparePage, ResearchPage)),
    ("OUTPUT", (PatchPage, SettingsPage)),
)


class MainWindow(QMainWindow):
    """Hosts every page and owns the file menu actions."""

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state
        self.setWindowTitle("NFL Blitz Mod Suite")
        self.resize(1380, 880)

        self._pages: Dict[str, QWidget] = {}
        self._page_items: Dict[str, QListWidgetItem] = {}

        splitter = QSplitter(Qt.Horizontal)
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(230)
        self.sidebar.currentItemChanged.connect(self._sidebar_changed)
        splitter.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(0, False)
        self.setCentralWidget(splitter)

        self._build_pages()
        self._build_menus()
        self._build_status_bar()

        state.statusMessage.connect(self._show_status_message)
        state.navigateRequested.connect(self.navigate)
        state.saveAsRequested.connect(self.save_rom_as)
        state.romLoaded.connect(self._rom_state_changed)
        state.romClosed.connect(self._rom_state_changed)
        state.romChanged.connect(lambda _r: self._refresh_status())
        state.historyChanged.connect(self._refresh_status)

        self.navigate("rom")
        self._rom_state_changed()

    # -- construction ------------------------------------------------------

    def _build_pages(self) -> None:
        for heading, page_classes in SECTIONS:
            label = QListWidgetItem(heading)
            label.setFlags(Qt.NoItemFlags)
            label.setForeground(theme.color("text_faint"))
            self.sidebar.addItem(label)
            for page_class in page_classes:
                page = page_class(self.state)
                self._pages[page.page_key] = page
                self.stack.addWidget(page)
                item = QListWidgetItem(page.page_title)
                item.setData(Qt.UserRole, page.page_key)
                self.sidebar.addItem(item)
                self._page_items[page.page_key] = item

    def _build_menus(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")
        self._add_action(file_menu, "Open ROM…", self.open_rom, QKeySequence.Open)
        self._save_action = self._add_action(
            file_menu, "Save ROM As…", self.save_rom_as, QKeySequence.SaveAs
        )
        self._backup_action = self._add_action(
            file_menu, "Create Backup", self.create_backup
        )
        file_menu.addSeparator()
        self._export_patch_action = self._add_action(
            file_menu, "Export Patch…", lambda: self.navigate("patch")
        )
        self._import_patch_action = self._add_action(
            file_menu, "Import Patch…", self._import_patch
        )
        file_menu.addSeparator()
        self._close_action = self._add_action(file_menu, "Close ROM", self.close_rom)
        self._add_action(file_menu, "Exit", self.close, QKeySequence.Quit)

        edit_menu = menu_bar.addMenu("&Edit")
        self._undo_action = self._add_action(
            edit_menu, "Undo", self.undo, QKeySequence.Undo
        )
        self._redo_action = self._add_action(
            edit_menu, "Redo", self.redo, QKeySequence.Redo
        )
        edit_menu.addSeparator()
        self._revert_action = self._add_action(
            edit_menu, "Revert all changes to the original ROM", self.revert_all
        )
        self._history_action = self._add_action(
            edit_menu, "Show edit history…", self.show_history
        )

        tools_menu = menu_bar.addMenu("&Tools")
        self._scanner_action = self._add_action(tools_menu, "ROM Scanner…", self.run_scanner)
        self._add_action(tools_menu, "Compare ROMs", lambda: self.navigate("compare"))
        self._add_action(tools_menu, "Find Text", lambda: self.navigate("search"))
        self._add_action(tools_menu, "Find Values", lambda: self.navigate("search"))
        self._pointer_action = self._add_action(
            tools_menu, "Pointer Finder…", self.run_pointer_finder
        )
        self._add_action(tools_menu, "Address Bookmarks", lambda: self.navigate("bookmarks"))
        tools_menu.addSeparator()
        self._add_action(tools_menu, "Research Mode", lambda: self.navigate("research"))
        self._add_action(
            tools_menu, "Reload game definitions", self.state.reload_definitions
        )

        help_menu = menu_bar.addMenu("&Help")
        self._add_action(help_menu, "Documentation", self.show_documentation)
        self._add_action(help_menu, "About", lambda: AboutDialog(self).exec())

    @staticmethod
    def _add_action(menu, text: str, slot, shortcut=None) -> QAction:
        action = QAction(text, menu)
        action.triggered.connect(slot)
        if shortcut is not None:
            action.setShortcut(shortcut)
        menu.addAction(action)
        return action

    def _build_status_bar(self) -> None:
        bar = QStatusBar()
        self.setStatusBar(bar)
        self._rom_label = QLabel("No ROM loaded")
        self._modified_label = QLabel("")
        self._definition_label = QLabel("")
        for widget in (self._definition_label, self._modified_label, self._rom_label):
            bar.addPermanentWidget(widget)

    # -- navigation --------------------------------------------------------

    def page(self, key: str) -> Optional[QWidget]:
        """Look up a page by its key, for cross-page navigation."""
        return self._pages.get(key)

    def navigate(self, key: str) -> None:
        item = self._page_items.get(key)
        if item is not None:
            self.sidebar.setCurrentItem(item)

    def _sidebar_changed(self, current: Optional[QListWidgetItem], _previous) -> None:
        if current is None:
            return
        key = current.data(Qt.UserRole)
        page = self._pages.get(key)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        page.on_activated()

    # -- file actions ------------------------------------------------------

    def open_rom(self) -> None:
        rom_page = self._pages["rom"]
        self.navigate("rom")
        rom_page.open_rom_dialog()

    def create_backup(self) -> None:
        self._pages["rom"].create_backup()

    def close_rom(self) -> None:
        self._pages["rom"].close_rom()

    def save_rom_as(self) -> None:
        """The Save As flow, including the modification summary."""
        rom = self.state.rom
        if not rom.is_loaded:
            QMessageBox.information(self, "Save ROM As", "Open a ROM first.")
            return

        summary = rom.modification_summary()
        order = ByteOrder(self.state.settings.get("default_save_byte_order", "z64"))
        fix_crc = bool(self.state.settings.get("recalculate_crc_on_save", True))

        if self.state.settings.get("confirm_before_save", True):
            dialog = SaveSummaryDialog(summary, self._summary_lines(summary), self)
            dialog.set_defaults(order, fix_crc)
            if dialog.exec() != SaveSummaryDialog.Accepted:
                return
            order = dialog.byte_order
            fix_crc = dialog.fix_checksum

        suggested = "modified.z64"
        if rom.path is not None:
            suggested = f"{rom.path.stem}-modified{order.extension}"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save ROM As", suggested, ROM_FILTER
        )
        if not path:
            return
        if not Path(path).suffix:
            path = path + order.extension

        try:
            written = rom.save_as(path, order, fix_checksum=fix_crc)
        except (ValueError, OSError) as exc:
            QMessageBox.critical(self, "Could not save ROM", str(exc))
            return

        self.state.status(f"Saved {written}", 6000)
        self._refresh_status()
        QMessageBox.information(
            self,
            "ROM saved",
            f"Wrote {written}\n({written.stat().st_size:,} bytes)\n\n"
            "Your original file was not touched.",
        )

    def _summary_lines(self, summary: dict) -> List[str]:
        lines = []
        definition = self.state.definition
        if definition is not None:
            for page_key, label in (
                ("teams", "Teams"),
                ("roster", "Players"),
            ):
                page = self._pages.get(page_key)
                editor = getattr(page, "editor", None)
                if editor is not None and editor.availability():
                    lines.append(f"{label} table present: {editor.record_count} record(s)")
        lines.append(f"Changed regions: {summary['changed_regions']:,}")
        lines.append(f"Changed bytes: {summary['changed_bytes']:,}")
        lines.append(f"Undo history steps: {summary['history_steps']:,}")
        if summary["first_change"] is not None:
            lines.append(
                f"Change span: 0x{summary['first_change']:06X} – "
                f"0x{summary['last_change']:06X}"
            )
        if summary["changed_bytes"] == 0:
            lines.append("")
            lines.append(
                "Nothing has been modified — this would be a byte-for-byte copy."
            )
        return lines

    def _import_patch(self) -> None:
        self.navigate("patch")
        self._pages["patch"].apply_patch()

    # -- edit actions ------------------------------------------------------

    def undo(self) -> None:
        command = self.state.rom.undo_last() if self.state.rom.is_loaded else None
        if command is None:
            self.state.status("Nothing to undo.", 2500)
        else:
            self.state.status(f"Undid: {command.description}", 4000)
        self._refresh_current_page()

    def redo(self) -> None:
        command = self.state.rom.redo_last() if self.state.rom.is_loaded else None
        if command is None:
            self.state.status("Nothing to redo.", 2500)
        else:
            self.state.status(f"Redid: {command.description}", 4000)
        self._refresh_current_page()

    def revert_all(self) -> None:
        if not self.state.rom.is_loaded or not self.state.rom.is_modified:
            self.state.status("The working copy already matches the original.", 3000)
            return
        answer = QMessageBox.question(
            self,
            "Revert all changes",
            "Restore every byte to the ROM as it was loaded? This is a single "
            "undo step, so it can be reversed.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.state.rom.revert_all()
        self._refresh_current_page()

    def show_history(self) -> None:
        history = self.state.rom.undo.history
        undone = self.state.rom.undo.undone
        lines = [f"{len(history)} applied step(s), newest last:", ""]
        lines += [f"  {i + 1:4d}.  {c.description}" for i, c in enumerate(history)]
        if undone:
            lines += ["", f"{len(undone)} undone step(s) available to redo:", ""]
            lines += [f"        {c.description}" for c in undone]
        TextReportDialog("Edit history", lines, self).exec()

    def _refresh_current_page(self) -> None:
        page = self.stack.currentWidget()
        if page is not None and hasattr(page, "on_activated"):
            page.on_activated()

    # -- tools -------------------------------------------------------------

    def run_scanner(self) -> None:
        if not self.state.rom.is_loaded:
            QMessageBox.information(self, "ROM Scanner", "Open a ROM first.")
            return
        ScannerDialog(bytes(self.state.rom.data), self).exec()

    def run_pointer_finder(self) -> None:
        if not self.state.rom.is_loaded:
            QMessageBox.information(self, "Pointer Finder", "Open a ROM first.")
            return
        hex_page = self._pages.get("hex")
        target = hex_page.hex_view.cursor_offset if hex_page else 0
        PointerFinderDialog(bytes(self.state.rom.data), target, self).exec()

    def show_documentation(self) -> None:
        docs = Path(__file__).resolve().parent.parent / "docs"
        readme = Path(__file__).resolve().parent.parent / "README.md"
        lines = [
            "Documentation lives in the project folder:",
            "",
            f"  {readme}",
        ]
        if docs.is_dir():
            for path in sorted(docs.glob("*.md")):
                lines.append(f"  {path}")
        lines += [
            "",
            "Start with docs/DISCOVERING_ADDRESSES.md — it explains how to "
            "find the addresses this suite does not yet know, using the "
            "comparison, search and bookmark tools.",
        ]
        TextReportDialog("Documentation", lines, self).exec()

    # -- state -------------------------------------------------------------

    def _show_status_message(self, message: str, timeout: int) -> None:
        self.statusBar().showMessage(message, timeout)

    def _rom_state_changed(self) -> None:
        loaded = self.state.rom.is_loaded
        for key, item in self._page_items.items():
            page = self._pages[key]
            requires = getattr(page, "requires_rom", True)
            item.setFlags(
                Qt.ItemIsEnabled | Qt.ItemIsSelectable
                if loaded or not requires
                else Qt.NoItemFlags
            )
        for action in (
            self._save_action,
            self._backup_action,
            self._close_action,
            self._import_patch_action,
            self._scanner_action,
            self._pointer_action,
            self._revert_action,
        ):
            action.setEnabled(loaded)
        self._refresh_status()

    def _refresh_status(self) -> None:
        rom = self.state.rom
        undo = rom.undo
        self._undo_action.setEnabled(rom.is_loaded and undo.can_undo)
        self._redo_action.setEnabled(rom.is_loaded and undo.can_redo)
        self._undo_action.setText(
            f"Undo {undo.undo_description}" if undo.can_undo else "Undo"
        )
        self._redo_action.setText(
            f"Redo {undo.redo_description}" if undo.can_redo else "Redo"
        )

        if not rom.is_loaded:
            self._rom_label.setText("No ROM loaded")
            self._modified_label.setText("")
            self._definition_label.setText("")
            self.setWindowTitle("NFL Blitz Mod Suite")
            return

        name = rom.path.name if rom.path else "(in memory)"
        self._rom_label.setText(f"{name}   {rom.size / 1024:,.0f} KB")
        if rom.is_dirty:
            summary = rom.modification_summary()
            self._modified_label.setText(
                f"● {summary['changed_bytes']:,} byte(s) changed"
            )
            self._modified_label.setStyleSheet(f"color: {theme.COLORS['modified']};")
        else:
            self._modified_label.setText("saved")
            self._modified_label.setStyleSheet(f"color: {theme.COLORS['text_dim']};")

        definition = self.state.definition
        self._definition_label.setText(
            definition.display_name if definition else "no definition — hex tools only"
        )
        self.setWindowTitle(
            f"NFL Blitz Mod Suite — {name}" + ("*" if rom.is_dirty else "")
        )

    # -- shutdown ----------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.state.rom.is_loaded and self.state.rom.is_dirty:
            answer = QMessageBox.question(
                self,
                "Unsaved changes",
                "The working copy has modifications that have not been saved to "
                "a file. Quit anyway?\n\n"
                "(Your original ROM is untouched either way.)",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
        self.state.save_user_data()
        event.accept()
