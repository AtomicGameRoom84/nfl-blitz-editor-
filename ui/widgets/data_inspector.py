"""Decodes the bytes under the hex cursor as every plausible type.

Half of ROM research is "what *is* this?".  Showing one address as an 8-,
16- and 32-bit integer in both byte orders, as a float, and as text answers
that question without the user reaching for a calculator.
"""

from __future__ import annotations

import struct
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout

from core.datatypes import DataType, Endian
from core.rom_manager import ROMManager
from ui import theme

#: Rows shown, in display order.
ROWS = (
    ("u8", DataType.U8, Endian.BIG),
    ("s8", DataType.S8, Endian.BIG),
    ("u16 BE", DataType.U16, Endian.BIG),
    ("u16 LE", DataType.U16, Endian.LITTLE),
    ("s16 BE", DataType.S16, Endian.BIG),
    ("u32 BE", DataType.U32, Endian.BIG),
    ("u32 LE", DataType.U32, Endian.LITTLE),
    ("s32 BE", DataType.S32, Endian.BIG),
    ("f32 BE", DataType.F32, Endian.BIG),
    ("f32 LE", DataType.F32, Endian.LITTLE),
)


class DataInspector(QFrame):
    """A live read-out of the value under the cursor."""

    def __init__(self, rom: ROMManager, parent=None) -> None:
        super().__init__(parent)
        self.rom = rom
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        heading = QLabel("DATA INSPECTOR")
        heading.setObjectName("SectionHeading")
        layout.addWidget(heading)

        self._address = QLabel("—")
        self._address.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._address)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(3)
        grid.setColumnStretch(1, 1)
        self._values = {}
        for row, (label_text, _, _) in enumerate(ROWS):
            label = QLabel(label_text)
            label.setObjectName("Hint")
            value = QLabel("—")
            value.setFont(theme.monospace_font(11))
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(label, row, 0, Qt.AlignRight)
            grid.addWidget(value, row, 1)
            self._values[label_text] = value
        layout.addLayout(grid)

        self._binary = QLabel("—")
        self._binary.setFont(theme.monospace_font(11))
        self._binary.setObjectName("Hint")
        layout.addWidget(self._binary)

        self._text = QLabel("—")
        self._text.setWordWrap(True)
        self._text.setFont(theme.monospace_font(11))
        layout.addWidget(self._text)

        self._original = QLabel("")
        self._original.setWordWrap(True)
        self._original.setObjectName("Hint")
        layout.addWidget(self._original)

    def update_for(self, offset: Optional[int]) -> None:
        """Refresh every row for ``offset``, blanking what does not fit."""
        if offset is None or not self.rom.is_loaded:
            self._address.setText("—")
            for value in self._values.values():
                value.setText("—")
            self._binary.setText("")
            self._text.setText("")
            self._original.setText("")
            return

        data = self.rom.data
        self._address.setText(f"Address  0x{offset:08X}   ({offset:,})")

        for label_text, data_type, endian in ROWS:
            end = offset + data_type.size
            if end > len(data):
                self._values[label_text].setText("—")
                continue
            chunk = bytes(data[offset:end])
            try:
                value = data_type.decode(chunk, endian)
            except (ValueError, struct.error):
                self._values[label_text].setText("—")
                continue
            if data_type.is_float:
                self._values[label_text].setText(f"{value:.6g}")
            else:
                width = data_type.size * 2
                self._values[label_text].setText(f"{value}   0x{value & ((1 << (width * 4)) - 1):0{width}X}")

        self._binary.setText(f"bits  {data[offset]:08b}")

        preview = bytes(data[offset : offset + 24])
        printable = "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in preview)
        self._text.setText(f"text  {printable}")

        original = self.rom.original
        if offset < len(original) and original[offset] != data[offset]:
            self._original.setText(
                f"Modified — originally 0x{original[offset]:02X} "
                f"({original[offset]})"
            )
            self._original.setStyleSheet(f"color: {theme.COLORS['modified']};")
        else:
            self._original.setText("")
