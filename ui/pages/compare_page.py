"""ROM Comparison: the fastest route from "I changed something" to an address.

Dump a ROM, change one thing, dump again, compare. Every differing region is
a candidate. Regions can be bookmarked straight from the results table,
which is where the discovery workflow starts.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
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
from core.datatypes import DataType
from tools.comparator import ComparisonResult, DiffRegion, ROMComparator
from ui import theme
from ui.dialogs.bookmark_dialog import BookmarkDialog
from ui.pages.base_page import Page, card, hint

ROM_FILTER = "N64 ROMs (*.z64 *.v64 *.n64 *.rom *.bin);;All files (*)"
COLUMNS = ("Address", "Length", "Region", "Before", "After", "Reads as")


class ComparePage(Page):
    page_key = "compare"
    page_title = "ROM Comparison"
    page_subtitle = (
        "Compare two ROM files byte for byte. Different byte orders are "
        "normalised first, so a .v64 and a .z64 dump of the same cartridge "
        "compare as identical."
    )
    requires_rom = False

    def build(self) -> None:
        self._result: Optional[ComparisonResult] = None

        setup_card, setup_layout = card("ROMS TO COMPARE")

        left_row = QHBoxLayout()
        left_row.addWidget(QLabel("Original"))
        self._left_edit = QLineEdit()
        self._left_edit.setPlaceholderText("Path to the unmodified ROM")
        left_row.addWidget(self._left_edit, 1)
        left_browse = QPushButton("Browse…")
        left_browse.clicked.connect(lambda: self._browse(self._left_edit))
        left_row.addWidget(left_browse)
        left_loaded = QPushButton("Use loaded ROM (as opened)")
        left_loaded.clicked.connect(self._use_loaded_original)
        left_row.addWidget(left_loaded)
        setup_layout.addLayout(left_row)

        right_row = QHBoxLayout()
        right_row.addWidget(QLabel("Modified "))
        self._right_edit = QLineEdit()
        self._right_edit.setPlaceholderText("Path to the modified ROM")
        right_row.addWidget(self._right_edit, 1)
        right_browse = QPushButton("Browse…")
        right_browse.clicked.connect(lambda: self._browse(self._right_edit))
        right_row.addWidget(right_browse)
        right_working = QPushButton("Use working copy (your edits)")
        right_working.clicked.connect(self._use_working_copy)
        right_row.addWidget(right_working)
        setup_layout.addLayout(right_row)

        options = QHBoxLayout()
        options.addWidget(QLabel("Merge regions separated by fewer than"))
        self._merge_gap = QSpinBox()
        self._merge_gap.setRange(0, 4096)
        self._merge_gap.setValue(16)
        self._merge_gap.setSuffix(" unchanged bytes")
        options.addWidget(self._merge_gap)
        options.addStretch(1)
        compare_button = QPushButton("Compare")
        compare_button.setObjectName("Primary")
        compare_button.clicked.connect(self.run_comparison)
        options.addWidget(compare_button)
        setup_layout.addLayout(options)
        self.body.addWidget(setup_card)

        self._summary = QLabel("No comparison run yet.")
        self._summary.setWordWrap(True)
        self.body.addWidget(self._summary)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Show region"))
        self._region_filter = QComboBox()
        self._region_filter.activated.connect(lambda _: self._populate())
        filter_row.addWidget(self._region_filter, 1)
        filter_row.addWidget(QLabel("Max length"))
        self._max_length = QSpinBox()
        self._max_length.setRange(0, 1_000_000)
        self._max_length.setValue(0)
        self._max_length.setSpecialValueText("any")
        self._max_length.setToolTip(
            "Single gameplay constants show up as short regions; set this to 4 "
            "to hide bulk data changes."
        )
        self._max_length.valueChanged.connect(lambda _: self._populate())
        filter_row.addWidget(self._max_length)
        self.body.addLayout(filter_row)

        self._table = QTableWidget(0, len(COLUMNS))
        self._table.setHorizontalHeaderLabels(list(COLUMNS))
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(
            len(COLUMNS) - 1, QHeaderView.Stretch
        )
        self.body.addWidget(self._table, 1)

        actions = QHBoxLayout()
        for label, slot, primary in (
            ("Bookmark selected difference…", self.bookmark_selected, True),
            ("Show in Hex Explorer", self.show_in_hex, False),
            ("Export CSV…", self.export_csv, False),
            ("Export JSON…", self.export_json, False),
        ):
            button = QPushButton(label)
            if primary:
                button.setObjectName("Primary")
            button.clicked.connect(slot)
            actions.addWidget(button)
        actions.addStretch(1)
        self.body.addLayout(actions)

        self.body.addWidget(
            hint(
                "Workflow: change exactly one thing between the two dumps. A "
                "single changed value usually appears as a 1, 2 or 4 byte "
                "region — the 'Reads as' column decodes it for you."
            )
        )

    # -- setup helpers -----------------------------------------------------

    def _browse(self, target: QLineEdit) -> None:
        start = self.state.settings.get("last_directory", "") or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Select ROM", start, ROM_FILTER)
        if path:
            target.setText(path)

    def _use_loaded_original(self) -> None:
        if not self.state.rom.is_loaded or self.state.rom.path is None:
            QMessageBox.information(
                self, "ROM Comparison", "Open a ROM from a file first."
            )
            return
        self._left_edit.setText(str(self.state.rom.path))

    def _use_working_copy(self) -> None:
        if not self.state.rom.is_loaded:
            QMessageBox.information(self, "ROM Comparison", "Open a ROM first.")
            return
        self._right_edit.setText("<working copy>")

    # -- comparison --------------------------------------------------------

    def run_comparison(self) -> None:
        left_path = self._left_edit.text().strip()
        right_path = self._right_edit.text().strip()
        if not left_path or not right_path:
            QMessageBox.information(
                self, "ROM Comparison", "Choose two ROMs to compare."
            )
            return

        comparator = ROMComparator(merge_gap=self._merge_gap.value())
        try:
            if right_path == "<working copy>":
                if not self.state.rom.is_loaded:
                    raise ValueError("No ROM is loaded, so there is no working copy.")
                if left_path == str(self.state.rom.path):
                    left = self.state.rom.original
                    left_name = f"{Path(left_path).name} (as opened)"
                else:
                    left, _ = comparator.load_normalised(left_path)
                    left_name = Path(left_path).name
                result = comparator.compare_buffers(
                    left, bytes(self.state.rom.data), left_name, "working copy"
                )
            else:
                result = comparator.compare_files(left_path, right_path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Comparison failed", str(exc))
            return

        self._result = result
        self._refresh_region_filter()
        self._populate()
        self._summary.setText(
            f"{result.left_name}  vs  {result.right_name}\n{result.summary()}"
        )
        self._summary.setStyleSheet(
            f"color: {theme.COLORS['success'] if result.identical else theme.COLORS['text']};"
        )

    def _refresh_region_filter(self) -> None:
        self._region_filter.blockSignals(True)
        self._region_filter.clear()
        self._region_filter.addItem("All regions", None)
        if self._result:
            for name in ROMComparator.group_by_region(self._result):
                self._region_filter.addItem(name, name)
        self._region_filter.blockSignals(False)

    def _filtered(self) -> List[DiffRegion]:
        if not self._result:
            return []
        regions = self._result.regions
        wanted = self._region_filter.currentData()
        if wanted:
            regions = [r for r in regions if r.region == wanted]
        limit = self._max_length.value()
        if limit:
            regions = [r for r in regions if r.length <= limit]
        return regions

    def _populate(self) -> None:
        regions = self._filtered()
        shown = regions[:5000]
        self._table.setRowCount(len(shown))
        for row, region in enumerate(shown):
            readings = region.interpretations()
            reads_as = ""
            if readings:
                best = readings[0]
                reads_as = (
                    f"{best['type']} {best['endian'][:2].upper()}: "
                    f"{best['before']} → {best['after']}"
                )
                if best.get("delta") is not None:
                    reads_as += f"  ({best['delta']:+g})"
            else:
                before_text, after_text = region.ascii_preview()
                if before_text.strip(".") or after_text.strip("."):
                    reads_as = f"text: {before_text!r} → {after_text!r}"

            cells = (
                region.to_dict()["offset_hex"],
                str(region.length),
                region.region,
                region.left_bytes[:16].hex(" ").upper(),
                region.right_bytes[:16].hex(" ").upper(),
                reads_as,
            )
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column == 0:
                    item.setData(Qt.UserRole, row)
                self._table.setItem(row, column, item)
        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setSectionResizeMode(
            len(COLUMNS) - 1, QHeaderView.Stretch
        )
        if len(regions) > len(shown):
            self._summary.setText(
                self._summary.text() + f"\nShowing the first {len(shown):,} regions."
            )

    def _selected_regions(self) -> List[DiffRegion]:
        regions = self._filtered()
        rows = sorted({index.row() for index in self._table.selectedIndexes()})
        return [regions[row] for row in rows if row < len(regions)]

    # -- actions -----------------------------------------------------------

    def bookmark_selected(self) -> None:
        selected = self._selected_regions()
        if not selected:
            QMessageBox.information(
                self, "Bookmark", "Select a difference in the table first."
            )
            return
        region = selected[0]
        data_type = {1: DataType.U8, 2: DataType.U16, 4: DataType.U32}.get(
            region.length, DataType.U8
        )
        readings = region.interpretations()
        note = (
            f"Found by comparing {self._result.left_name} against "
            f"{self._result.right_name}."
        )
        if readings:
            note += "\nPossible readings:\n" + "\n".join(
                f"  {r['type']} {r['endian']}: {r['before']} -> {r['after']}"
                for r in readings
            )
        bookmark = Bookmark(
            name=f"Diff at 0x{region.offset:06X}",
            address=region.offset,
            data_type=data_type,
            confidence="suspected",
            notes=note,
            rom_key=self.state.rom_key,
            rom_label=self.state.rom_label,
            default_value=readings[0]["before"] if readings else None,
        )
        dialog = BookmarkDialog(bookmark, self, "Bookmark this difference")
        if dialog.exec() != BookmarkDialog.Accepted:
            return
        try:
            self.state.bookmarks.add(dialog.result_bookmark())
        except ValueError as exc:
            QMessageBox.warning(self, "Bookmark", str(exc))
            return
        self.state.bookmarks.save()
        self.state.status(f"Bookmarked 0x{region.offset:06X}", 4000)

    def show_in_hex(self) -> None:
        selected = self._selected_regions()
        if not selected:
            return
        if not self.state.rom.is_loaded:
            QMessageBox.information(
                self,
                "Hex Explorer",
                "Load one of these ROMs in the ROM Manager to inspect the "
                "address in the hex view.",
            )
            return
        region = selected[0]
        self.state.navigate("hex")
        page = self.window().page("hex")
        if page is not None:
            page.show_address(region.offset, region.length)

    def export_csv(self) -> None:
        if not self._result:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export differences", "rom-differences.csv", "CSV (*.csv)"
        )
        if path:
            self._result.to_csv(path)
            self.state.status(f"Exported to {path}", 5000)

    def export_json(self) -> None:
        if not self._result:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export differences", "rom-differences.json", "JSON (*.json)"
        )
        if path:
            self._result.to_json(path)
            self.state.status(f"Exported to {path}", 5000)
