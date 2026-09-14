"""Address Bookmarks: turning a discovery into something you can reuse.

The important button on this page is "Promote to game definition". It takes
a bookmark you trust and writes it into your copy of the game definition,
at which point it appears as a labelled control in the Gameplay Values
editor. That is the whole discovery pipeline in one step:

    ROM comparison / search  ->  bookmark  ->  definition entry  ->  editor
"""

from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from core.address_db import KNOWN_CATEGORIES, entry_from_bookmark
from core.bookmarks import Bookmark
from core.datatypes import DataType
from ui import theme
from ui.dialogs.bookmark_dialog import BookmarkDialog
from ui.pages.base_page import Page, hint
from ui.widgets.table_utils import fit_columns

COLUMNS = ("Name", "Address", "Type", "Category", "Current", "Default", "Confidence", "Notes")


class BookmarksPage(Page):
    page_key = "bookmarks"
    page_title = "Address Bookmarks"
    page_subtitle = (
        "Every address you have identified, with its type, default value and "
        "notes. Promote the ones you trust into the game definition."
    )
    requires_rom = False

    def build(self) -> None:
        filters = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter by name, note, tag or address…")
        self._search.textChanged.connect(self.refresh)
        filters.addWidget(self._search, 1)

        self._category = QComboBox()
        self._category.activated.connect(lambda _: self.refresh())
        filters.addWidget(self._category)

        self._this_rom_only = QCheckBox("This ROM only")
        self._this_rom_only.setChecked(True)
        self._this_rom_only.toggled.connect(self.refresh)
        filters.addWidget(self._this_rom_only)
        self.body.addLayout(filters)

        self._table = QTableWidget(0, len(COLUMNS))
        self._table.setHorizontalHeaderLabels(list(COLUMNS))
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(
            len(COLUMNS) - 1, QHeaderView.Stretch
        )
        self._table.doubleClicked.connect(lambda _: self.edit_selected())
        self.body.addWidget(self._table, 1)

        actions = QHBoxLayout()
        for label, slot, primary in (
            ("Add…", self.add_bookmark, False),
            ("Edit…", self.edit_selected, False),
            ("Delete", self.delete_selected, False),
            ("Show in Hex Explorer", self.show_in_hex, False),
            ("Promote to game definition…", self.promote_selected, True),
        ):
            button = QPushButton(label)
            if primary:
                button.setObjectName("Primary")
            button.clicked.connect(slot)
            actions.addWidget(button)
        actions.addStretch(1)
        self.body.addLayout(actions)

        io_row = QHBoxLayout()
        for label, slot in (
            ("Import JSON…", self.import_json),
            ("Export JSON…", self.export_json),
            ("Export CSV…", self.export_csv),
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            io_row.addWidget(button)
        io_row.addStretch(1)
        self._count_label = QLabel("")
        self._count_label.setObjectName("Hint")
        io_row.addWidget(self._count_label)
        self.body.addLayout(io_row)

        self.body.addWidget(
            hint(
                "Bookmarks are stored in your user data directory as JSON, so "
                "they can be shared, version controlled and merged with other "
                "researchers' findings."
            )
        )

        self.state.bookmarksChanged.connect(self.refresh)
        self.state.romLoaded.connect(self.refresh)
        self.state.romChanged.connect(
            lambda _r: self.refresh() if self.isVisible() else None
        )
        self.refresh()

    # -- data --------------------------------------------------------------

    def on_activated(self) -> None:
        self.refresh()

    def _visible(self) -> List[Bookmark]:
        rom_key = self.state.rom_key if self._this_rom_only.isChecked() else None
        category = self._category.currentData()
        return self.state.bookmarks.query(
            text=self._search.text(), category=category, rom_key=rom_key
        )

    def refresh(self) -> None:
        current = self._category.currentData()
        self._category.blockSignals(True)
        self._category.clear()
        self._category.addItem("All categories", None)
        for name in self.state.bookmarks.categories():
            self._category.addItem(name, name)
        index = self._category.findData(current)
        self._category.setCurrentIndex(max(0, index))
        self._category.blockSignals(False)

        bookmarks = self._visible()
        self._table.setRowCount(len(bookmarks))
        for row, bookmark in enumerate(bookmarks):
            current_value = "—"
            if self.state.rom.is_loaded:
                try:
                    current_value = str(bookmark.read_from(self.state.rom.data))
                except (IndexError, ValueError):
                    current_value = "out of range"
            cells = (
                bookmark.name,
                bookmark.address_hex,
                f"{bookmark.data_type.value} {bookmark.endian.short}",
                bookmark.category,
                current_value,
                "—" if bookmark.default_value is None else str(bookmark.default_value),
                bookmark.confidence,
                bookmark.notes.replace("\n", " ")[:120],
            )
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column == 0:
                    item.setData(Qt.UserRole, bookmark.id)
                if column == 4 and current_value not in ("—", "out of range"):
                    if str(bookmark.default_value) != current_value:
                        item.setForeground(theme.color("modified"))
                self._table.setItem(row, column, item)
        fit_columns(self._table, stretch_column=len(COLUMNS) - 1)
        self._count_label.setText(
            f"{len(bookmarks)} shown of {len(self.state.bookmarks)} total"
        )

    def _selected(self) -> List[Bookmark]:
        rows = {index.row() for index in self._table.selectedIndexes()}
        found = []
        for row in sorted(rows):
            item = self._table.item(row, 0)
            if item is None:
                continue
            bookmark = self.state.bookmarks.get(item.data(Qt.UserRole))
            if bookmark is not None:
                found.append(bookmark)
        return found

    # -- actions -----------------------------------------------------------

    def add_bookmark(self) -> None:
        bookmark = Bookmark(
            name="New bookmark",
            address=0,
            data_type=DataType.U16,
            rom_key=self.state.rom_key,
            rom_label=self.state.rom_label,
        )
        dialog = BookmarkDialog(bookmark, self, "New bookmark")
        if dialog.exec() != BookmarkDialog.Accepted:
            return
        try:
            self.state.bookmarks.add(dialog.result_bookmark())
        except ValueError as exc:
            QMessageBox.warning(self, "Bookmark", str(exc))
            return
        self.state.bookmarks.save()

    def edit_selected(self) -> None:
        selected = self._selected()
        if not selected:
            return
        dialog = BookmarkDialog(selected[0], self, "Edit bookmark")
        if dialog.exec() != BookmarkDialog.Accepted:
            return
        try:
            self.state.bookmarks.update(dialog.result_bookmark())
        except ValueError as exc:
            QMessageBox.warning(self, "Bookmark", str(exc))
            return
        self.state.bookmarks.save()

    def delete_selected(self) -> None:
        selected = self._selected()
        if not selected:
            return
        answer = QMessageBox.question(
            self,
            "Delete bookmarks",
            f"Delete {len(selected)} bookmark(s)? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        for bookmark in selected:
            self.state.bookmarks.remove(bookmark.id)
        self.state.bookmarks.save()

    def show_in_hex(self) -> None:
        selected = self._selected()
        if not selected or not self.state.rom.is_loaded:
            return
        self.state.navigate("hex")
        page = self.window().page("hex")
        if page is not None:
            page.show_address(selected[0].address, selected[0].size)

    def promote_selected(self) -> None:
        """Write selected bookmarks into the active game definition."""
        selected = self._selected()
        if not selected:
            QMessageBox.information(
                self, "Promote", "Select one or more bookmarks first."
            )
            return
        definition = self.state.definition
        if definition is None:
            QMessageBox.information(
                self,
                "No game definition",
                "No definition is active for this ROM. Choose one in the ROM "
                "Manager first — promoted entries are stored in that "
                "definition's file.",
            )
            return

        category, ok = QInputDialog.getItem(
            self,
            "Promote to game definition",
            f"Add {len(selected)} entr(y/ies) to "
            f"{definition.display_name} under which category?",
            list(KNOWN_CATEGORIES),
            0,
            False,
        )
        if not ok:
            return

        updated = definition
        for bookmark in selected:
            entry = entry_from_bookmark(bookmark, category)
            updated = self.state.address_db.add_entry(updated, entry)
        self.state.definition = updated
        self.state.definitionChanged.emit()
        QMessageBox.information(
            self,
            "Promoted",
            f"Added {len(selected)} entr(y/ies) to:\n\n{updated.source_path}\n\n"
            "They now appear in the matching gameplay editor. Entries keep the "
            "confidence level from their bookmark, so anything unverified stays "
            "marked as such.",
        )

    # -- import / export ---------------------------------------------------

    def import_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import bookmarks", "", "JSON (*.json);;All files (*)"
        )
        if not path:
            return
        try:
            added = self.state.bookmarks.import_json(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
            return
        self.state.bookmarks.save()
        self.state.status(f"Imported {added} bookmark(s).", 5000)

    def export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export bookmarks", "bookmarks.json", "JSON (*.json)"
        )
        if not path:
            return
        self.state.bookmarks.export_json(path, self._visible())
        self.state.status(f"Exported to {path}", 5000)

    def export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export bookmarks", "bookmarks.csv", "CSV (*.csv)"
        )
        if not path:
            return
        self.state.bookmarks.export_csv(path)
        self.state.status(f"Exported to {path}", 5000)
