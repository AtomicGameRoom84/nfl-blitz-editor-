"""Settings page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QWidget,
)

from core import paths
from core.byte_order import ByteOrder
from ui.pages.base_page import Page, card, field_row, hint


class SettingsPage(Page):
    page_key = "settings"
    page_title = "Settings"
    page_subtitle = "Stored in your user data directory, not in the application folder"
    requires_rom = False
    scrollable = True

    def build(self) -> None:
        settings = self.state.settings

        rom_card, rom_layout = card("ROM HANDLING")
        self._auto_backup = QCheckBox("Offer to back up the original ROM when one is opened")
        self._auto_backup.setChecked(bool(settings.get("auto_backup_on_load")))
        rom_layout.addWidget(self._auto_backup)

        self._confirm_save = QCheckBox("Show a modification summary before saving")
        self._confirm_save.setChecked(bool(settings.get("confirm_before_save")))
        rom_layout.addWidget(self._confirm_save)

        self._fix_crc = QCheckBox(
            "Recalculate the N64 boot checksum when saving (needed for real hardware)"
        )
        self._fix_crc.setChecked(bool(settings.get("recalculate_crc_on_save")))
        rom_layout.addWidget(self._fix_crc)

        self._save_order = QComboBox()
        for order in (ByteOrder.Z64, ByteOrder.V64, ByteOrder.N64):
            self._save_order.addItem(order.label, order.value)
        index = self._save_order.findData(settings.get("default_save_byte_order", "z64"))
        self._save_order.setCurrentIndex(max(0, index))
        rom_layout.addWidget(field_row("Default save format", self._save_order, 210))

        backup_row = QHBoxLayout()
        self._backup_dir = QLineEdit(str(settings.backup_path()))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_backup_dir)
        backup_row.addWidget(self._backup_dir, 1)
        backup_row.addWidget(browse)
        rom_layout.addWidget(field_row("Backup folder", self._wrap(backup_row), 210))
        self.body.addWidget(rom_card)

        hex_card, hex_layout = card("HEX EXPLORER")
        self._bytes_per_row = QSpinBox()
        self._bytes_per_row.setRange(4, 64)
        self._bytes_per_row.setValue(int(settings.get("hex_bytes_per_row", 16)))
        hex_layout.addWidget(field_row("Bytes per row", self._bytes_per_row, 210))

        self._font_size = QSpinBox()
        self._font_size.setRange(7, 24)
        self._font_size.setValue(int(settings.get("hex_font_size", 12)))
        hex_layout.addWidget(field_row("Font size", self._font_size, 210))

        self._uppercase = QCheckBox("Show hex digits in upper case")
        self._uppercase.setChecked(bool(settings.get("hex_uppercase", True)))
        hex_layout.addWidget(self._uppercase)
        self.body.addWidget(hex_card)

        history_card, history_layout = card("HISTORY")
        self._history_limit = QSpinBox()
        self._history_limit.setRange(10, 100_000)
        self._history_limit.setValue(int(settings.get("undo_history_limit", 500)))
        history_layout.addWidget(field_row("Undo steps kept", self._history_limit, 210))
        history_layout.addWidget(
            hint("Takes effect the next time the application starts.")
        )
        self.body.addWidget(history_card)

        locations_card, locations_layout = card("WHERE THINGS ARE STORED")
        for label, value in (
            ("User data", paths.user_data_dir()),
            ("Your game definitions", paths.user_games_dir()),
            ("Bookmarks", paths.bookmarks_dir()),
            ("Research notes", paths.research_dir()),
            ("Backups", settings.backup_path()),
            ("Bundled definitions", paths.BUILTIN_GAMES_DIR),
        ):
            row = QLabel(f"{label}:  {value}")
            row.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row.setWordWrap(True)
            row.setObjectName("Hint")
            locations_layout.addWidget(row)
        self.body.addWidget(locations_card)

        buttons = QHBoxLayout()
        save_button = QPushButton("Save settings")
        save_button.setObjectName("Primary")
        save_button.clicked.connect(self.save_settings)
        reset_button = QPushButton("Reset to defaults")
        reset_button.clicked.connect(self.reset_settings)
        prune_button = QPushButton("Prune old backups (keep 20)")
        prune_button.clicked.connect(self.prune_backups)
        for button in (save_button, reset_button, prune_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        self.body.addLayout(buttons)
        self.body.addStretch(1)

    @staticmethod
    def _wrap(layout) -> QWidget:
        """Wrap a layout in a widget so it can sit inside a field row."""
        widget = QWidget()
        widget.setLayout(layout)
        layout.setContentsMargins(0, 0, 0, 0)
        return widget

    def _browse_backup_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Backup folder", self._backup_dir.text()
        )
        if path:
            self._backup_dir.setText(path)

    def save_settings(self) -> None:
        settings = self.state.settings
        settings.set("auto_backup_on_load", self._auto_backup.isChecked())
        settings.set("confirm_before_save", self._confirm_save.isChecked())
        settings.set("recalculate_crc_on_save", self._fix_crc.isChecked())
        settings.set("default_save_byte_order", self._save_order.currentData())
        settings.set("backup_directory", self._backup_dir.text().strip())
        settings.set("hex_bytes_per_row", self._bytes_per_row.value())
        settings.set("hex_font_size", self._font_size.value())
        settings.set("hex_uppercase", self._uppercase.isChecked())
        settings.set("undo_history_limit", self._history_limit.value())
        settings.save()

        hex_page = self.window().page("hex")
        if hex_page is not None:
            hex_page.hex_view.set_bytes_per_row(self._bytes_per_row.value())
            hex_page.hex_view.set_font_size(self._font_size.value())
            hex_page.hex_view.set_uppercase(self._uppercase.isChecked())

        self.state.backups.directory = Path(settings.backup_path())
        self.state.status("Settings saved.", 4000)

    def reset_settings(self) -> None:
        answer = QMessageBox.question(
            self,
            "Reset settings",
            "Reset every setting to its default? Bookmarks, research notes and "
            "game definitions are not affected.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.state.settings.reset()
        self.state.settings.save()
        QMessageBox.information(
            self, "Settings reset", "Restart the application to see every change."
        )

    def prune_backups(self) -> None:
        removed = self.state.backups.prune(20)
        self.state.status(f"Removed {removed} old backup(s).", 4000)
