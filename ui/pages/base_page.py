"""Shared scaffolding for every sidebar page."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from editors.base import Availability
from ui.app_state import AppState


def card(title: str = "") -> tuple[QFrame, QVBoxLayout]:
    """A bordered panel with an optional heading.  Returns the frame and layout."""
    frame = QFrame()
    frame.setObjectName("Card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(8)
    if title:
        heading = QLabel(title)
        heading.setObjectName("SectionHeading")
        layout.addWidget(heading)
    return frame, layout


def hint(text: str) -> QLabel:
    """A wrapped, dimmed explanatory label."""
    label = QLabel(text)
    label.setObjectName("Hint")
    label.setWordWrap(True)
    return label


def field_row(label_text: str, widget: QWidget, label_width: int = 150) -> QWidget:
    """A ``label: widget`` row for simple forms."""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    label = QLabel(label_text)
    label.setMinimumWidth(label_width)
    label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    layout.addWidget(label)
    layout.addWidget(widget, 1)
    return row


class UnavailableBanner(QFrame):
    """Explains why an editor cannot run, instead of showing a blank page.

    Every editor that depends on undiscovered data shows one of these, with
    the exact list of what is missing and a pointer at the discovery tools.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        self._title = QLabel("Not available")
        self._title.setObjectName("SectionHeading")
        self._reason = QLabel("")
        self._reason.setWordWrap(True)
        self._missing = QLabel("")
        self._missing.setWordWrap(True)
        self._missing.setObjectName("Hint")
        self._next_steps = QLabel(
            "The Hex/Data Explorer, Value Search, ROM Comparison and Bookmarks "
            "all work on any ROM — that is how these addresses get found. "
            "See docs/DISCOVERING_ADDRESSES.md for the workflow."
        )
        self._next_steps.setWordWrap(True)
        self._next_steps.setObjectName("Hint")

        for widget in (self._title, self._reason, self._missing, self._next_steps):
            layout.addWidget(widget)

    def show_status(self, status: Availability, title: str = "Not available") -> None:
        self._title.setText(title)
        self._reason.setText(status.reason)
        if status.missing:
            self._missing.setText(
                "Still needed: " + ", ".join(status.missing)
            )
            self._missing.setVisible(True)
        else:
            self._missing.setVisible(False)


class Page(QWidget):
    """Base class for sidebar pages.

    Subclasses set :attr:`page_key`, :attr:`page_title` and
    :attr:`page_subtitle`, then add widgets to :attr:`body`.
    """

    page_key = "page"
    page_title = "Page"
    page_subtitle = ""
    #: When True the sidebar entry is greyed out until a ROM is loaded.
    requires_rom = True
    #: When True the page content sits inside a vertical scroll area.
    scrollable = False

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(parent)
        self.state = state

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(12)

        header = QVBoxLayout()
        header.setSpacing(2)
        self._title_label = QLabel(self.page_title)
        self._title_label.setObjectName("PageTitle")
        header.addWidget(self._title_label)
        if self.page_subtitle:
            self._subtitle_label = QLabel(self.page_subtitle)
            self._subtitle_label.setObjectName("PageSubtitle")
            self._subtitle_label.setWordWrap(True)
            header.addWidget(self._subtitle_label)
        else:
            self._subtitle_label = None
        outer.addLayout(header)

        self.body = QVBoxLayout()
        self.body.setSpacing(12)

        if self.scrollable:
            container = QWidget()
            container.setObjectName("PageScrollBody")
            container.setLayout(self.body)
            # Minimum (not Maximum): the container may grow to fill the
            # viewport, but never shrinks below what its content needs -- which
            # is what makes the scroll bar appear instead of squashing rows.
            container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
            scroll = QScrollArea()
            scroll.setObjectName("PageScroll")
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidget(container)
            outer.addWidget(scroll, 1)
        else:
            outer.addLayout(self.body, 1)

        self.build()

    # -- hooks -------------------------------------------------------------

    def build(self) -> None:
        """Construct the page contents.  Subclasses override this."""

    def on_activated(self) -> None:
        """Called each time the page becomes visible."""

    def set_subtitle(self, text: str) -> None:
        if self._subtitle_label is not None:
            self._subtitle_label.setText(text)
