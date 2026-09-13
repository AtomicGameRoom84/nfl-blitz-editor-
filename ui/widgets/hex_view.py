"""A virtualised hex editor widget.

Painting is done by hand rather than with a model/view because a ROM is
megabytes long: only the rows currently on screen are ever formatted, so
scrolling a 64 MiB image costs the same as scrolling a 512 KiB one.

Features
--------
* Address / hex / ASCII columns with selectable, navigable cursor.
* Nibble-accurate typing in the hex column, character typing in ASCII.
* Byte-level highlighting for modified bytes, bookmarks and search hits.
* Every edit is routed through :class:`~core.rom_manager.ROMManager`, so it
  lands on the shared undo stack like any other modification.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QResizeEvent,
)
from PySide6.QtWidgets import QAbstractScrollArea, QApplication

from core.rom_manager import ROMManager
from ui import theme


class Pane(Enum):
    HEX = "hex"
    ASCII = "ascii"


#: Highlight roles, painted in this order (later wins).
HIGHLIGHT_ROLES = ("modified", "bookmark", "match")


class HexView(QAbstractScrollArea):
    """Scrollable hex/ASCII view and editor over a :class:`ROMManager`."""

    cursorMoved = Signal(int)
    selectionChanged = Signal(int, int)
    editApplied = Signal(int, int)

    def __init__(self, rom: ROMManager, parent=None) -> None:
        super().__init__(parent)
        self.rom = rom
        self._bytes_per_row = 16
        self._uppercase = True
        self._cursor = 0
        self._anchor = 0
        self._pane = Pane.HEX
        self._nibble = 0
        self._read_only = False
        self._highlights: Dict[str, List[Tuple[int, int]]] = {
            role: [] for role in HIGHLIGHT_ROLES
        }
        #: Resolved lazily so a change of theme or font re-measures.
        self._char_width = 8
        self._row_height = 16
        self._ascent = 12

        self.setFont(theme.monospace_font(12))
        self.viewport().setCursor(Qt.IBeamCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.viewport().setAttribute(Qt.WA_OpaquePaintEvent, True)
        self._update_metrics()

    # -- configuration -----------------------------------------------------

    @property
    def bytes_per_row(self) -> int:
        return self._bytes_per_row

    def set_bytes_per_row(self, count: int) -> None:
        self._bytes_per_row = max(1, int(count))
        self._update_metrics()
        self.viewport().update()

    def set_font_size(self, points: int) -> None:
        self.setFont(theme.monospace_font(max(6, int(points))))
        self._update_metrics()
        self.viewport().update()

    def set_uppercase(self, enabled: bool) -> None:
        self._uppercase = bool(enabled)
        self.viewport().update()

    def set_read_only(self, enabled: bool) -> None:
        self._read_only = bool(enabled)

    @property
    def read_only(self) -> bool:
        return self._read_only

    # -- data --------------------------------------------------------------

    @property
    def length(self) -> int:
        return self.rom.size if self.rom.is_loaded else 0

    def refresh(self) -> None:
        """Re-measure and repaint; call after the ROM is loaded or replaced."""
        self._cursor = min(self._cursor, max(0, self.length - 1))
        self._anchor = min(self._anchor, max(0, self.length - 1))
        self._update_metrics()
        self.viewport().update()

    # -- highlights --------------------------------------------------------

    def set_highlight(self, role: str, ranges: Sequence[Tuple[int, int]]) -> None:
        """Replace the ranges painted for one highlight role."""
        if role not in self._highlights:
            raise KeyError(f"unknown highlight role {role!r}")
        self._highlights[role] = [(int(a), int(b)) for a, b in ranges]
        self.viewport().update()

    def clear_highlight(self, role: str) -> None:
        self.set_highlight(role, [])

    def _highlight_at(self, offset: int) -> Optional[str]:
        for role in HIGHLIGHT_ROLES:
            for start, end in self._highlights[role]:
                if start <= offset < end:
                    return role
        return None

    # -- geometry ----------------------------------------------------------

    def _update_metrics(self) -> None:
        metrics = QFontMetrics(self.font())
        self._char_width = max(1, metrics.horizontalAdvance("0"))
        self._row_height = metrics.height() + 2
        self._ascent = metrics.ascent()

        rows = self.total_rows()
        visible = self.visible_rows()
        bar = self.verticalScrollBar()
        bar.setRange(0, max(0, rows - visible))
        bar.setPageStep(max(1, visible))
        bar.setSingleStep(1)

        horizontal = self.horizontalScrollBar()
        overflow = max(0, self._total_width() - self.viewport().width())
        horizontal.setRange(0, overflow)
        horizontal.setPageStep(max(1, self.viewport().width()))

    def total_rows(self) -> int:
        if self.length == 0:
            return 0
        return (self.length + self._bytes_per_row - 1) // self._bytes_per_row

    def visible_rows(self) -> int:
        return max(1, self.viewport().height() // self._row_height)

    def _address_width(self) -> int:
        return self._char_width * 10  # 8 hex digits + two spaces

    def _hex_x(self, column: int) -> int:
        """Left edge of the hex cell for ``column`` within a row."""
        return (
            self._address_width()
            + column * 3 * self._char_width
            + (column // 8) * self._char_width
        )

    def _hex_width(self) -> int:
        last = self._bytes_per_row - 1
        return self._hex_x(last) + 2 * self._char_width - self._address_width()

    def _ascii_x(self, column: int = 0) -> int:
        return (
            self._address_width()
            + self._hex_width()
            + 2 * self._char_width
            + column * self._char_width
        )

    def _total_width(self) -> int:
        return self._ascii_x(self._bytes_per_row) + self._char_width

    def first_visible_offset(self) -> int:
        return self.verticalScrollBar().value() * self._bytes_per_row

    # -- cursor ------------------------------------------------------------

    @property
    def cursor_offset(self) -> int:
        return self._cursor

    @property
    def selection(self) -> Tuple[int, int]:
        """Half-open ``(start, end)`` selection range."""
        start, end = sorted((self._anchor, self._cursor))
        return start, end + 1

    def has_selection(self) -> bool:
        return self._anchor != self._cursor

    def set_cursor(self, offset: int, extend: bool = False, scroll: bool = True) -> None:
        if self.length == 0:
            return
        offset = max(0, min(int(offset), self.length - 1))
        self._cursor = offset
        if not extend:
            self._anchor = offset
        self._nibble = 0
        if scroll:
            self.ensure_visible(offset)
        self.viewport().update()
        self.cursorMoved.emit(offset)
        start, end = self.selection
        self.selectionChanged.emit(start, end)

    def select_range(self, start: int, end: int) -> None:
        """Select ``[start, end)`` and scroll it into view."""
        if self.length == 0:
            return
        start = max(0, min(start, self.length - 1))
        end = max(start + 1, min(end, self.length))
        # Anchor at the far end so the cursor -- and therefore the data
        # inspector -- sits on the first byte of the range, which is the one
        # the caller cared about.
        self._anchor = end - 1
        self._cursor = start
        self.ensure_visible(start)
        self.viewport().update()
        self.cursorMoved.emit(start)
        self.selectionChanged.emit(start, end)

    def ensure_visible(self, offset: int) -> None:
        row = offset // self._bytes_per_row
        bar = self.verticalScrollBar()
        if row < bar.value():
            bar.setValue(row)
        elif row >= bar.value() + self.visible_rows():
            bar.setValue(row - self.visible_rows() + 1)

    # -- painting ----------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self.viewport())
        painter.setFont(self.font())
        painter.fillRect(event.rect(), theme.color("surface"))

        if self.length == 0:
            painter.setPen(theme.color("text_faint"))
            painter.drawText(
                self.viewport().rect(),
                Qt.AlignCenter,
                "No ROM loaded.\nFile → Open ROM…",
            )
            return

        scroll_x = self.horizontalScrollBar().value()
        first_row = self.verticalScrollBar().value()
        rows = min(self.visible_rows() + 1, self.total_rows() - first_row)

        selection_start, selection_end = self.selection
        selected = self.has_selection()
        data = self.rom.data
        original = self.rom.original

        text_color = theme.color("text")
        dim_color = theme.color("text_dim")
        faint_color = theme.color("text_faint")
        address_color = theme.color("info")
        selection_color = theme.color("selection")
        cursor_color = theme.color("accent")
        role_colors = {
            "modified": theme.color("modified"),
            "bookmark": theme.color("bookmark"),
            "match": theme.color("match"),
        }

        for visible_row in range(rows):
            row = first_row + visible_row
            row_offset = row * self._bytes_per_row
            y = visible_row * self._row_height
            baseline = y + self._ascent

            painter.setPen(address_color)
            painter.drawText(
                -scroll_x, baseline, self._format_hex(row_offset, 8)
            )

            for column in range(self._bytes_per_row):
                offset = row_offset + column
                if offset >= self.length:
                    break
                value = data[offset]
                hex_x = self._hex_x(column) - scroll_x
                ascii_x = self._ascii_x(column) - scroll_x

                in_selection = selected and selection_start <= offset < selection_end
                role = self._highlight_at(offset)
                is_modified = offset < len(original) and original[offset] != value

                # Cell backgrounds.
                if in_selection:
                    painter.fillRect(
                        QRect(hex_x - 1, y, 2 * self._char_width + 2, self._row_height),
                        selection_color,
                    )
                    painter.fillRect(
                        QRect(ascii_x, y, self._char_width, self._row_height),
                        selection_color,
                    )
                elif role is not None:
                    tint = QColor(role_colors[role])
                    tint.setAlpha(60)
                    painter.fillRect(
                        QRect(hex_x - 1, y, 2 * self._char_width + 2, self._row_height),
                        tint,
                    )
                    painter.fillRect(
                        QRect(ascii_x, y, self._char_width, self._row_height), tint
                    )

                if is_modified:
                    painter.setPen(role_colors["modified"])
                elif role == "bookmark":
                    painter.setPen(role_colors["bookmark"])
                elif role == "match":
                    painter.setPen(role_colors["match"])
                elif value == 0:
                    painter.setPen(faint_color)
                else:
                    painter.setPen(text_color)

                painter.drawText(hex_x, baseline, self._format_hex(value, 2))

                printable = 0x20 <= value < 0x7F
                painter.setPen(
                    painter.pen().color() if printable else dim_color
                )
                painter.drawText(
                    ascii_x, baseline, chr(value) if printable else "."
                )

            # Cursor caret.
            if row_offset <= self._cursor < row_offset + self._bytes_per_row:
                column = self._cursor - row_offset
                painter.setPen(cursor_color)
                if self._pane is Pane.HEX:
                    caret_x = self._hex_x(column) - scroll_x + self._nibble * self._char_width
                    width = self._char_width
                else:
                    caret_x = self._ascii_x(column) - scroll_x
                    width = self._char_width
                painter.drawRect(QRect(caret_x - 1, y, width + 1, self._row_height - 1))

        # Column separators.
        painter.setPen(theme.color("border"))
        separator_x = self._address_width() - self._char_width // 2 - scroll_x
        painter.drawLine(separator_x, 0, separator_x, self.viewport().height())
        separator_x = self._ascii_x(0) - self._char_width - scroll_x
        painter.drawLine(separator_x, 0, separator_x, self.viewport().height())

    def _format_hex(self, value: int, width: int) -> str:
        text = f"{value:0{width}x}"
        return text.upper() if self._uppercase else text

    # -- events ------------------------------------------------------------

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_metrics()

    def _offset_at(self, x: int, y: int) -> Optional[Tuple[int, Pane]]:
        x += self.horizontalScrollBar().value()
        row = self.verticalScrollBar().value() + y // self._row_height
        if row < 0 or row >= self.total_rows():
            return None
        ascii_start = self._ascii_x(0) - self._char_width
        if x >= ascii_start:
            column = (x - self._ascii_x(0)) // self._char_width
            pane = Pane.ASCII
        else:
            relative = x - self._address_width()
            if relative < 0:
                column = 0
            else:
                # Undo the extra gap inserted every eight bytes.
                group = relative // (25 * self._char_width)
                column = (relative - group * self._char_width) // (3 * self._char_width)
            pane = Pane.HEX
        column = max(0, min(int(column), self._bytes_per_row - 1))
        offset = row * self._bytes_per_row + column
        if offset >= self.length:
            offset = self.length - 1
        return offset, pane

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.length == 0:
            return
        hit = self._offset_at(event.position().x(), event.position().y())
        if hit is None:
            return
        offset, pane = hit
        self._pane = pane
        self.set_cursor(offset, extend=bool(event.modifiers() & Qt.ShiftModifier), scroll=False)
        self.setFocus()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not (event.buttons() & Qt.LeftButton) or self.length == 0:
            return
        hit = self._offset_at(event.position().x(), event.position().y())
        if hit is not None:
            self.set_cursor(hit[0], extend=True, scroll=False)

    def wheelEvent(self, event) -> None:
        super().wheelEvent(event)
        self.viewport().update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self.length == 0:
            return super().keyPressEvent(event)

        key = event.key()
        extend = bool(event.modifiers() & Qt.ShiftModifier)
        control = bool(event.modifiers() & Qt.ControlModifier)
        per_row = self._bytes_per_row

        if key == Qt.Key_Tab:
            self._pane = Pane.ASCII if self._pane is Pane.HEX else Pane.HEX
            self._nibble = 0
            self.viewport().update()
            return
        if control and key == Qt.Key_C:
            self.copy_selection()
            return
        if control and key == Qt.Key_A:
            self.select_range(0, self.length)
            return

        moves = {
            Qt.Key_Left: -1,
            Qt.Key_Right: 1,
            Qt.Key_Up: -per_row,
            Qt.Key_Down: per_row,
            Qt.Key_PageUp: -per_row * self.visible_rows(),
            Qt.Key_PageDown: per_row * self.visible_rows(),
        }
        if key in moves:
            self.set_cursor(self._cursor + moves[key], extend=extend)
            return
        if key == Qt.Key_Home:
            target = 0 if control else self._cursor - (self._cursor % per_row)
            self.set_cursor(target, extend=extend)
            return
        if key == Qt.Key_End:
            target = (
                self.length - 1
                if control
                else min(self.length - 1, self._cursor - (self._cursor % per_row) + per_row - 1)
            )
            self.set_cursor(target, extend=extend)
            return

        if self._read_only or not event.text():
            return super().keyPressEvent(event)

        text = event.text()
        if self._pane is Pane.HEX:
            if text.lower() in "0123456789abcdef":
                self._type_nibble(int(text, 16))
            return
        character = text[0]
        if 0x20 <= ord(character) < 0x7F:
            self._write_byte(self._cursor, ord(character))
            self.set_cursor(min(self._cursor + 1, self.length - 1))

    # -- editing -----------------------------------------------------------

    def _type_nibble(self, nibble: int) -> None:
        current = self.rom.data[self._cursor]
        if self._nibble == 0:
            value = (nibble << 4) | (current & 0x0F)
        else:
            value = (current & 0xF0) | nibble
        self._write_byte(self._cursor, value)
        if self._nibble == 0:
            self._nibble = 1
            self.viewport().update()
        else:
            self._nibble = 0
            if self._cursor + 1 < self.length:
                self.set_cursor(self._cursor + 1)
            else:
                self.viewport().update()

    def _write_byte(self, offset: int, value: int) -> None:
        command = self.rom.write_bytes(
            offset, bytes([value & 0xFF]), f"Edit byte at 0x{offset:06X}"
        )
        if command is not None:
            self.editApplied.emit(offset, 1)
        self.viewport().update()

    def fill_selection(self, value: int) -> int:
        """Set every byte of the selection to ``value``.  Returns bytes written."""
        start, end = self.selection
        if self._read_only or end <= start:
            return 0
        payload = bytes([value & 0xFF]) * (end - start)
        command = self.rom.write_bytes(
            start, payload, f"Fill 0x{start:06X}..0x{end:06X} with {value:02X}"
        )
        self.viewport().update()
        return (end - start) if command is not None else 0

    def paste_bytes(self, payload: bytes) -> int:
        """Write ``payload`` at the cursor, clipped to the end of the ROM."""
        if self._read_only or not payload:
            return 0
        room = self.length - self._cursor
        payload = payload[:room]
        command = self.rom.write_bytes(
            self._cursor, payload, f"Paste {len(payload)} byte(s) at 0x{self._cursor:06X}"
        )
        self.viewport().update()
        return len(payload) if command is not None else 0

    def copy_selection(self) -> str:
        """Copy the selection to the clipboard as a hex string."""
        start, end = self.selection
        payload = bytes(self.rom.data[start:end])
        text = payload.hex(" ").upper()
        QApplication.clipboard().setText(text)
        return text
