"""Helpers for filling Qt tables without quadratic cost.

``QHeaderView.ResizeToContents`` re-measures every cell in a column each time
an item is inserted. On a table of a few dozen rows that is invisible; on the
480-row NFL Blitz roster it turns filling the table into an O(rows x cols)
measurement storm that takes minutes and makes the window look hung.

:func:`bulk_update` suspends the expensive machinery -- repaints, item
signals, sorting -- while a table is populated, and :func:`fit_columns` does
the one-off measurement afterwards.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional, Sequence

from PySide6.QtWidgets import QHeaderView, QTableWidget

#: Never measure more than this many rows when sizing columns; beyond it the
#: widths stop changing but the cost keeps growing.
SAMPLE_ROWS = 50


@contextmanager
def bulk_update(table: QTableWidget) -> Iterator[QTableWidget]:
    """Fill a table cheaply.

    Turns off repaints, ``itemChanged`` emissions and sorting for the
    duration, and restores whatever was set before -- including when the body
    raises, so a failed refresh cannot leave a table permanently mute.
    """
    header = table.horizontalHeader()
    previous_mode = header.sectionResizeMode(0) if header.count() else None
    was_blocked = table.signalsBlocked()
    was_sorting = table.isSortingEnabled()

    table.setUpdatesEnabled(False)
    table.blockSignals(True)
    table.setSortingEnabled(False)
    if previous_mode is not None:
        # Interactive costs nothing per insert; the real sizing happens once,
        # in fit_columns, after the rows are in.
        header.setSectionResizeMode(QHeaderView.Interactive)
    try:
        yield table
    finally:
        table.setSortingEnabled(was_sorting)
        table.blockSignals(was_blocked)
        table.setUpdatesEnabled(True)


def fit_columns(
    table: QTableWidget,
    stretch_column: Optional[int] = None,
    sample_rows: int = SAMPLE_ROWS,
) -> None:
    """Size columns once, measuring only the first ``sample_rows`` rows.

    ``stretch_column`` is left to absorb the remaining width.
    """
    header = table.horizontalHeader()
    if header.count() == 0:
        return

    rows = table.rowCount()
    if rows > sample_rows:
        # Measure a prefix, then keep those widths: resizeColumnsToContents
        # on the whole table is what makes a big roster crawl.
        hidden = []
        for row in range(sample_rows, rows):
            if not table.isRowHidden(row):
                table.setRowHidden(row, True)
                hidden.append(row)
        try:
            table.resizeColumnsToContents()
        finally:
            for row in hidden:
                table.setRowHidden(row, False)
    else:
        table.resizeColumnsToContents()

    header.setSectionResizeMode(QHeaderView.Interactive)
    if stretch_column is not None and 0 <= stretch_column < header.count():
        header.setSectionResizeMode(stretch_column, QHeaderView.Stretch)


def clamp_rows(values: Sequence, limit: int) -> tuple[Sequence, bool]:
    """Return ``values`` trimmed to ``limit`` plus whether it was trimmed."""
    if len(values) <= limit:
        return values, False
    return values[:limit], True
