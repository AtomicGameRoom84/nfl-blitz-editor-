"""A numeric entry for values a ``QSpinBox`` cannot hold.

Qt's spin boxes are limited to signed 32-bit range, which is not enough for
an unsigned 32-bit ROM field -- a KSEG0 pointer such as ``0x802DE3D8`` is
above ``2**31`` and a spin box would silently clamp it, corrupting the ROM.
This widget accepts decimal or hexadecimal text instead and reports invalid
input rather than guessing.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLineEdit

from core.datatypes import parse_number
from ui import theme

#: Widest range a QSpinBox can represent.
QT_INT_MIN = -(2 ** 31)
QT_INT_MAX = 2 ** 31 - 1


def fits_in_spinbox(low: float | None, high: float | None) -> bool:
    """Whether a spin box can represent the whole range."""
    if low is not None and low < QT_INT_MIN:
        return False
    if high is not None and high > QT_INT_MAX:
        return False
    return True


class NumberEdit(QLineEdit):
    """Hex/decimal entry for a wide integer field."""

    def __init__(self, hexadecimal: bool = True, parent=None) -> None:
        super().__init__(parent)
        self._hex = hexadecimal
        self._value = 0
        self.setFont(theme.monospace_font(11))
        self.setPlaceholderText("0x00000000 or a decimal number")
        self.setToolTip(
            "Accepts decimal, or hexadecimal with a 0x or $ prefix. Too wide "
            "for a spin box, so it is typed rather than stepped."
        )
        self.setValue(0)

    def setValue(self, value: int) -> None:
        self._value = int(value)
        self.setText(f"0x{self._value:08X}" if self._hex else str(self._value))

    def value(self) -> int:
        """The entered number.

        Raises ``ValueError`` when the text is not a number, so a typo is
        reported instead of being written to the ROM as zero.
        """
        return parse_number(self.text())
