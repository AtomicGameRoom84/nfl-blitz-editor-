"""Hex/Data Explorer: the tool that works on any ROM, supported or not."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.bookmarks import Bookmark
from core.datatypes import DataType, parse_hex_bytes, parse_number
from ui.dialogs.bookmark_dialog import BookmarkDialog
from ui.pages.base_page import Page, hint
from ui.widgets.data_inspector import DataInspector
from ui.widgets.hex_view import HexView


class HexExplorerPage(Page):
    page_key = "hex"
    page_title = "Hex / Data Explorer"
    page_subtitle = (
        "Raw byte access to the working copy. Every edit joins the shared undo "
        "history, and modified bytes are highlighted against the loaded ROM."
    )

    def build(self) -> None:
        state = self.state

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self._goto_edit = QLineEdit()
        self._goto_edit.setPlaceholderText("Go to address (0x1000)")
        self._goto_edit.setMaximumWidth(190)
        self._goto_edit.returnPressed.connect(self.go_to_address)
        toolbar.addWidget(self._goto_edit)

        go_button = QPushButton("Go")
        go_button.clicked.connect(self.go_to_address)
        toolbar.addWidget(go_button)

        self._find_edit = QLineEdit()
        self._find_edit.setPlaceholderText("Find bytes (DE AD BE EF) or \"text\"")
        self._find_edit.returnPressed.connect(self.find_next)
        toolbar.addWidget(self._find_edit, 1)

        find_button = QPushButton("Find next")
        find_button.clicked.connect(self.find_next)
        toolbar.addWidget(find_button)

        toolbar.addWidget(QLabel("Width"))
        self._width_picker = QComboBox()
        for width in (8, 16, 24, 32):
            self._width_picker.addItem(str(width), width)
        self._width_picker.setCurrentIndex(1)
        self._width_picker.activated.connect(
            lambda _: self.hex_view.set_bytes_per_row(self._width_picker.currentData())
        )
        toolbar.addWidget(self._width_picker)

        self._read_only = QCheckBox("Read only")
        self._read_only.toggled.connect(self._toggle_read_only)
        toolbar.addWidget(self._read_only)
        self.body.addLayout(toolbar)

        # -- main split ----------------------------------------------------
        split = QHBoxLayout()
        split.setSpacing(12)

        self.hex_view = HexView(state.rom)
        self.hex_view.set_bytes_per_row(int(state.settings.get("hex_bytes_per_row", 16)))
        self.hex_view.set_font_size(int(state.settings.get("hex_font_size", 12)))
        self.hex_view.set_uppercase(bool(state.settings.get("hex_uppercase", True)))
        self.hex_view.cursorMoved.connect(self._cursor_moved)
        self.hex_view.selectionChanged.connect(self._selection_changed)
        split.addWidget(self.hex_view, 1)

        side = QWidget()
        side.setMaximumWidth(310)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(10)

        self.inspector = DataInspector(state.rom)
        side_layout.addWidget(self.inspector)

        self._selection_label = QLabel("No selection")
        self._selection_label.setObjectName("Hint")
        self._selection_label.setWordWrap(True)
        side_layout.addWidget(self._selection_label)

        for label, slot in (
            ("Bookmark this address…", self.bookmark_cursor),
            ("Copy selection as hex", self.copy_selection),
            ("Paste hex at cursor…", self.paste_hex),
            ("Fill selection…", self.fill_selection),
            ("Revert selection to original", self.revert_selection),
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            side_layout.addWidget(button)

        side_layout.addWidget(
            hint(
                "Type hex digits to edit. Tab switches between the hex and ASCII "
                "columns. Ctrl+Z / Ctrl+Y undo and redo."
            )
        )
        side_layout.addStretch(1)
        split.addWidget(side)
        self.body.addLayout(split, 1)

        state.romLoaded.connect(self._rom_reloaded)
        state.romClosed.connect(self._rom_reloaded)
        state.romChanged.connect(lambda _ranges: self._refresh_highlights())
        state.bookmarksChanged.connect(self._refresh_highlights)

    # -- helpers -----------------------------------------------------------

    def on_activated(self) -> None:
        self._refresh_highlights()
        self.inspector.update_for(
            self.hex_view.cursor_offset if self.state.rom.is_loaded else None
        )
        self.hex_view.setFocus()

    def _rom_reloaded(self) -> None:
        self.hex_view.refresh()
        self._refresh_highlights()
        self.inspector.update_for(
            self.hex_view.cursor_offset if self.state.rom.is_loaded else None
        )

    def _toggle_read_only(self, enabled: bool) -> None:
        self.hex_view.set_read_only(enabled)

    def _cursor_moved(self, offset: int) -> None:
        self.inspector.update_for(offset)
        marks = self.state.bookmarks.at_address(offset)
        if marks:
            self.state.status(
                "Bookmark: " + ", ".join(f"{m.name} ({m.category})" for m in marks), 6000
            )

    def _selection_changed(self, start: int, end: int) -> None:
        length = end - start
        if length <= 1:
            self._selection_label.setText(f"Cursor at 0x{start:08X}")
        else:
            self._selection_label.setText(
                f"Selection 0x{start:08X}–0x{end - 1:08X}  ({length:,} bytes)"
            )

    def _refresh_highlights(self) -> None:
        rom = self.state.rom
        if not rom.is_loaded:
            for role in ("modified", "bookmark", "match"):
                self.hex_view.clear_highlight(role)
            return
        self.hex_view.set_highlight(
            "bookmark",
            [(b.address, b.end) for b in self.state.bookmarks.query(rom_key=self.state.rom_key)],
        )
        self.hex_view.viewport().update()

    # -- actions -----------------------------------------------------------

    def go_to_address(self) -> None:
        text = self._goto_edit.text().strip()
        if not text or not self.state.rom.is_loaded:
            return
        try:
            address = parse_number(text)
        except ValueError:
            QMessageBox.warning(
                self, "Go to address", f"{text!r} is not a number I understand."
            )
            return
        if not 0 <= address < self.state.rom.size:
            QMessageBox.warning(
                self,
                "Go to address",
                f"0x{address:X} is outside this ROM "
                f"(0x0–0x{self.state.rom.size - 1:X}).",
            )
            return
        self.hex_view.set_cursor(address)
        self.hex_view.setFocus()

    def find_next(self) -> None:
        """Find the next occurrence of a byte pattern or quoted string."""
        if not self.state.rom.is_loaded:
            return
        query = self._find_edit.text().strip()
        if not query:
            return
        if query.startswith('"') and query.endswith('"') and len(query) > 1:
            needle = query[1:-1].encode("ascii", errors="ignore")
        else:
            try:
                needle = parse_hex_bytes(query)
            except ValueError:
                needle = query.encode("ascii", errors="ignore")
        if not needle:
            return

        data = bytes(self.state.rom.data)
        start = self.hex_view.cursor_offset + 1
        found = data.find(needle, start)
        wrapped = False
        if found < 0:
            found = data.find(needle, 0)
            wrapped = True
        if found < 0:
            self.state.status(f"No match for {needle.hex(' ').upper()}", 5000)
            return
        self.hex_view.select_range(found, found + len(needle))
        self.hex_view.set_highlight("match", [(found, found + len(needle))])
        self.state.status(
            f"Found at 0x{found:08X}" + (" (wrapped to start)" if wrapped else ""), 4000
        )

    def bookmark_cursor(self) -> None:
        if not self.state.rom.is_loaded:
            return
        offset = self.hex_view.cursor_offset
        start, end = self.hex_view.selection
        length = end - start
        data_type = {1: DataType.U8, 2: DataType.U16, 4: DataType.U32}.get(
            length, DataType.U8
        )
        bookmark = Bookmark(
            name=f"Address 0x{offset:06X}",
            address=start if length > 1 else offset,
            data_type=data_type,
            rom_key=self.state.rom_key,
            rom_label=self.state.rom_label,
        )
        try:
            bookmark.default_value = bookmark.read_from(self.state.rom.data)
        except (IndexError, ValueError):
            bookmark.default_value = None

        dialog = BookmarkDialog(bookmark, self, "New bookmark")
        if dialog.exec() != BookmarkDialog.Accepted:
            return
        try:
            result = dialog.result_bookmark()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid bookmark", str(exc))
            return
        self.state.bookmarks.add(result)
        self.state.bookmarks.save()
        self.state.status(f"Bookmarked {result.name} at {result.address_hex}", 4000)

    def copy_selection(self) -> None:
        if not self.state.rom.is_loaded:
            return
        text = self.hex_view.copy_selection()
        self.state.status(f"Copied {len(text.split())} byte(s) to the clipboard.", 3000)

    def paste_hex(self) -> None:
        if not self.state.rom.is_loaded or self.hex_view.read_only:
            return
        clipboard = QApplication.clipboard().text()
        text, ok = QInputDialog.getText(
            self, "Paste hex at cursor", "Bytes to write:", text=clipboard
        )
        if not ok or not text.strip():
            return
        try:
            payload = parse_hex_bytes(text)
        except ValueError as exc:
            QMessageBox.warning(self, "Paste hex", str(exc))
            return
        written = self.hex_view.paste_bytes(payload)
        self.state.status(f"Wrote {written} byte(s).", 3000)

    def fill_selection(self) -> None:
        if not self.state.rom.is_loaded or self.hex_view.read_only:
            return
        start, end = self.hex_view.selection
        if end - start < 1:
            return
        text, ok = QInputDialog.getText(
            self,
            "Fill selection",
            f"Byte value to write across 0x{start:X}–0x{end - 1:X}:",
            text="00",
        )
        if not ok:
            return
        try:
            value = parse_number(text if text.strip().lower().startswith(("0x", "$")) else "0x" + text.strip())
        except ValueError as exc:
            QMessageBox.warning(self, "Fill selection", str(exc))
            return
        written = self.hex_view.fill_selection(value & 0xFF)
        self.state.status(f"Filled {written} byte(s).", 3000)

    def revert_selection(self) -> None:
        if not self.state.rom.is_loaded:
            return
        start, end = self.hex_view.selection
        command = self.state.rom.revert_range(start, end - start)
        if command is None:
            self.state.status("Selection already matches the original ROM.", 3000)
        else:
            self.state.status(f"Reverted {end - start} byte(s) to the original.", 4000)

    # -- external navigation ----------------------------------------------

    def show_address(self, address: int, length: int = 1) -> None:
        """Jump here from another page (a search hit, a bookmark, a diff)."""
        if not self.state.rom.is_loaded:
            return
        self.hex_view.select_range(address, address + max(1, length))
        self.hex_view.set_highlight("match", [(address, address + max(1, length))])
        self.inspector.update_for(address)
