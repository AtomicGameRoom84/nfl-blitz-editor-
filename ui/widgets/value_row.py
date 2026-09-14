"""One editable gameplay constant: label, slider, spin box and provenance.

Rows are built from a :class:`~core.address_db.ValueEntry`, so what the user
sees -- range, units, default, how trustworthy the address is -- comes
entirely from the game definition.  An entry whose address has not been
discovered still gets a row, greyed out and labelled, rather than being
hidden: the suite shows what it is looking for as well as what it knows.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core.address_db import ValueEntry
from editors.gameplay_editor import EntryState
from ui import theme

#: Badge colour per confidence level.
CONFIDENCE_COLORS = {
    "undiscovered": "text_faint",
    "guess": "danger",
    "experimental": "warning",
    "tested": "info",
    "confirmed": "success",
}

#: Sliders are integral, so fractional steps are scaled by this factor.
SLIDER_PRECISION = 100


class ValueRow(QWidget):
    """A single gameplay value control."""

    def __init__(
        self,
        entry: ValueEntry,
        on_change: Callable[[ValueEntry, float], None],
        on_restore: Callable[[ValueEntry], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.entry = entry
        self._on_change = on_change
        self._on_restore = on_restore
        self._updating = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(10)

        self._name = QLabel(entry.name)
        self._name.setMinimumWidth(230)
        top.addWidget(self._name)

        low, high = entry.effective_bounds()
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setMinimum(int(low * SLIDER_PRECISION))
        self._slider.setMaximum(int(high * SLIDER_PRECISION))
        self._slider.valueChanged.connect(self._slider_moved)
        top.addWidget(self._slider, 1)

        self._spin = QDoubleSpinBox()
        self._spin.setDecimals(4 if entry.data_type.is_float or entry.scale != 1 else 0)
        self._spin.setRange(low * entry.scale, high * entry.scale)
        self._spin.setSingleStep(entry.step * entry.scale)
        self._spin.setMaximumWidth(130)
        if entry.unit:
            self._spin.setSuffix(f" {entry.unit}")
        self._spin.valueChanged.connect(self._spin_changed)
        top.addWidget(self._spin)

        self._restore = QPushButton("Restore")
        self._restore.setMaximumWidth(80)
        self._restore.setToolTip("Restore this value's default")
        self._restore.clicked.connect(lambda: self._on_restore(self.entry))
        top.addWidget(self._restore)
        outer.addLayout(top)

        self._meta = QLabel("")
        self._meta.setObjectName("Hint")
        self._meta.setWordWrap(True)
        outer.addWidget(self._meta)

    # -- state -------------------------------------------------------------

    def apply_state(self, state: EntryState) -> None:
        """Refresh the row from a freshly read :class:`EntryState`."""
        entry = state.entry
        self._updating = True
        try:
            enabled = state.available
            self._slider.setEnabled(enabled)
            self._spin.setEnabled(enabled)
            self._restore.setEnabled(enabled and state.default_value is not None)

            if state.current is not None:
                self._spin.setValue(state.current * entry.scale)
                self._slider.setValue(int(state.current * SLIDER_PRECISION))

            badge = entry.confidence
            badge_color = theme.COLORS[CONFIDENCE_COLORS.get(badge, "text_dim")]
            parts = [
                f"<span style='color:{badge_color}'>{badge}</span>",
                f"{entry.address_hex}",
                f"{entry.data_type.value} {entry.endian.short}",
            ]
            if state.default_value is not None:
                parts.append(f"default {state.default_value:g}")
            if state.modified:
                parts.append(
                    f"<span style='color:{theme.COLORS['modified']}'>"
                    f"changed from {state.original:g}</span>"
                )
            if state.error:
                parts.append(
                    f"<span style='color:{theme.COLORS['danger']}'>{state.error}</span>"
                )
            elif not entry.is_discovered:
                parts = [
                    f"<span style='color:{theme.COLORS['text_faint']}'>"
                    "address not discovered yet — this control is inactive"
                    "</span>"
                ]
            if entry.notes and entry.is_discovered:
                parts.append(entry.notes)
            self._meta.setText("&nbsp;&nbsp;•&nbsp;&nbsp;".join(parts))

            self._name.setStyleSheet(
                "" if enabled else f"color: {theme.COLORS['text_faint']};"
            )
        finally:
            self._updating = False

    # -- signals -----------------------------------------------------------

    def _slider_moved(self, raw: int) -> None:
        if self._updating:
            return
        value = raw / SLIDER_PRECISION
        self._updating = True
        self._spin.setValue(value * self.entry.scale)
        self._updating = False
        self._on_change(self.entry, value)

    def _spin_changed(self, display_value: float) -> None:
        if self._updating:
            return
        raw = display_value / self.entry.scale if self.entry.scale else display_value
        self._updating = True
        self._slider.setValue(int(raw * SLIDER_PRECISION))
        self._updating = False
        self._on_change(self.entry, raw)
