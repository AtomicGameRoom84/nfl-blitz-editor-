"""Gameplay value pages.

"Gameplay Values", "Physics & Movement" and "Passing & Ball Physics" are the
same page class with different categories; each renders whatever its
categories declare in the loaded ROM's game definition.  No addresses appear
in this file.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from PySide6.QtCore import Qt

from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.address_db import ValueEntry
from editors.base import Availability
from editors.gameplay_editor import GameplayEditor
from tools.gameshark import float_high_half, make_code
from ui import theme
from ui.pages.base_page import Page, UnavailableBanner, card, hint


from ui.widgets.value_row import ValueRow


class GameplayPage(Page):
    """Base class; subclasses set :attr:`categories`."""

    #: Definition categories rendered by this page, in display order.
    categories: Tuple[str, ...] = ("misc",)
    scrollable = True

    def build(self) -> None:
        self.editors: List[GameplayEditor] = [
            GameplayEditor(self.state.rom, self.state.definition, category)
            for category in self.categories
        ]
        self._rows: Dict[str, ValueRow] = {}

        self._banner = UnavailableBanner()
        self.body.addWidget(self._banner)

        self._groups_container = QWidget()
        self._groups_layout = QVBoxLayout(self._groups_container)
        self._groups_layout.setContentsMargins(0, 0, 0, 0)
        self._groups_layout.setSpacing(12)
        self.body.addWidget(self._groups_container)

        # Runtime codes: things this section can change *right now* in an
        # emulator, even though no ROM address for them is known.
        self._runtime_card, self._runtime_layout = card("RUNTIME CODES FOR THIS SECTION")
        self.body.addWidget(self._runtime_card)

        self._actions = QWidget()
        actions_layout = QHBoxLayout(self._actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        restore_all = QPushButton("Restore all defaults")
        restore_all.clicked.connect(self.restore_all)
        actions_layout.addWidget(restore_all)
        self._modified_label = QLabel("")
        self._modified_label.setObjectName("Hint")
        actions_layout.addWidget(self._modified_label)
        actions_layout.addStretch(1)
        self.body.addWidget(self._actions)

        self.body.addWidget(
            hint(
                "These controls come from the game definition for the loaded "
                "ROM, not from hardcoded addresses. Found a new one? Bookmark "
                "it, then use Bookmarks → \"Promote to game definition\" and "
                "it appears here."
            )
        )
        self.body.addStretch(1)

        self.state.definitionChanged.connect(self.rebuild)
        self.state.romLoaded.connect(self.rebuild)
        self.state.romClosed.connect(self.rebuild)
        self.state.romChanged.connect(lambda _r: self.refresh_values())
        self.rebuild()

    # -- construction ------------------------------------------------------

    def on_activated(self) -> None:
        self.rebuild()

    def _clear_groups(self) -> None:
        while self._groups_layout.count():
            item = self._groups_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Detach now: deleteLater() alone leaves the old widget parented
                # and still painting until the event loop next runs.
                widget.setParent(None)
                widget.deleteLater()
        self._rows.clear()

    def rebuild(self) -> None:
        """Rebuild every row from the current definition."""
        for editor in self.editors:
            editor.set_definition(self.state.definition)
            editor.rom = self.state.rom

        self._clear_groups()

        statuses = [editor.availability() for editor in self.editors]
        any_available = any(bool(status) for status in statuses)
        total_entries = sum(len(editor.entries()) for editor in self.editors)

        self._banner.setVisible(not any_available)
        if not any_available:
            # Report the most informative reason rather than the first.
            blocked = max(statuses, key=lambda s: len(s.missing)) if statuses else Availability(False)
            self._banner.show_status(
                blocked, f"{self.page_title} is not available yet"
            )

        self._actions.setVisible(any_available)
        if not total_entries:
            return

        multiple = len(self.editors) > 1
        for editor in self.editors:
            entries = editor.entries()
            if not entries:
                continue
            for group in editor.groups():
                group_entries = [e for e in entries if (e.group or "General") == group]
                if not group_entries:
                    continue
                heading = f"{editor.category.upper()} — {group.upper()}" if multiple else group.upper()
                frame, layout = card(heading)
                for entry in group_entries:
                    row = ValueRow(entry, self._value_changed, self._restore_one)
                    self._rows[entry.id] = row
                    layout.addWidget(row)
                self._groups_layout.addWidget(frame)

        self._rebuild_runtime_codes()
        self.refresh_values()

    def _rebuild_runtime_codes(self) -> None:
        """List the catalogued RAM addresses that belong to this page."""
        while self._runtime_layout.count() > 1:      # keep the heading
            item = self._runtime_layout.takeAt(1)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        definition = self.state.definition
        codes = []
        if definition is not None:
            for category in self.categories:
                codes.extend(definition.ram_codes_in(category))
        self._runtime_codes = codes
        self._runtime_card.setVisible(bool(codes))
        if not codes:
            return

        self._runtime_layout.addWidget(
            hint(
                "These are runtime (RAM) addresses, not ROM offsets \u2014 so they "
                "cannot be baked into a saved ROM, but they work today in an "
                "emulator or on a GameShark. Copy the codes and paste them in."
            )
        )
        for entry in codes:
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 2, 0, 2)
            name = QLabel(entry.name)
            name.setMinimumWidth(230)
            layout.addWidget(name)
            value = int(entry.default if entry.default is not None else 1) or 1
            raw = float_high_half(float(value)) if entry.float_high_half else value
            code_text = make_code(entry.address, raw, entry.width).format()
            code_label = QLabel(code_text)
            code_label.setFont(theme.monospace_font(11))
            code_label.setStyleSheet(f"color: {theme.COLORS['accent']};")
            code_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(code_label)
            badge = QLabel(entry.confidence)
            badge.setObjectName("Hint")
            layout.addWidget(badge)
            layout.addStretch(1)
            self._runtime_layout.addWidget(row)

        buttons = QWidget()
        button_row = QHBoxLayout(buttons)
        button_row.setContentsMargins(0, 6, 0, 0)
        copy_all = QPushButton("Copy these codes")
        copy_all.clicked.connect(self._copy_runtime_codes)
        button_row.addWidget(copy_all)
        open_page = QPushButton("Open the GameShark page")
        open_page.clicked.connect(lambda: self.state.navigate("gameshark"))
        button_row.addWidget(open_page)
        button_row.addStretch(1)
        self._runtime_layout.addWidget(buttons)

    def _copy_runtime_codes(self) -> None:
        lines = []
        for entry in getattr(self, "_runtime_codes", []):
            value = int(entry.default if entry.default is not None else 1) or 1
            raw = float_high_half(float(value)) if entry.float_high_half else value
            lines.append(f"{make_code(entry.address, raw, entry.width).format()}  ; {entry.name}")
        if not lines:
            return
        QApplication.clipboard().setText("\n".join(lines))
        self.state.status(f"Copied {len(lines)} GameShark code(s).", 4000)

    def refresh_values(self) -> None:
        if not self._rows:
            return
        changed = 0
        for editor in self.editors:
            for entry in editor.entries():
                row = self._rows.get(entry.id)
                if row is not None:
                    row.apply_state(editor.state_for(entry))
            if self.state.rom.is_loaded and editor.definition is not None:
                changed += editor.modified_count()
        self._modified_label.setText(
            f"{changed} value(s) changed from the loaded ROM"
            if changed
            else "No changes in this section"
        )

    # -- editing -----------------------------------------------------------

    def _editor_for(self, entry: ValueEntry) -> GameplayEditor:
        for editor in self.editors:
            if editor.category == entry.category:
                return editor
        return self.editors[0]

    def _value_changed(self, entry: ValueEntry, value: float) -> None:
        try:
            self._editor_for(entry).set_value(entry, value)
        except (ValueError, IndexError) as exc:
            self.state.status(str(exc), 6000)

    def _restore_one(self, entry: ValueEntry) -> None:
        try:
            self._editor_for(entry).restore_default(entry)
        except (ValueError, IndexError) as exc:
            QMessageBox.warning(self, "Restore default", str(exc))

    def restore_all(self) -> None:
        changed = 0
        try:
            for editor in self.editors:
                changed += editor.restore_all_defaults()
        except (ValueError, IndexError) as exc:
            QMessageBox.warning(self, "Restore defaults", str(exc))
            return
        self.state.status(f"Restored {changed} value(s).", 4000)


class GameplayValuesPage(GameplayPage):
    page_key = "gameplay"
    page_title = "Gameplay Values"
    page_subtitle = "Game rules and any other constants the definition declares"
    categories = ("misc",)


class MovementPage(GameplayPage):
    page_key = "movement"
    page_title = "Physics & Movement"
    page_subtitle = (
        "Running speed, acceleration, turning, jumping, weight, and contact physics"
    )
    categories = ("movement", "physics")


class PassingPage(GameplayPage):
    page_key = "passing"
    page_title = "Passing & Ball Physics"
    page_subtitle = "Pass distance, velocity, accuracy and ball flight"
    categories = ("passing",)
