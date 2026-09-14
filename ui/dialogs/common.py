"""Dialogs shared by several pages."""

from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.byte_order import ByteOrder
from core.datatypes import parse_number
from core.version import full_title, version_string
from tools.pointer_finder import PointerFinder
from tools.scanner import ROMScanner
from ui import theme


class TextReportDialog(QDialog):
    """Read-only monospaced report."""

    def __init__(self, title: str, lines: List[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 560)
        layout = QVBoxLayout(self)
        view = QPlainTextEdit("\n".join(lines))
        view.setReadOnly(True)
        view.setFont(theme.monospace_font(11))
        layout.addWidget(view)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class ScannerDialog(TextReportDialog):
    """Runs :class:`~tools.scanner.ROMScanner` and shows the result."""

    def __init__(self, data: bytes, parent=None) -> None:
        # Surveying a 16 MiB cartridge takes a few seconds with the window
        # unresponsive, so say so with the cursor rather than looking hung.
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            report = ROMScanner().scan(data)
        finally:
            QApplication.restoreOverrideCursor()
        super().__init__("ROM Scanner", report.lines(), parent)


class PointerFinderDialog(QDialog):
    """Search for words that could reference an address."""

    def __init__(self, data: bytes, initial_target: int = 0, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pointer Finder")
        self.resize(720, 520)
        self._data = data

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Find 32-bit words that could point at an address. Every result "
                "is a candidate, not a proven reference."
            )
        )

        row = QHBoxLayout()
        row.addWidget(QLabel("Target address"))
        self._target = QLineEdit(f"0x{initial_target:06X}")
        row.addWidget(self._target)
        row.addWidget(QLabel("Load base (optional)"))
        self._base = QLineEdit()
        self._base.setPlaceholderText("e.g. 0x80000400")
        row.addWidget(self._base)
        search = QPushButton("Search")
        search.setObjectName("Primary")
        search.clicked.connect(self.run_search)
        row.addWidget(search)
        layout.addLayout(row)

        self._status = QLabel("")
        layout.addWidget(self._status)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(
            ["Found at", "Value", "Would mean"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self._table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def run_search(self) -> None:
        try:
            target = parse_number(self._target.text())
            base = parse_number(self._base.text()) if self._base.text().strip() else None
        except ValueError as exc:
            self._status.setText(str(exc))
            return
        hits = PointerFinder(self._data).candidates_for(target, base)
        self._table.setRowCount(len(hits))
        for row, hit in enumerate(hits):
            for column, text in enumerate(
                (hit.address_hex, hit.value_hex, hit.interpretation)
            ):
                self._table.setItem(row, column, QTableWidgetItem(text))
        self._status.setText(f"{len(hits)} candidate reference(s).")


class SaveSummaryDialog(QDialog):
    """Modification summary shown before writing a new ROM file."""

    def __init__(self, summary: dict, details: List[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Modification summary")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)

        heading = QLabel("MODIFICATION SUMMARY")
        heading.setObjectName("SectionHeading")
        layout.addWidget(heading)

        for line in details:
            label = QLabel(line)
            label.setWordWrap(True)
            layout.addWidget(label)

        layout.addWidget(QLabel(""))
        order_row = QHBoxLayout()
        order_row.addWidget(QLabel("Save as"))
        self._order = QComboBox()
        for order in (ByteOrder.Z64, ByteOrder.V64, ByteOrder.N64):
            self._order.addItem(order.label, order)
        order_row.addWidget(self._order, 1)
        layout.addLayout(order_row)

        self._fix_crc = QCheckBox(
            "Recalculate the N64 boot checksum (needed for real hardware)"
        )
        self._fix_crc.setChecked(True)
        layout.addWidget(self._fix_crc)

        buttons = QDialogButtonBox()
        self._save = buttons.addButton("Save ROM", QDialogButtonBox.AcceptRole)
        self._save.setObjectName("Primary")
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def byte_order(self) -> ByteOrder:
        return self._order.currentData()

    @property
    def fix_checksum(self) -> bool:
        return self._fix_crc.isChecked()

    def set_defaults(self, order: ByteOrder, fix_checksum: bool) -> None:
        index = self._order.findData(order)
        if index >= 0:
            self._order.setCurrentIndex(index)
        self._fix_crc.setChecked(fix_checksum)


class AboutDialog(QDialog):
    """The Help -> About box."""

    TEXT = (
        "<h2>NFL Blitz Mod Suite</h2>"
        "<p><b>Version {version}</b> \u2014 an early preview. Teams and rosters "
        "for the USA cartridge are mapped and editable; gameplay constants are "
        "not yet located, and the graphics editor is not implemented.</p>"
        "<p>A ROM hacking workbench for the Nintendo 64 version of NFL Blitz.</p>"
        "<p><b>This application ships no game data and no ROM addresses that "
        "have not been verified.</b> The team, roster and graphics editors "
        "report themselves unavailable until a game definition describes where "
        "that data lives — finding it is what the comparison, search and "
        "bookmark tools are for.</p>"
        "<p>You must supply your own legally obtained cartridge dump. Share "
        "your work as an IPS or BPS patch, never as a ROM.</p>"
        "<p>Built with Python and PySide6.</p>"
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"About {full_title()}")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        label = QLabel(self.TEXT.format(version=version_string()))
        label.setWordWrap(True)
        label.setTextFormat(Qt.RichText)
        layout.addWidget(label)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
