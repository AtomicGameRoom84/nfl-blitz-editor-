"""Value Search: find candidate addresses for a value you can see in game."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
)

from core.bookmarks import Bookmark
from core.datatypes import COMMON_TYPES, Endian, parse_hex_bytes, parse_number
from tools.search import SearchResult, ValueSearcher
from ui.dialogs.bookmark_dialog import BookmarkDialog
from ui.pages.base_page import Page, card, hint

MODES = (
    ("Exact value", "value"),
    ("Value range", "range"),
    ("Text", "text"),
    ("Hex bytes", "bytes"),
    ("Hex bytes with wildcards (?? )", "masked"),
    ("All printable strings", "strings"),
)

REFINEMENTS = (
    ("unchanged since this search", "same"),
    ("changed since this search", "changed"),
    ("increased since this search", "increased"),
    ("decreased since this search", "decreased"),
    ("equal to a value…", "equals"),
)


class SearchPage(Page):
    page_key = "search"
    page_title = "Value Search"
    page_subtitle = (
        "Find every address holding a value. Narrow the list by re-searching "
        "after the value changes — that is how an unknown constant gets pinned down."
    )

    def build(self) -> None:
        self._result: Optional[SearchResult] = None

        query_card, query_layout = card("SEARCH")

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Search for"))
        self._mode = QComboBox()
        for label, key in MODES:
            self._mode.addItem(label, key)
        self._mode.activated.connect(lambda _: self._mode_changed())
        row1.addWidget(self._mode)

        self._value_edit = QLineEdit()
        self._value_edit.setPlaceholderText("100, 0x64, $64 or \"RANDY\"")
        self._value_edit.returnPressed.connect(self.run_search)
        row1.addWidget(self._value_edit, 1)

        self._to_label = QLabel("to")
        self._value2_edit = QLineEdit()
        self._value2_edit.setPlaceholderText("upper bound")
        self._value2_edit.setMaximumWidth(140)
        row1.addWidget(self._to_label)
        row1.addWidget(self._value2_edit)
        query_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Type"))
        self._type = QComboBox()
        for data_type in COMMON_TYPES:
            self._type.addItem(data_type.value, data_type)
        self._type.setCurrentIndex(2)  # u16: the most common size for a constant
        row2.addWidget(self._type)

        row2.addWidget(QLabel("Endian"))
        self._endian = QComboBox()
        for endian in Endian:
            self._endian.addItem(endian.label, endian)
        row2.addWidget(self._endian)

        row2.addWidget(QLabel("Align"))
        self._alignment = QComboBox()
        self._alignment.addItem("type size", None)
        for value in (1, 2, 4, 8, 16):
            self._alignment.addItem(str(value), value)
        row2.addWidget(self._alignment)

        self._case_sensitive = QCheckBox("Case sensitive")
        self._case_sensitive.setChecked(True)
        row2.addWidget(self._case_sensitive)

        self._min_length = QSpinBox()
        self._min_length.setRange(2, 64)
        self._min_length.setValue(5)
        self._min_length.setPrefix("min len ")
        row2.addWidget(self._min_length)
        row2.addStretch(1)
        query_layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Restrict to"))
        self._range_start = QLineEdit()
        self._range_start.setPlaceholderText("start (0x0)")
        self._range_start.setMaximumWidth(150)
        self._range_end = QLineEdit()
        self._range_end.setPlaceholderText("end (end of ROM)")
        self._range_end.setMaximumWidth(170)
        row3.addWidget(self._range_start)
        row3.addWidget(QLabel("–"))
        row3.addWidget(self._range_end)

        self._skip_boot = QCheckBox("Skip header and boot code (first 0x1000)")
        self._skip_boot.setChecked(True)
        row3.addWidget(self._skip_boot)
        row3.addStretch(1)

        search_button = QPushButton("Search ROM")
        search_button.setObjectName("Primary")
        search_button.clicked.connect(self.run_search)
        row3.addWidget(search_button)
        query_layout.addLayout(row3)
        self.body.addWidget(query_card)

        # -- refinement ----------------------------------------------------
        refine_card, refine_layout = card("NARROW THE RESULTS")
        refine_row = QHBoxLayout()
        refine_row.addWidget(QLabel("Keep addresses"))
        self._refinement = QComboBox()
        for label, key in REFINEMENTS:
            self._refinement.addItem(label, key)
        refine_row.addWidget(self._refinement)
        self._refine_value = QDoubleSpinBox()
        self._refine_value.setRange(-1e12, 1e12)
        self._refine_value.setDecimals(4)
        refine_row.addWidget(self._refine_value)
        refine_button = QPushButton("Apply")
        refine_button.clicked.connect(self.refine_results)
        refine_row.addWidget(refine_button)
        refine_row.addStretch(1)
        refine_layout.addLayout(refine_row)
        refine_layout.addWidget(
            hint(
                "Run a search, edit the value in the emulator or in another dump, "
                "load that ROM here, then apply a refinement. Addresses that did "
                "not behave as expected drop out of the list."
            )
        )
        self.body.addWidget(refine_card)

        # -- results -------------------------------------------------------
        self._summary = QLabel("No search run yet.")
        self.body.addWidget(self._summary)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Address", "Value", "Hex", "Type"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.doubleClicked.connect(lambda _: self.show_in_hex())
        self.body.addWidget(self._table, 1)

        actions = QHBoxLayout()
        for label, slot in (
            ("Show in Hex Explorer", self.show_in_hex),
            ("Bookmark selected…", self.bookmark_selected),
            ("Clear results", self.clear_results),
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            actions.addWidget(button)
        actions.addStretch(1)
        self.body.addLayout(actions)

        self._mode_changed()

    # -- helpers -----------------------------------------------------------

    def _mode_changed(self) -> None:
        mode = self._mode.currentData()
        self._value2_edit.setVisible(mode == "range")
        self._to_label.setVisible(mode == "range")
        typed = mode in ("value", "range")
        self._type.setEnabled(typed)
        self._endian.setEnabled(typed)
        self._alignment.setEnabled(typed)
        self._case_sensitive.setEnabled(mode == "text")
        self._min_length.setEnabled(mode == "strings")
        self._value_edit.setEnabled(mode != "strings")
        placeholders = {
            "value": "100, 0x64 or $64",
            "range": "lower bound",
            "text": "RANDY",
            "bytes": "DE AD BE EF",
            "masked": "DE ?? BE EF",
            "strings": "(not used)",
        }
        self._value_edit.setPlaceholderText(placeholders[mode])

    def _window(self) -> tuple[int, Optional[int]]:
        start = 0
        if self._skip_boot.isChecked():
            start = 0x1000
        if self._range_start.text().strip():
            start = parse_number(self._range_start.text())
        end = None
        if self._range_end.text().strip():
            end = parse_number(self._range_end.text())
        return start, end

    # -- actions -----------------------------------------------------------

    def run_search(self) -> None:
        if not self.state.rom.is_loaded:
            QMessageBox.information(self, "Value Search", "Load a ROM first.")
            return
        mode = self._mode.currentData()
        searcher = ValueSearcher(self.state.rom.data)
        try:
            start, end = self._window()
            if mode == "value":
                result = searcher.search_value(
                    self._parse_value(),
                    self._type.currentData(),
                    self._endian.currentData(),
                    start,
                    end,
                    self._alignment.currentData(),
                )
            elif mode == "range":
                result = searcher.search_range(
                    self._parse_value(),
                    self._parse_value(self._value2_edit.text()),
                    self._type.currentData(),
                    self._endian.currentData(),
                    start,
                    end,
                    self._alignment.currentData(),
                )
            elif mode == "text":
                result = searcher.search_text(
                    self._value_edit.text(),
                    case_sensitive=self._case_sensitive.isChecked(),
                    start=start,
                    end=end,
                )
            elif mode == "bytes":
                result = searcher.search_bytes(
                    parse_hex_bytes(self._value_edit.text()), start, end
                )
            elif mode == "masked":
                pattern, mask = self._parse_masked(self._value_edit.text())
                result = searcher.search_masked_bytes(pattern, mask, start, end)
            else:
                result = searcher.find_strings(self._min_length.value(), start, end)
        except ValueError as exc:
            QMessageBox.warning(self, "Search", str(exc))
            return

        self._result = result
        self._populate(result)

    def _parse_value(self, text: Optional[str] = None) -> float:
        raw = (text if text is not None else self._value_edit.text()).strip()
        if not raw:
            raise ValueError("Enter a value to search for.")
        if self._type.currentData().is_float:
            return float(raw)
        return parse_number(raw)

    @staticmethod
    def _parse_masked(text: str) -> tuple[bytes, List[bool]]:
        tokens = text.replace(",", " ").split()
        if not tokens:
            raise ValueError("Enter a pattern such as 'DE ?? BE EF'.")
        pattern = bytearray()
        mask: List[bool] = []
        for token in tokens:
            if token in ("??", "?", "*", "xx", "XX"):
                pattern.append(0)
                mask.append(False)
            else:
                pattern.append(int(token, 16) & 0xFF)
                mask.append(True)
        return bytes(pattern), mask

    def refine_results(self) -> None:
        if not self._result or not self._result.hits:
            QMessageBox.information(
                self, "Narrow results", "Run a search first, then refine it."
            )
            return
        if self._result.hits[0].data_type is None:
            QMessageBox.information(
                self,
                "Narrow results",
                "Refinement works on typed value searches, not on text or byte "
                "pattern searches.",
            )
            return

        key = self._refinement.currentData()
        target = self._refine_value.value()
        previous = {hit.address: hit.value for hit in self._result.hits}

        def predicate_for(address: int):
            before = previous[address]

            def check(value):
                if key == "same":
                    return value == before
                if key == "changed":
                    return value != before
                if key == "increased":
                    return value > before
                if key == "decreased":
                    return value < before
                return value == target

            return check

        kept = []
        for hit in self._result.hits:
            data_type = hit.data_type
            end = hit.address + data_type.size
            if end > self.state.rom.size:
                continue
            raw = bytes(self.state.rom.data[hit.address : end])
            value = data_type.decode(raw, hit.endian)
            if predicate_for(hit.address)(value):
                kept.append(
                    type(hit)(hit.address, value, raw, data_type, hit.endian)
                )

        self._result = SearchResult(
            hits=kept,
            description=f"{self._result.description} → "
            f"{self._refinement.currentText()}",
        )
        self._populate(self._result)

    def _populate(self, result: SearchResult) -> None:
        self._summary.setText(result.summary())
        self._table.setRowCount(0)
        shown = result.hits[:5000]
        self._table.setRowCount(len(shown))
        for row, hit in enumerate(shown):
            values = (
                hit.address_hex,
                str(hit.value),
                hit.hex,
                hit.type_label,
            )
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column == 0:
                    item.setData(Qt.UserRole, hit.address)
                self._table.setItem(row, column, item)
        if len(result.hits) > len(shown):
            self._summary.setText(
                result.summary() + f"  (showing the first {len(shown):,})"
            )

    def _selected_addresses(self) -> List[int]:
        rows = {index.row() for index in self._table.selectedIndexes()}
        addresses = []
        for row in sorted(rows):
            item = self._table.item(row, 0)
            if item is not None:
                addresses.append(item.data(Qt.UserRole))
        return addresses

    def show_in_hex(self) -> None:
        addresses = self._selected_addresses()
        if not addresses:
            return
        size = 1
        if self._result and self._result.hits:
            first = next(
                (h for h in self._result.hits if h.address == addresses[0]), None
            )
            if first is not None:
                size = len(first.raw)
        self.state.navigate("hex")
        page = self.window().page("hex")
        if page is not None:
            page.show_address(addresses[0], size)

    def bookmark_selected(self) -> None:
        addresses = self._selected_addresses()
        if not addresses:
            QMessageBox.information(self, "Bookmark", "Select one or more results.")
            return
        data_type = self._type.currentData()
        endian = self._endian.currentData()

        if len(addresses) == 1:
            bookmark = Bookmark(
                name=f"Search hit 0x{addresses[0]:06X}",
                address=addresses[0],
                data_type=data_type,
                endian=endian,
                rom_key=self.state.rom_key,
                rom_label=self.state.rom_label,
                notes=f"Found by: {self._result.description if self._result else ''}",
            )
            try:
                bookmark.default_value = bookmark.read_from(self.state.rom.data)
            except (IndexError, ValueError):
                pass
            dialog = BookmarkDialog(bookmark, self, "Bookmark search hit")
            if dialog.exec() != BookmarkDialog.Accepted:
                return
            try:
                self.state.bookmarks.add(dialog.result_bookmark())
            except ValueError as exc:
                QMessageBox.warning(self, "Bookmark", str(exc))
                return
        else:
            answer = QMessageBox.question(
                self,
                "Bookmark candidates",
                f"Save all {len(addresses)} selected addresses as candidate "
                "bookmarks in the 'Uncategorised' category?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                return
            for address in addresses:
                self.state.bookmarks.add(
                    Bookmark(
                        name=f"Candidate 0x{address:06X}",
                        address=address,
                        data_type=data_type,
                        endian=endian,
                        confidence="unknown",
                        rom_key=self.state.rom_key,
                        rom_label=self.state.rom_label,
                        notes=f"Found by: {self._result.description if self._result else ''}",
                    )
                )
        self.state.bookmarks.save()
        self.state.status(f"Bookmarked {len(addresses)} address(es).", 4000)

    def clear_results(self) -> None:
        self._result = None
        self._table.setRowCount(0)
        self._summary.setText("No search run yet.")
