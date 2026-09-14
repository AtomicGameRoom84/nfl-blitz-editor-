"""GameShark codes: use published research, and convert it where possible.

Two halves:

* **Known runtime addresses** — the catalogue in the loaded ROM's game
  definition. Pick values and the page generates codes to paste into an
  emulator or a real GameShark.
* **Import** — paste a code list and the page explains every line, says which
  ones can become permanent ROM edits, and applies those as one undo step.

The distinction the page keeps insisting on: a GameShark code patches RAM at
runtime. Only codes whose address lies in a *verified* RAM-to-ROM range can
become a ROM edit, and even then only if the game does not recompute the
value while it runs.
"""

from __future__ import annotations

from typing import Dict, List

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from core.address_db import RamCode
from core.bookmarks import Bookmark
from core.datatypes import DataType, parse_number
from tools.gameshark import (
    GameSharkError,
    RamMap,
    apply_to_rom,
    convert,
    float_high_half,
    make_code,
    parse_list,
)
from ui import theme
from ui.pages.base_page import Page, card, hint
from ui.widgets.table_utils import bulk_update, fit_columns

CATALOGUE_COLUMNS = ("Name", "Category", "RAM address", "Value", "GameShark code", "Notes")
IMPORT_COLUMNS = ("Code", "What it does", "Maps to ROM", "Before", "After")


class GameSharkPage(Page):
    page_key = "gameshark"
    page_title = "GameShark Codes"
    page_subtitle = (
        "Generate codes from known runtime addresses, and turn published codes "
        "into permanent ROM edits where the address is verifiably mapped."
    )
    requires_rom = False

    def build(self) -> None:
        self._catalogue: List[RamCode] = []
        self._values: Dict[str, int] = {}
        self._results = []

        # -- catalogue -----------------------------------------------------
        cat_card, cat_layout = card("KNOWN RUNTIME ADDRESSES")
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Category"))
        self._category = QComboBox()
        self._category.activated.connect(lambda _: self._refresh_catalogue())
        filter_row.addWidget(self._category)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter by name…")
        self._search.textChanged.connect(lambda _: self._refresh_catalogue())
        filter_row.addWidget(self._search, 1)
        copy_button = QPushButton("Copy codes for selected rows")
        copy_button.setObjectName("Primary")
        copy_button.clicked.connect(self.copy_selected_codes)
        filter_row.addWidget(copy_button)
        save_button = QPushButton("Save as .txt…")
        save_button.clicked.connect(self.save_selected_codes)
        filter_row.addWidget(save_button)
        cat_layout.addLayout(filter_row)

        self._table = QTableWidget(0, len(CATALOGUE_COLUMNS))
        self._table.setHorizontalHeaderLabels(list(CATALOGUE_COLUMNS))
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(
            len(CATALOGUE_COLUMNS) - 1, QHeaderView.Stretch
        )
        self._table.itemChanged.connect(self._catalogue_value_changed)
        self._table.setMinimumHeight(240)
        cat_layout.addWidget(self._table)
        self._catalogue_note = QLabel("")
        self._catalogue_note.setObjectName("Hint")
        self._catalogue_note.setWordWrap(True)
        cat_layout.addWidget(self._catalogue_note)
        self.body.addWidget(cat_card)

        # -- import --------------------------------------------------------
        import_card, import_layout = card("IMPORT CODES")
        self._input = QPlainTextEdit()
        self._input.setFont(theme.monospace_font(11))
        self._input.setMaximumHeight(120)
        self._input.setPlaceholderText(
            "Paste codes, one per line:\n"
            "812ADD6C 42C8   ; Infinite Turbo P1\n"
            "802997E3 0003   ; Fast Passes"
        )
        import_layout.addWidget(self._input)

        buttons = QHBoxLayout()
        analyse = QPushButton("Analyse")
        analyse.clicked.connect(self.analyse_codes)
        buttons.addWidget(analyse)
        load = QPushButton("Load .txt…")
        load.clicked.connect(self.load_codes)
        buttons.addWidget(load)
        self._apply_button = QPushButton("Apply convertible codes to the ROM")
        self._apply_button.setObjectName("Primary")
        self._apply_button.clicked.connect(self.apply_codes)
        self._apply_button.setEnabled(False)
        buttons.addWidget(self._apply_button)
        self._bookmark_button = QPushButton("Bookmark convertible codes")
        self._bookmark_button.clicked.connect(self.bookmark_codes)
        self._bookmark_button.setEnabled(False)
        buttons.addWidget(self._bookmark_button)
        buttons.addStretch(1)
        import_layout.addLayout(buttons)

        self._import_summary = QLabel("Nothing analysed yet.")
        self._import_summary.setWordWrap(True)
        import_layout.addWidget(self._import_summary)

        self._import_table = QTableWidget(0, len(IMPORT_COLUMNS))
        self._import_table.setHorizontalHeaderLabels(list(IMPORT_COLUMNS))
        self._import_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._import_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._import_table.setAlternatingRowColors(True)
        self._import_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self._import_table.setMinimumHeight(180)
        import_layout.addWidget(self._import_table)
        self.body.addWidget(import_card)

        self.body.addWidget(
            hint(
                "A GameShark code writes to console memory while the game runs. "
                "That is not the same as editing the ROM: a code can only become "
                "a permanent patch when its address lies in a range this "
                "definition has verified as a copy of ROM data, and even then "
                "only if the game does not recompute the value at runtime. "
                "Everything else is emulator-only — which is still useful, and "
                "still worth bookmarking. See docs/GAMESHARK_N64.md."
            )
        )

        self.state.romLoaded.connect(self._reload)
        self.state.romClosed.connect(self._reload)
        self.state.definitionChanged.connect(self._reload)
        self._reload()

    # -- catalogue ---------------------------------------------------------

    def on_activated(self) -> None:
        self._reload()

    def _ram_map(self) -> RamMap:
        if self.state.definition is None:
            return RamMap([])
        return RamMap.from_definition(self.state.definition)

    def _reload(self) -> None:
        definition = self.state.definition
        codes = list(definition.ram_codes) if definition else []
        self._catalogue = codes
        for code in codes:
            self._values.setdefault(code.id, int(code.default or 1))

        current = self._category.currentData()
        self._category.blockSignals(True)
        self._category.clear()
        self._category.addItem("All categories", None)
        for name in (definition.ram_code_categories() if definition else []):
            self._category.addItem(name, name)
        index = self._category.findData(current)
        self._category.setCurrentIndex(max(0, index))
        self._category.blockSignals(False)

        ranges = self._ram_map().ranges
        if not codes:
            self._catalogue_note.setText(
                "No runtime addresses are catalogued for this ROM. Paste "
                "published codes below, or bookmark what you find yourself."
            )
        else:
            mapped = ", ".join(
                f"0x{r.ram_start:08X}–0x{r.ram_end:08X} → ROM 0x{r.rom_start:06X}"
                for r in ranges
            ) or "none"
            self._catalogue_note.setText(
                f"{len(codes)} catalogued address(es). Verified RAM→ROM "
                f"ranges for this build: {mapped}. Addresses outside those "
                "ranges are emulator-only."
            )
        self._refresh_catalogue()

    def _visible(self) -> List[RamCode]:
        category = self._category.currentData()
        needle = self._search.text().strip().lower()
        out = []
        for code in self._catalogue:
            if category and code.category != category:
                continue
            if needle and needle not in f"{code.name} {code.notes}".lower():
                continue
            out.append(code)
        return out

    def _code_for(self, entry: RamCode) -> str:
        value = self._values.get(entry.id, 1)
        if entry.float_high_half:
            value = float_high_half(float(value))
        return make_code(entry.address, value, entry.width).format()

    def _refresh_catalogue(self) -> None:
        codes = self._visible()
        with bulk_update(self._table):
            self._table.setRowCount(len(codes))
            for row, entry in enumerate(codes):
                value = self._values.get(entry.id, 1)
                label = entry.values.get(str(value), "")
                cells = (
                    entry.name,
                    entry.category,
                    entry.address_hex,
                    f"{value}" + (f"  ({label})" if label else ""),
                    self._code_for(entry),
                    entry.notes.replace("\n", " "),
                )
                for column, text in enumerate(cells):
                    item = QTableWidgetItem(text)
                    if column == 0:
                        item.setData(Qt.UserRole, entry.id)
                    if column != 3:
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    if column == 4:
                        item.setFont(theme.monospace_font(11))
                        item.setForeground(theme.color("accent"))
                    self._table.setItem(row, column, item)
        fit_columns(self._table, stretch_column=len(CATALOGUE_COLUMNS) - 1)

    def _catalogue_value_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 3:
            return
        name_item = self._table.item(item.row(), 0)
        if name_item is None:
            return
        entry = next(
            (c for c in self._catalogue if c.id == name_item.data(Qt.UserRole)), None
        )
        if entry is None:
            return
        try:
            value = parse_number(item.text().split("(")[0])
        except ValueError:
            # Never rebuild the table from inside itemChanged: it deletes the
            # item Qt is mid-signal on and re-enters this slot.
            self.state.status(f"{item.text()!r} is not a number.", 4000)
            QTimer.singleShot(0, self._refresh_catalogue)
            return
        low = entry.minimum if entry.minimum is not None else 0
        high = entry.maximum if entry.maximum is not None else 0xFFFF
        if not low <= value <= high:
            self.state.status(
                f"{entry.name}: {value} is outside {low:g}..{high:g}.", 5000
            )
            QTimer.singleShot(0, self._refresh_catalogue)
            return
        self._values[entry.id] = int(value)
        QTimer.singleShot(0, self._refresh_catalogue)

    def _selected_entries(self) -> List[RamCode]:
        codes = self._visible()
        rows = sorted({i.row() for i in self._table.selectedIndexes()})
        return [codes[r] for r in rows if r < len(codes)]

    def _selected_code_text(self) -> str:
        chosen = self._selected_entries() or self._visible()
        lines = []
        for entry in chosen:
            lines.append(f"{self._code_for(entry)}  ; {entry.name}")
        return "\n".join(lines)

    def copy_selected_codes(self) -> None:
        text = self._selected_code_text()
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.state.status(f"Copied {len(text.splitlines())} code(s).", 4000)

    def save_selected_codes(self) -> None:
        text = self._selected_code_text()
        if not text:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save codes", "codes.txt", "Text (*.txt)"
        )
        if not path:
            return
        header = f"; {self.state.definition.display_name if self.state.definition else ''}\n"
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(header + text + "\n")
        self.state.status(f"Saved to {path}", 5000)

    # -- import ------------------------------------------------------------

    def load_codes(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load codes", "", "Text (*.txt);;All files (*)"
        )
        if not path:
            return
        try:
            self._input.setPlainText(open(path, "r", encoding="utf-8").read())
        except OSError as exc:
            QMessageBox.critical(self, "Could not read file", str(exc))
            return
        self.analyse_codes()

    def import_from_device(self) -> None:
        """Pull a game's codes out of a GameShark firmware dump."""
        from PySide6.QtWidgets import QInputDialog

        from tools.gameshark_db import find_game, list_games, load_firmware

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open a GameShark ROM",
            "",
            "N64 ROMs (*.z64 *.v64 *.n64 *.bin);;All files (*)",
        )
        if not path:
            return
        try:
            firmware = load_firmware(path)
        except OSError as exc:
            QMessageBox.critical(self, "Could not read file", str(exc))
            return

        suggestion = ""
        if self.state.rom.is_loaded and self.state.rom.header is not None:
            suggestion = self.state.rom.header.image_name.title()
        name, ok = QInputDialog.getText(
            self, "Which game?", "Game name (substring):", text=suggestion
        )
        if not ok or not name.strip():
            return

        game = find_game(firmware, name.strip())
        if game is None:
            titles = [g.name for g in list_games(firmware)][:40]
            QMessageBox.information(
                self,
                "Not found",
                f"No codes for {name!r} in that dump."
                + (
                    "\n\nGames this dump appears to cover include:\n  "
                    + "\n  ".join(titles)
                    if titles
                    else ""
                ),
            )
            return

        lines = [f"; {game.name} \u2014 from {path}"]
        for entry in game.entries:
            for code in entry.codes:
                lines.append(f"{code.format()}  ; {entry.name}")
        self._input.setPlainText("\n".join(lines))
        self.state.status(
            f"Loaded {len(game.entries)} cheat(s) for {game.name}.", 6000
        )
        self.analyse_codes()

    def analyse_codes(self) -> None:
        text = self._input.toPlainText()
        if not text.strip():
            return
        try:
            codes, problems = parse_list(text)
        except GameSharkError as exc:
            QMessageBox.warning(self, "Could not parse codes", str(exc))
            return

        rom = self.state.rom if self.state.rom.is_loaded else None
        self._results = convert(codes, self._ram_map(), rom)

        self._import_table.setRowCount(len(self._results))
        for row, result in enumerate(self._results):
            code = result.code
            meaning = code.type.name if code.type else f"unknown type {code.type_byte:02X}"
            if code.comment:
                meaning += f"  — {code.comment}"
            if result.convertible:
                maps = f"ROM 0x{result.rom_offset:06X}"
                before = result.current_bytes.hex().upper()
                after = code.payload.hex().upper()
            else:
                maps = result.reason
                before = after = ""
            for column, value in enumerate((code.format(), meaning, maps, before, after)):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setFont(theme.monospace_font(11))
                if column == 2:
                    item.setForeground(
                        theme.color("success") if result.convertible else theme.color("text_dim")
                    )
                self._import_table.setItem(row, column, item)
        fit_columns(self._import_table, stretch_column=1)

        convertible = [r for r in self._results if r.changes_anything]
        summary = (
            f"{len(codes)} code(s) parsed; "
            f"{sum(1 for r in self._results if r.convertible)} map into this ROM, "
            f"{len(convertible)} would change it."
        )
        if problems:
            summary += f"\n{len(problems)} line(s) could not be parsed: " + "; ".join(
                problems[:4]
            )
        self._import_summary.setText(summary)
        self._apply_button.setEnabled(bool(convertible) and self.state.rom.is_loaded)
        self._bookmark_button.setEnabled(
            any(r.convertible for r in self._results) and self.state.rom.is_loaded
        )

    def apply_codes(self) -> None:
        if not self.state.rom.is_loaded or not self._results:
            return
        convertible = [r for r in self._results if r.changes_anything]
        answer = QMessageBox.question(
            self,
            "Apply codes to the ROM",
            f"Write {len(convertible)} code(s) into the working copy as one "
            "undoable step?\n\nThis only makes sense for values the game reads "
            "from the ROM. A code targeting something the game recomputes at "
            "runtime will have no effect once patched.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return
        written = apply_to_rom(self.state.rom, self._results)
        self.state.status(f"Applied {written} code(s) to the working copy.", 5000)
        self.analyse_codes()

    def bookmark_codes(self) -> None:
        """Record every convertible code as a bookmark, for later research."""
        if not self.state.rom.is_loaded:
            return
        added = 0
        for result in self._results:
            if not result.convertible:
                continue
            code = result.code
            added += 1
            self.state.bookmarks.add(
                Bookmark(
                    name=code.comment or f"GameShark {code.format()}",
                    address=result.rom_offset,
                    data_type=DataType.U8 if code.width == 1 else DataType.U16,
                    category="Uncategorised",
                    confidence="suspected",
                    rom_key=self.state.rom_key,
                    rom_label=self.state.rom_label,
                    notes=(
                        f"From GameShark code {code.format()} "
                        f"(RAM 0x{code.normalised_address:08X}). "
                        f"{code.type.description if code.type else ''}"
                    ),
                )
            )
        if added:
            self.state.bookmarks.save()
        self.state.status(f"Bookmarked {added} address(es).", 4000)
