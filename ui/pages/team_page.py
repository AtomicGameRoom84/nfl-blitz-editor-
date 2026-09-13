"""Team Editor page.

The form is generated from the ``teams`` table in the game definition: one
control per declared field, typed according to the field's declaration.
Nothing here knows what a "nickname" is at a byte level.
"""

from __future__ import annotations

from typing import Dict

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.address_db import FieldDefinition
from editors.team_editor import TeamEditor
from ui import theme
from ui.pages.base_page import Page, UnavailableBanner, card, field_row, hint


class ColorButton(QPushButton):
    """A button that shows and picks an RGB colour."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rgb = (0, 0, 0)
        self.setMinimumWidth(120)
        self.clicked.connect(self._pick)

    def rgb(self) -> tuple[int, int, int]:
        return self._rgb

    def set_rgb(self, rgb: tuple[int, int, int]) -> None:
        self._rgb = rgb
        red, green, blue = rgb
        text_color = "#000000" if (red + green + blue) > 380 else "#ffffff"
        self.setText(f"#{red:02X}{green:02X}{blue:02X}")
        self.setStyleSheet(
            f"background-color: rgb({red},{green},{blue}); color: {text_color};"
            f"border: 1px solid {theme.COLORS['border']}; border-radius: 4px;"
        )

    def _pick(self) -> None:
        chosen = QColorDialog.getColor(QColor(*self._rgb), self, "Team colour")
        if chosen.isValid():
            self.set_rgb((chosen.red(), chosen.green(), chosen.blue()))


class TeamEditorPage(Page):
    page_key = "teams"
    page_title = "Team Editor"
    page_subtitle = "Team names, abbreviations, colours and logo references"
    scrollable = True

    def build(self) -> None:
        self.editor = TeamEditor(self.state.rom, self.state.definition)
        self._controls: Dict[str, QWidget] = {}

        self._banner = UnavailableBanner()
        self.body.addWidget(self._banner)

        self._form_container = QWidget()
        form_outer = QVBoxLayout(self._form_container)
        form_outer.setContentsMargins(0, 0, 0, 0)
        form_outer.setSpacing(12)

        picker_card, picker_layout = card("TEAM")
        picker_row = QHBoxLayout()
        self._team_picker = QComboBox()
        self._team_picker.setMinimumWidth(320)
        self._team_picker.activated.connect(lambda _: self.load_team())
        picker_row.addWidget(self._team_picker, 1)
        self._offset_label = QLabel("")
        self._offset_label.setObjectName("Hint")
        picker_row.addWidget(self._offset_label)
        picker_layout.addLayout(picker_row)
        form_outer.addWidget(picker_card)

        self._fields_card, self._fields_layout = card("TEAM DETAILS")
        form_outer.addWidget(self._fields_card)

        buttons = QHBoxLayout()
        save_button = QPushButton("Save Team")
        save_button.setObjectName("Primary")
        save_button.clicked.connect(self.save_team)
        reset_button = QPushButton("Reset Changes")
        reset_button.clicked.connect(self.reset_team)
        revert_button = QPushButton("Revert this team to the original ROM")
        revert_button.clicked.connect(self.revert_team)
        export_button = QPushButton("Export teams CSV…")
        export_button.clicked.connect(self.export_csv)
        import_button = QPushButton("Import teams CSV…")
        import_button.clicked.connect(self.import_csv)
        for button in (save_button, reset_button, revert_button, export_button, import_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        form_outer.addLayout(buttons)

        form_outer.addWidget(
            hint(
                "Team records are written in place, so a replacement name must "
                "fit the field width the ROM allocates. Adding brand new teams "
                "would require relocating the table and is not supported."
            )
        )
        self.body.addWidget(self._form_container)
        self.body.addStretch(1)

        self.state.definitionChanged.connect(self.rebuild)
        self.state.romLoaded.connect(self.rebuild)
        self.state.romClosed.connect(self.rebuild)
        self.rebuild()

    # -- construction ------------------------------------------------------

    def on_activated(self) -> None:
        self.rebuild()

    def rebuild(self) -> None:
        self.editor.set_definition(self.state.definition)
        self.editor.rom = self.state.rom

        status = self.editor.availability()
        self._banner.setVisible(not status)
        self._form_container.setVisible(bool(status))
        if not status:
            self._banner.show_status(status, "Team Editor is not available yet")
            return

        current = self._team_picker.currentIndex()
        self._team_picker.blockSignals(True)
        self._team_picker.clear()
        self._team_picker.addItems(self.editor.team_labels())
        self._team_picker.setCurrentIndex(
            max(0, min(current, self._team_picker.count() - 1))
        )
        self._team_picker.blockSignals(False)

        self._build_fields()
        self.load_team()

    def _build_fields(self) -> None:
        while self._fields_layout.count() > 1:  # keep the heading
            item = self._fields_layout.takeAt(1)
            widget = item.widget()
            if widget is not None:
                # Detach now: deleteLater() alone leaves the old widget parented
                # and still painting until the event loop next runs.
                widget.setParent(None)
                widget.deleteLater()
        self._controls.clear()

        for field in self.editor.fields():
            control = self._control_for(field)
            self._controls[field.id] = control
            self._fields_layout.addWidget(field_row(field.name, control))

    def _control_for(self, field: FieldDefinition) -> QWidget:
        if field.kind == "color":
            return ColorButton()
        if field.kind == "text":
            edit = QLineEdit()
            edit.setMaxLength(field.size)
            edit.setPlaceholderText(f"up to {field.size} characters")
            return edit
        if field.kind == "enum":
            combo = QComboBox()
            for raw, label in field.options.get("values", {}).items():
                combo.addItem(f"{label}", int(raw))
            return combo
        box = QSpinBox()
        low = field.minimum if field.minimum is not None else field.data_type.minimum
        high = field.maximum if field.maximum is not None else field.data_type.maximum
        box.setRange(int(low if low is not None else 0), int(high if high is not None else 2**31 - 1))
        return box

    # -- data --------------------------------------------------------------

    @property
    def _index(self) -> int:
        return max(0, self._team_picker.currentIndex())

    def load_team(self) -> None:
        if not self.editor.availability():
            return
        record = self.editor.read_record(self._index)
        self._offset_label.setText(
            f"record at 0x{record.offset:06X}"
        )
        for field in self.editor.fields():
            control = self._controls.get(field.id)
            if control is None:
                continue
            value = record.values.get(field.id)
            if isinstance(control, ColorButton):
                rgb = self.editor.read_color(self._index, field.id)
                control.set_rgb(rgb or (0, 0, 0))
            elif isinstance(control, QLineEdit):
                control.setText(str(value or ""))
            elif isinstance(control, QComboBox):
                index = control.findData(int(value or 0))
                control.setCurrentIndex(max(0, index))
            elif isinstance(control, QSpinBox):
                control.setValue(int(value or 0))

    def save_team(self) -> None:
        if not self.editor.availability():
            return
        index = self._index
        values = {}
        colors = {}
        for field in self.editor.fields():
            control = self._controls.get(field.id)
            if isinstance(control, ColorButton):
                colors[field.id] = control.rgb()
            elif isinstance(control, QLineEdit):
                values[field.id] = control.text()
            elif isinstance(control, QComboBox):
                values[field.id] = control.currentData()
            elif isinstance(control, QSpinBox):
                values[field.id] = control.value()

        try:
            with self.state.rom.undo.transaction(f"Edit team #{index}"):
                for field_id, value in values.items():
                    self.editor.write_field(index, field_id, value)
                for field_id, rgb in colors.items():
                    self.editor.write_color(index, field_id, rgb)
        except (ValueError, KeyError, RuntimeError) as exc:
            QMessageBox.warning(self, "Could not save team", str(exc))
            self.load_team()
            return

        self.rebuild()
        self._team_picker.setCurrentIndex(index)
        self.state.status(f"Team #{index} written to the working copy.", 4000)

    def reset_team(self) -> None:
        """Discard unsaved form edits by re-reading the working copy."""
        self.load_team()

    def revert_team(self) -> None:
        table = self.editor.table
        if table is None or not self.editor.availability():
            return
        index = self._index
        offset = table.record_offset(index)
        command = self.state.rom.revert_range(offset, table.record_size)
        if command is None:
            self.state.status("This team already matches the original ROM.", 4000)
        else:
            self.state.status(f"Team #{index} reverted to the original ROM.", 4000)
        self.rebuild()
        self._team_picker.setCurrentIndex(index)

    # -- CSV ---------------------------------------------------------------

    def export_csv(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        if not self.editor.availability():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export teams", "teams.csv", "CSV (*.csv)")
        if path:
            self.editor.export_csv(path)
            self.state.status(f"Exported to {path}", 5000)

    def import_csv(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        if not self.editor.availability():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import teams", "", "CSV (*.csv)")
        if not path:
            return
        try:
            changed = self.editor.import_csv(path)
        except (ValueError, OSError, RuntimeError) as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
            return
        self.rebuild()
        self.state.status(f"Updated {changed} team record(s).", 5000)
