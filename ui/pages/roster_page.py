"""Roster Editor page.

A spreadsheet over the ``players`` table, plus bulk editing and CSV import
and export.  Columns are generated from the field declarations, so a ROM
whose player records carry different attributes needs no code change.
"""

from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
    QVBoxLayout,
)

from editors.roster_editor import RosterEditor
from editors.team_editor import TeamEditor
from ui.pages.base_page import Page, UnavailableBanner, card, hint


class RosterEditorPage(Page):
    page_key = "roster"
    page_title = "Roster Editor"
    page_subtitle = (
        "Player names, numbers, positions and attributes. Edit a cell directly, "
        "or use the bulk tools for whole-roster changes."
    )

    def build(self) -> None:
        self.editor = RosterEditor(self.state.rom, self.state.definition)
        self.teams = TeamEditor(self.state.rom, self.state.definition)
        self._field_ids: List[str] = []
        self._row_indices: List[int] = []
        self._loading = False

        self._banner = UnavailableBanner()
        self.body.addWidget(self._banner)

        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Team"))
        self._team_filter = QComboBox()
        self._team_filter.setMinimumWidth(260)
        self._team_filter.activated.connect(lambda _: self.refresh_table())
        filters.addWidget(self._team_filter)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter by player name…")
        self._search.textChanged.connect(lambda _: self.refresh_table())
        filters.addWidget(self._search, 1)
        self._count_label = QLabel("")
        self._count_label.setObjectName("Hint")
        filters.addWidget(self._count_label)
        content_layout.addLayout(filters)

        self._table = QTableWidget(0, 0)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.itemChanged.connect(self._item_changed)
        self._table.verticalHeader().setVisible(False)
        content_layout.addWidget(self._table, 1)

        bulk_card, bulk_layout = card("BULK EDIT SELECTED PLAYERS")
        bulk_row = QHBoxLayout()
        bulk_row.addWidget(QLabel("Field"))
        self._bulk_field = QComboBox()
        bulk_row.addWidget(self._bulk_field)
        bulk_row.addWidget(QLabel("Adjust by"))
        self._bulk_delta = QDoubleSpinBox()
        self._bulk_delta.setRange(-9999, 9999)
        self._bulk_delta.setValue(5)
        bulk_row.addWidget(self._bulk_delta)
        adjust_button = QPushButton("Apply adjustment")
        adjust_button.clicked.connect(self.bulk_adjust)
        bulk_row.addWidget(adjust_button)
        bulk_row.addWidget(QLabel("Set to"))
        self._bulk_value = QDoubleSpinBox()
        self._bulk_value.setRange(-9999, 9999)
        bulk_row.addWidget(self._bulk_value)
        set_button = QPushButton("Apply value")
        set_button.clicked.connect(self.bulk_set)
        bulk_row.addWidget(set_button)
        bulk_row.addStretch(1)
        bulk_layout.addLayout(bulk_row)
        content_layout.addWidget(bulk_card)

        actions = QHBoxLayout()
        for label, slot in (
            ("Export roster CSV…", self.export_csv),
            ("Import roster CSV…", self.import_csv),
            ("Move selected to team…", self.move_to_team),
            ("Revert selected to original", self.revert_selected),
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            actions.addWidget(button)
        actions.addStretch(1)
        content_layout.addLayout(actions)

        content_layout.addWidget(
            hint(
                "Names are written in place and must fit the field width the ROM "
                "allocates; a name that is too long is refused rather than "
                "silently truncated."
            )
        )
        self.body.addWidget(self._content, 1)

        self.state.definitionChanged.connect(self.rebuild)
        self.state.romLoaded.connect(self.rebuild)
        self.state.romClosed.connect(self.rebuild)
        self.rebuild()

    # -- construction ------------------------------------------------------

    def on_activated(self) -> None:
        self.rebuild()

    def rebuild(self) -> None:
        for editor in (self.editor, self.teams):
            editor.set_definition(self.state.definition)
            editor.rom = self.state.rom

        status = self.editor.availability()
        self._banner.setVisible(not status)
        self._content.setVisible(bool(status))
        if not status:
            self._banner.show_status(status, "Roster Editor is not available yet")
            return

        self._field_ids = [field.id for field in self.editor.fields()]
        self._table.setColumnCount(len(self._field_ids) + 1)
        self._table.setHorizontalHeaderLabels(
            ["#"] + [field.name for field in self.editor.fields()]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        self._bulk_field.clear()
        for field_id in self.editor.attribute_fields():
            field = self.editor.table.field(field_id)
            self._bulk_field.addItem(field.name if field else field_id, field_id)

        self._refresh_team_filter()
        self.refresh_table()

    def _refresh_team_filter(self) -> None:
        current = self._team_filter.currentData()
        self._team_filter.blockSignals(True)
        self._team_filter.clear()
        self._team_filter.addItem("All players", None)
        if self.teams.availability():
            for record in self.teams.records():
                self._team_filter.addItem(self.teams.team_label(record), record.index)
        index = self._team_filter.findData(current)
        self._team_filter.setCurrentIndex(max(0, index))
        self._team_filter.blockSignals(False)

    def refresh_table(self) -> None:
        if not self.editor.availability():
            return
        team = self._team_filter.currentData()
        needle = self._search.text().strip().lower()

        records = (
            list(self.editor.records())
            if team is None
            else self.editor.players_for_team(team)
        )
        if needle:
            records = [
                r for r in records if needle in str(r.get("name", "")).lower()
            ]

        self._loading = True
        try:
            self._row_indices = [record.index for record in records]
            self._table.setRowCount(len(records))
            for row, record in enumerate(records):
                index_item = QTableWidgetItem(str(record.index))
                index_item.setFlags(index_item.flags() & ~Qt.ItemIsEditable)
                index_item.setData(Qt.UserRole, record.index)
                self._table.setItem(row, 0, index_item)
                for column, field_id in enumerate(self._field_ids, start=1):
                    value = record.values.get(field_id)
                    field = self.editor.table.field(field_id)
                    if field is not None and field.kind == "enum":
                        # Show the definition's label ("QB"), not the raw byte.
                        text = self.editor.position_label(value) if field_id == "position" \
                            else str(field.options.get("values", {}).get(str(value), value))
                    elif isinstance(value, float):
                        # A float read back from 4 bytes prints 17 digits of
                        # binary noise otherwise.
                        text = f"{value:g}"
                    else:
                        text = str(value)
                    item = QTableWidgetItem(text)
                    item.setData(Qt.UserRole, record.index)
                    self._table.setItem(row, column, item)
        finally:
            self._loading = False
        self._count_label.setText(f"{len(records)} player(s)")

    # -- editing -----------------------------------------------------------

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or item.column() == 0:
            return
        record_index = item.data(Qt.UserRole)
        field_id = self._field_ids[item.column() - 1]
        field = self.editor.table.field(field_id)
        text = item.text()
        try:
            if field is not None and field.kind == "text":
                value = text
            elif field is not None and field.kind == "enum":
                value = self._enum_value(field, text)
            elif field is not None and field.data_type.is_float:
                value = float(text)
            else:
                value = int(text, 0)
            self.editor.write_field(record_index, field_id, value)
        except (ValueError, KeyError, RuntimeError, IndexError) as exc:
            QMessageBox.warning(self, "Could not write value", str(exc))
            self.refresh_table()
            return
        self.state.status(
            f"Player #{record_index}: {field.name if field else field_id} = {value}", 3000
        )

    @staticmethod
    def _enum_value(field, text: str) -> int:
        """Accept either an enum label ("QB") or its raw number."""
        options = field.options.get("values", {})
        for raw, label in options.items():
            if str(label).strip().lower() == text.strip().lower():
                return int(raw)
        try:
            return int(text, 0)
        except ValueError as exc:
            allowed = ", ".join(str(v) for v in options.values())
            raise ValueError(
                f"{text!r} is not a valid {field.name}. Expected one of: {allowed}"
            ) from exc

    def _selected_indices(self) -> List[int]:
        rows = {index.row() for index in self._table.selectedIndexes()}
        return [
            self._row_indices[row] for row in sorted(rows) if row < len(self._row_indices)
        ]

    def bulk_adjust(self) -> None:
        indices = self._selected_indices()
        field_id = self._bulk_field.currentData()
        if not indices or not field_id:
            QMessageBox.information(self, "Bulk edit", "Select some players first.")
            return
        try:
            changed = self.editor.bulk_adjust(
                indices, field_id, self._bulk_delta.value()
            )
        except (ValueError, KeyError, RuntimeError) as exc:
            QMessageBox.warning(self, "Bulk edit", str(exc))
            return
        self.refresh_table()
        self.state.status(f"Adjusted {changed} player(s).", 4000)

    def bulk_set(self) -> None:
        indices = self._selected_indices()
        field_id = self._bulk_field.currentData()
        if not indices or not field_id:
            QMessageBox.information(self, "Bulk edit", "Select some players first.")
            return
        value = self._bulk_value.value()
        field = self.editor.table.field(field_id)
        if field is not None and not field.data_type.is_float:
            value = int(value)
        try:
            changed = self.editor.bulk_set(indices, field_id, value)
        except (ValueError, KeyError, RuntimeError) as exc:
            QMessageBox.warning(self, "Bulk edit", str(exc))
            return
        self.refresh_table()
        self.state.status(f"Set {changed} player(s).", 4000)

    def move_to_team(self) -> None:
        indices = self._selected_indices()
        if not indices:
            QMessageBox.information(self, "Move players", "Select some players first.")
            return
        if self.editor.table is None or self.editor.table.field("team") is None:
            QMessageBox.information(
                self,
                "Move players",
                "This ROM's player records do not carry a team field, so "
                "players cannot be reassigned.",
            )
            return
        labels = (
            self.teams.team_labels()
            if self.teams.availability()
            else [str(i) for i in range(256)]
        )
        from PySide6.QtWidgets import QInputDialog

        choice, ok = QInputDialog.getItem(
            self, "Move players", "Move to team:", labels, 0, False
        )
        if not ok:
            return
        team_index = labels.index(choice)
        try:
            with self.state.rom.undo.transaction(
                f"Move {len(indices)} player(s) to team #{team_index}"
            ):
                for index in indices:
                    self.editor.move_to_team(index, team_index)
        except (ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Move players", str(exc))
            return
        self.refresh_table()
        self.state.status(f"Moved {len(indices)} player(s).", 4000)

    def revert_selected(self) -> None:
        indices = self._selected_indices()
        table = self.editor.table
        if not indices or table is None:
            return
        with self.state.rom.undo.transaction(
            f"Revert {len(indices)} player record(s) to the original ROM"
        ):
            for index in indices:
                self.state.rom.revert_range(
                    table.record_offset(index), table.record_size
                )
        self.refresh_table()
        self.state.status(f"Reverted {len(indices)} player(s).", 4000)

    # -- CSV ---------------------------------------------------------------

    def export_csv(self) -> None:
        if not self.editor.availability():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export roster", "roster.csv", "CSV (*.csv)"
        )
        if path:
            self.editor.export_csv(path)
            self.state.status(f"Exported to {path}", 5000)

    def import_csv(self) -> None:
        if not self.editor.availability():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import roster", "", "CSV (*.csv)")
        if not path:
            return
        try:
            changed = self.editor.import_csv(path)
        except (ValueError, OSError, RuntimeError) as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
            return
        self.refresh_table()
        self.state.status(f"Updated {changed} player record(s).", 5000)
