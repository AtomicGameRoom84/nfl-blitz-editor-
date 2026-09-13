"""Create or edit an address bookmark."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
)

from core.bookmarks import CONFIDENCE_LEVELS, DEFAULT_CATEGORIES, Bookmark
from core.datatypes import COMMON_TYPES, Endian, parse_number


class BookmarkDialog(QDialog):
    """Form for one :class:`~core.bookmarks.Bookmark`."""

    def __init__(self, bookmark: Bookmark, parent=None, title: str = "Bookmark") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(440)
        self._bookmark = bookmark

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self._name = QLineEdit(bookmark.name)
        self._address = QLineEdit(bookmark.address_hex)
        self._address.setToolTip("Decimal, or hexadecimal with a 0x or $ prefix.")

        self._type = QComboBox()
        for data_type in COMMON_TYPES:
            self._type.addItem(f"{data_type.value} — {data_type.label}", data_type)
        index = self._type.findData(bookmark.data_type)
        self._type.setCurrentIndex(max(0, index))

        self._endian = QComboBox()
        for endian in Endian:
            self._endian.addItem(endian.label, endian)
        self._endian.setCurrentIndex(0 if bookmark.endian is Endian.BIG else 1)

        self._category = QComboBox()
        self._category.setEditable(True)
        self._category.addItems(list(DEFAULT_CATEGORIES))
        self._category.setCurrentText(bookmark.category or "Uncategorised")

        self._confidence = QComboBox()
        self._confidence.addItems(list(CONFIDENCE_LEVELS))
        self._confidence.setCurrentText(bookmark.confidence)

        self._default = self._spin(bookmark.default_value)
        self._minimum = self._spin(bookmark.minimum)
        self._maximum = self._spin(bookmark.maximum)

        self._tags = QLineEdit(", ".join(bookmark.tags))
        self._notes = QPlainTextEdit(bookmark.notes)
        self._notes.setMinimumHeight(90)
        self._notes.setPlaceholderText(
            "What does this address appear to do? How was it found? What have "
            "you tested?"
        )

        form.addRow("Name", self._name)
        form.addRow("Address", self._address)
        form.addRow("Data type", self._type)
        form.addRow("Endianness", self._endian)
        form.addRow("Category", self._category)
        form.addRow("Confidence", self._confidence)
        form.addRow("Default value", self._default)
        form.addRow("Minimum", self._minimum)
        form.addRow("Maximum", self._maximum)
        form.addRow("Tags", self._tags)
        form.addRow("Notes", self._notes)
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
        box.setMinimum(-1e12)
        box.setValue(value if value is not None else -1e12)
        return box

    @staticmethod
    def _spin_value(box: QDoubleSpinBox) -> Optional[float]:
        value = box.value()
        return None if value <= -1e12 else value

    def result_bookmark(self) -> Bookmark:
        """The edited bookmark.  Raises ``ValueError`` if the address is invalid."""
        bookmark = self._bookmark
        bookmark.name = self._name.text().strip() or "Unnamed"
        bookmark.address = parse_number(self._address.text())
        bookmark.data_type = self._type.currentData()
        bookmark.endian = self._endian.currentData()
        bookmark.category = self._category.currentText().strip() or "Uncategorised"
        bookmark.confidence = self._confidence.currentText()
        bookmark.default_value = self._spin_value(self._default)
        bookmark.minimum = self._spin_value(self._minimum)
        bookmark.maximum = self._spin_value(self._maximum)
        bookmark.tags = [t.strip() for t in self._tags.text().split(",") if t.strip()]
        bookmark.notes = self._notes.toPlainText().strip()
        return bookmark
