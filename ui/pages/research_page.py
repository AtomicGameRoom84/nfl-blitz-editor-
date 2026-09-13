"""Research Mode: record what you changed and what happened."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.datatypes import COMMON_TYPES, parse_number
from tools.research import OUTCOMES, Experiment
from ui.pages.base_page import Page, hint

COLUMNS = ("Name", "Address", "Original", "Modified", "Outcome", "Result", "Updated")


class ExperimentDialog(QDialog):
    """Form for one :class:`~tools.research.Experiment`."""

    def __init__(self, experiment: Experiment, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Experiment")
        self.setMinimumWidth(470)
        self._experiment = experiment

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._name = QLineEdit(experiment.name)
        self._address = QLineEdit(
            experiment.address_hex if experiment.address is not None else ""
        )
        self._address.setPlaceholderText("0x001234 (optional)")

        self._type = QComboBox()
        for data_type in COMMON_TYPES:
            self._type.addItem(data_type.value, data_type)
        self._type.setCurrentIndex(max(0, self._type.findData(experiment.data_type)))

        self._original = self._spin(experiment.original_value)
        self._modified = self._spin(experiment.modified_value)

        self._outcome = QComboBox()
        self._outcome.addItems(list(OUTCOMES))
        self._outcome.setCurrentText(experiment.outcome)

        self._hypothesis = QPlainTextEdit(experiment.hypothesis)
        self._hypothesis.setMaximumHeight(70)
        self._hypothesis.setPlaceholderText("What do you expect this to change?")
        self._result = QPlainTextEdit(experiment.result)
        self._result.setMaximumHeight(70)
        self._result.setPlaceholderText("What actually happened in game?")
        self._notes = QPlainTextEdit(experiment.notes)
        self._notes.setMaximumHeight(70)
        self._tags = QLineEdit(", ".join(experiment.tags))

        form.addRow("Name", self._name)
        form.addRow("Address", self._address)
        form.addRow("Data type", self._type)
        form.addRow("Original value", self._original)
        form.addRow("Modified value", self._modified)
        form.addRow("Outcome", self._outcome)
        form.addRow("Hypothesis", self._hypothesis)
        form.addRow("Result", self._result)
        form.addRow("Notes", self._notes)
        form.addRow("Tags", self._tags)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _spin(value: Optional[float]) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setDecimals(4)
        box.setRange(-1e12, 1e12)
        box.setSpecialValueText("(none)")
        box.setValue(value if value is not None else -1e12)
        return box

    @staticmethod
    def _spin_value(box: QDoubleSpinBox) -> Optional[float]:
        return None if box.value() <= -1e12 else box.value()

    def result_experiment(self) -> Experiment:
        experiment = self._experiment
        experiment.name = self._name.text().strip() or "Untitled experiment"
        raw_address = self._address.text().strip()
        experiment.address = parse_number(raw_address) if raw_address else None
        experiment.data_type = self._type.currentData()
        experiment.original_value = self._spin_value(self._original)
        experiment.modified_value = self._spin_value(self._modified)
        experiment.outcome = self._outcome.currentText()
        experiment.hypothesis = self._hypothesis.toPlainText().strip()
        experiment.result = self._result.toPlainText().strip()
        experiment.notes = self._notes.toPlainText().strip()
        experiment.tags = [t.strip() for t in self._tags.text().split(",") if t.strip()]
        return experiment


class ResearchPage(Page):
    page_key = "research"
    page_title = "Research Mode"
    page_subtitle = (
        "A lab notebook for reverse engineering: what you changed, what you "
        "expected, and what actually happened."
    )
    requires_rom = False

    def build(self) -> None:
        filters = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter experiments…")
        self._search.textChanged.connect(self.refresh)
        filters.addWidget(self._search, 1)
        self._outcome_filter = QComboBox()
        self._outcome_filter.addItem("All outcomes", None)
        for outcome in OUTCOMES:
            self._outcome_filter.addItem(outcome, outcome)
        self._outcome_filter.activated.connect(lambda _: self.refresh())
        filters.addWidget(self._outcome_filter)
        self.body.addLayout(filters)

        self._table = QTableWidget(0, len(COLUMNS))
        self._table.setHorizontalHeaderLabels(list(COLUMNS))
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(
            len(COLUMNS) - 2, QHeaderView.Stretch
        )
        self._table.doubleClicked.connect(lambda _: self.edit_selected())
        self.body.addWidget(self._table, 1)

        actions = QHBoxLayout()
        for label, slot, primary in (
            ("New experiment…", self.add_experiment, True),
            ("Edit…", self.edit_selected, False),
            ("Delete", self.delete_selected, False),
            ("Export Markdown…", self.export_markdown, False),
            ("Export CSV…", self.export_csv, False),
            ("Import JSON…", self.import_json, False),
        ):
            button = QPushButton(label)
            if primary:
                button.setObjectName("Primary")
            button.clicked.connect(slot)
            actions.addWidget(button)
        actions.addStretch(1)
        self._stats = QLabel("")
        self._stats.setObjectName("Hint")
        actions.addWidget(self._stats)
        self.body.addLayout(actions)

        self.body.addWidget(
            hint(
                "A useful experiment changes exactly one value. Record the "
                "original so you can put it back, and write down 'no effect' "
                "results too — they are what stops the next person repeating "
                "the same test."
            )
        )

        self.state.researchChanged.connect(self.refresh)
        self.refresh()

    # -- data --------------------------------------------------------------

    def on_activated(self) -> None:
        self.refresh()

    def _visible(self) -> List[Experiment]:
        return self.state.research.query(
            text=self._search.text(), outcome=self._outcome_filter.currentData()
        )

    def refresh(self) -> None:
        experiments = self._visible()
        self._table.setRowCount(len(experiments))
        for row, experiment in enumerate(experiments):
            cells = (
                experiment.name,
                experiment.address_hex,
                "—" if experiment.original_value is None else f"{experiment.original_value:g}",
                "—" if experiment.modified_value is None else f"{experiment.modified_value:g}",
                experiment.outcome,
                experiment.result.replace("\n", " ")[:120],
                experiment.updated[:16].replace("T", " "),
            )
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column == 0:
                    item.setData(Qt.UserRole, experiment.id)
                self._table.setItem(row, column, item)
        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setSectionResizeMode(
            len(COLUMNS) - 2, QHeaderView.Stretch
        )
        stats = self.state.research.stats()
        self._stats.setText(
            f"{stats['total']} experiment(s) — "
            f"{stats.get('confirmed', 0)} confirmed, "
            f"{stats.get('untested', 0)} untested"
        )

    def _selected(self) -> List[Experiment]:
        rows = {index.row() for index in self._table.selectedIndexes()}
        found = []
        for row in sorted(rows):
            item = self._table.item(row, 0)
            if item is None:
                continue
            experiment = self.state.research.get(item.data(Qt.UserRole))
            if experiment is not None:
                found.append(experiment)
        return found

    # -- actions -----------------------------------------------------------

    def add_experiment(self) -> None:
        experiment = Experiment(
            name="New experiment",
            rom_key=self.state.rom_key,
            rom_label=self.state.rom_label,
        )
        dialog = ExperimentDialog(experiment, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.state.research.add(dialog.result_experiment())
        except ValueError as exc:
            QMessageBox.warning(self, "Experiment", str(exc))
            return
        self.state.research.save()

    def edit_selected(self) -> None:
        selected = self._selected()
        if not selected:
            return
        dialog = ExperimentDialog(selected[0], self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.state.research.update(dialog.result_experiment())
        except ValueError as exc:
            QMessageBox.warning(self, "Experiment", str(exc))
            return
        self.state.research.save()

    def delete_selected(self) -> None:
        selected = self._selected()
        if not selected:
            return
        answer = QMessageBox.question(
            self,
            "Delete experiments",
            f"Delete {len(selected)} experiment(s)?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        for experiment in selected:
            self.state.research.remove(experiment.id)
        self.state.research.save()

    def export_markdown(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export research log", "research-log.md", "Markdown (*.md)"
        )
        if path:
            self.state.research.export_markdown(path)
            self.state.status(f"Exported to {path}", 5000)

    def export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export research log", "research-log.csv", "CSV (*.csv)"
        )
        if path:
            self.state.research.export_csv(path)
            self.state.status(f"Exported to {path}", 5000)

    def import_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import research log", "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            added = self.state.research.import_json(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
            return
        self.state.research.save()
        self.state.status(f"Imported {added} experiment(s).", 5000)
