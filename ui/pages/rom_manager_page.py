"""ROM Manager: load a ROM, see what it is, and manage backups."""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
)

from core.rom_validator import ValidationReport
from ui import theme
from ui.pages.base_page import Page, card, hint

ROM_FILTER = "N64 ROMs (*.z64 *.v64 *.n64 *.rom *.bin);;All files (*)"


class ROMManagerPage(Page):
    page_key = "rom"
    page_title = "ROM Manager"
    page_subtitle = (
        "Load a legally obtained NFL Blitz cartridge dump. The original file is "
        "opened read-only and is never modified."
    )
    requires_rom = False
    scrollable = True

    def build(self) -> None:
        state = self.state

        # -- status card ---------------------------------------------------
        status_card, status_layout = card("ROM STATUS")
        self._status_grid = QGridLayout()
        self._status_grid.setHorizontalSpacing(18)
        self._status_grid.setVerticalSpacing(5)
        self._status_grid.setColumnStretch(1, 1)
        self._status_fields = {}
        rows = [
            ("Loaded", "loaded"),
            ("File", "file"),
            ("Format", "format"),
            ("Region", "region"),
            ("Game code", "code"),
            ("Size", "size"),
            ("Boot CRC", "crc"),
            ("CIC chip", "cic"),
            ("Status", "status"),
        ]
        for row, (label_text, key) in enumerate(rows):
            label = QLabel(label_text)
            label.setObjectName("Hint")
            value = QLabel("—")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value.setWordWrap(True)
            self._status_grid.addWidget(label, row, 0, Qt.AlignRight | Qt.AlignTop)
            self._status_grid.addWidget(value, row, 1)
            self._status_fields[key] = value
        status_layout.addLayout(self._status_grid)

        self._warnings = QLabel("")
        self._warnings.setWordWrap(True)
        self._warnings.setVisible(False)
        status_layout.addWidget(self._warnings)

        buttons = QHBoxLayout()
        self._open_button = QPushButton("Open ROM…")
        self._open_button.setObjectName("Primary")
        self._open_button.clicked.connect(self.open_rom_dialog)
        self._backup_button = QPushButton("Create Backup")
        self._backup_button.clicked.connect(self.create_backup)
        self._save_button = QPushButton("Save ROM As…")
        self._save_button.clicked.connect(self.state.saveAsRequested)
        self._close_button = QPushButton("Close ROM")
        self._close_button.clicked.connect(self.close_rom)
        for button in (
            self._open_button, self._backup_button, self._save_button, self._close_button
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)
        status_layout.addLayout(buttons)
        self.body.addWidget(status_card)

        # -- identification card -------------------------------------------
        id_card, id_layout = card("DETECTED GAME VERSION")
        self._match_label = QLabel("—")
        self._match_label.setWordWrap(True)
        id_layout.addWidget(self._match_label)
        self._match_reasons = QLabel("")
        self._match_reasons.setObjectName("Hint")
        self._match_reasons.setWordWrap(True)
        id_layout.addWidget(self._match_reasons)

        picker_row = QHBoxLayout()
        picker_row.addWidget(QLabel("Use definition:"))
        self._definition_picker = QComboBox()
        self._definition_picker.setMinimumWidth(280)
        self._definition_picker.activated.connect(self._definition_chosen)
        picker_row.addWidget(self._definition_picker, 1)
        id_layout.addLayout(picker_row)

        id_buttons = QHBoxLayout()
        self._register_button = QPushButton("Register this ROM's fingerprint")
        self._register_button.setToolTip(
            "Copy this ROM's CRC and SHA-1 into your personal copy of the "
            "definition so it is matched exactly next time."
        )
        self._register_button.clicked.connect(self.register_fingerprint)
        reload_button = QPushButton("Reload definitions")
        reload_button.clicked.connect(self.reload_definitions)
        id_buttons.addWidget(self._register_button)
        id_buttons.addWidget(reload_button)
        id_buttons.addStretch(1)
        id_layout.addLayout(id_buttons)

        self._definition_stats = QLabel("")
        self._definition_stats.setObjectName("Hint")
        self._definition_stats.setWordWrap(True)
        id_layout.addWidget(self._definition_stats)
        self.body.addWidget(id_card)

        # -- recent and backups --------------------------------------------
        lists_row = QHBoxLayout()
        recent_card, recent_layout = card("RECENT ROMS")
        self._recent_list = QListWidget()
        self._recent_list.itemDoubleClicked.connect(self._open_recent)
        recent_layout.addWidget(self._recent_list)
        recent_layout.addWidget(hint("Double-click to open."))
        lists_row.addWidget(recent_card, 1)

        backup_card, backup_layout = card("BACKUPS")
        self._backup_list = QListWidget()
        backup_layout.addWidget(self._backup_list)
        backup_row = QHBoxLayout()
        restore_button = QPushButton("Restore selected to…")
        restore_button.clicked.connect(self.restore_backup)
        backup_row.addWidget(restore_button)
        backup_row.addStretch(1)
        backup_layout.addLayout(backup_row)
        lists_row.addWidget(backup_card, 1)
        self.body.addLayout(lists_row)

        self.body.addWidget(
            hint(
                "This tool never distributes ROM data. Share your work as an IPS "
                "or BPS patch from the Patch Builder, and let other people supply "
                "their own cartridge dump."
            )
        )

        state.romLoaded.connect(self.refresh)
        state.romClosed.connect(self.refresh)
        state.definitionChanged.connect(self.refresh)
        state.historyChanged.connect(self._refresh_status_only)
        self.refresh()

    # -- actions -----------------------------------------------------------

    def open_rom_dialog(self) -> None:
        start_dir = self.state.settings.get("last_directory", "") or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Open NFL Blitz ROM", start_dir, ROM_FILTER)
        if path:
            self.load_rom(path)

    def load_rom(self, path: str) -> Optional[ValidationReport]:
        """Load a ROM and offer a backup, reporting any problem clearly.

        Returns the load report, or ``None`` if the file could not be opened,
        so that a caller can tell the two apart.  The user sees the warnings
        either way: they are listed in the status panel below.
        """
        try:
            report = self.state.load_rom(path)
        except Exception as exc:  # surfaced to the user rather than swallowed
            QMessageBox.critical(self, "Could not open ROM", str(exc))
            return None

        if self.state.settings.get("auto_backup_on_load", True):
            self._offer_backup(path)

        warning_count = len(report.warnings)
        self.state.status(
            f"Loaded {Path(path).name}"
            + (f" with {warning_count} warning(s)" if warning_count else ""),
            6000,
        )
        return report

    def _offer_backup(self, path: str) -> None:
        if self.state.backups.has_backup_of(path):
            return
        answer = QMessageBox.question(
            self,
            "Create a backup?",
            f"Keep a private backup copy of:\n\n{path}\n\n"
            f"Backups are stored in:\n{self.state.backups.directory}\n\n"
            "The suite never writes to your original file, but a backup costs "
            "nothing and an original cartridge dump is hard to replace.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer == QMessageBox.Yes:
            self.create_backup()

    def create_backup(self) -> None:
        if self.state.rom.path is None:
            QMessageBox.information(
                self, "Nothing to back up", "Load a ROM from a file first."
            )
            return
        try:
            record = self.state.backups.create_backup(self.state.rom.path)
        except OSError as exc:
            QMessageBox.critical(self, "Backup failed", str(exc))
            return
        if record is None:
            self.state.status("An identical backup already exists.", 4000)
        else:
            self.state.status(f"Backed up to {record.path.name}", 5000)
        self._refresh_backups()

    def restore_backup(self) -> None:
        item = self._backup_list.currentItem()
        if item is None:
            QMessageBox.information(self, "Restore backup", "Select a backup first.")
            return
        record = item.data(Qt.UserRole)
        destination, _ = QFileDialog.getSaveFileName(
            self, "Restore backup to…", record.path.name, ROM_FILTER
        )
        if not destination:
            return
        try:
            self.state.backups.restore(record, destination)
        except OSError as exc:
            QMessageBox.critical(self, "Restore failed", str(exc))
            return
        self.state.status(f"Restored to {destination}", 5000)

    def close_rom(self) -> None:
        if not self.state.rom.is_loaded:
            return
        if self.state.rom.is_dirty:
            answer = QMessageBox.question(
                self,
                "Discard changes?",
                "The working copy has unsaved modifications. Close it anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        self.state.close_rom()
        self.state.status("ROM closed.", 3000)

    def register_fingerprint(self) -> None:
        if self.state.definition is None or self.state.identity is None:
            QMessageBox.information(
                self,
                "No definition selected",
                "Load a ROM and choose a game definition first.",
            )
            return
        updated = self.state.address_db.register_fingerprint(
            self.state.definition, self.state.identity
        )
        self.state.definition = updated
        self.state.definitionChanged.emit()
        QMessageBox.information(
            self,
            "Fingerprint registered",
            f"Saved this ROM's CRC and SHA-1 into:\n\n{updated.source_path}\n\n"
            "This ROM will now be matched exactly, and your copy of the "
            "definition takes precedence over the one shipped with the suite.",
        )

    def reload_definitions(self) -> None:
        self.state.reload_definitions()
        errors = self.state.address_db.load_errors
        if errors:
            QMessageBox.warning(
                self,
                "Some definitions failed to load",
                "\n".join(errors),
            )
        self.state.status(
            f"{len(self.state.address_db.definitions)} definition(s) loaded.", 4000
        )

    def _definition_chosen(self, index: int) -> None:
        definition_id = self._definition_picker.itemData(index)
        if definition_id is None:
            self.state.set_definition(None)
            return
        self.state.set_definition(self.state.address_db.get(definition_id))

    def _open_recent(self, item: QListWidgetItem) -> None:
        self.load_rom(item.data(Qt.UserRole))

    # -- refresh -----------------------------------------------------------

    def on_activated(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self._refresh_status_only()
        self._refresh_identification()
        self._refresh_recent()
        self._refresh_backups()

    def _refresh_status_only(self) -> None:
        rom = self.state.rom
        fields = self._status_fields
        loaded = rom.is_loaded

        for button in (self._backup_button, self._save_button, self._close_button):
            button.setEnabled(loaded)
        self._register_button.setEnabled(loaded and self.state.definition is not None)

        if not loaded:
            for value in fields.values():
                value.setText("—")
            fields["loaded"].setText("No ROM loaded")
            fields["status"].setText("Open a ROM to begin")
            self._warnings.setVisible(False)
            return

        header = rom.header
        report = rom.report
        fields["loaded"].setText(header.image_name or "(unnamed image)")
        fields["file"].setText(str(rom.path) if rom.path else "(in memory)")
        fields["format"].setText(
            f"N64 — loaded as {rom.source_byte_order.label}"
        )
        fields["region"].setText(f"{header.region} (0x{header.region_code:02X})")
        fields["code"].setText(f"{header.game_code}  rev {header.revision}")
        fields["size"].setText(
            f"{rom.size / 1024:,.0f} KB  ({rom.size:,} bytes)"
        )

        stored = rom.stored_boot_checksum()
        calculated = rom.calculate_boot_checksum()
        crc_text = f"{stored[0]:08X} / {stored[1]:08X}"
        if calculated is None:
            crc_text += "   (cannot verify — unknown boot code)"
        elif calculated == stored:
            crc_text += "   ✓ matches contents"
        else:
            crc_text += (
                f"   ✗ contents give {calculated[0]:08X}/{calculated[1]:08X}"
            )
        fields["crc"].setText(crc_text)
        cic = rom.detected_cic()
        fields["cic"].setText(str(cic) if cic else "Not recognised")

        if rom.is_dirty:
            summary = rom.modification_summary()
            fields["status"].setText(
                f"Modified — {summary['changed_bytes']:,} byte(s) in "
                f"{summary['changed_regions']} region(s), "
                f"{summary['history_steps']} undo step(s)"
            )
            fields["status"].setStyleSheet(f"color: {theme.COLORS['modified']};")
        else:
            fields["status"].setText("Ready for editing")
            fields["status"].setStyleSheet(f"color: {theme.COLORS['success']};")

        if report and report.warnings:
            self._warnings.setText(
                "Warnings:\n" + "\n".join(f"  • {w}" for w in report.warnings)
            )
            self._warnings.setStyleSheet(f"color: {theme.COLORS['warning']};")
            self._warnings.setVisible(True)
        else:
            self._warnings.setVisible(False)

    def _refresh_identification(self) -> None:
        picker = self._definition_picker
        picker.blockSignals(True)
        picker.clear()
        picker.addItem("(none — hex tools only)", None)
        for definition in self.state.address_db.all():
            suffix = "  [yours]" if definition.user_defined else ""
            picker.addItem(definition.display_name + suffix, definition.id)
        if self.state.definition is not None:
            index = picker.findData(self.state.definition.id)
            picker.setCurrentIndex(max(0, index))
        else:
            picker.setCurrentIndex(0)
        picker.blockSignals(False)

        if not self.state.rom.is_loaded:
            self._match_label.setText("—")
            self._match_reasons.setText("")
            self._definition_stats.setText("")
            return

        match = self.state.match
        if match is None and self.state.definition is None:
            self._match_label.setText(
                "ROM version not yet supported for automatic editing."
            )
            self._match_label.setStyleSheet(f"color: {theme.COLORS['warning']};")
            self._match_reasons.setText(
                "No shipped definition matches this ROM. The Hex/Data Explorer, "
                "Value Search, ROM Comparison, Bookmarks and Patch Builder all "
                "still work — they are how a definition gets written."
            )
        elif match is not None:
            confidence = "exact fingerprint match" if match.exact else "heuristic match"
            self._match_label.setText(
                f"{match.definition.display_name}  —  {confidence} "
                f"(score {match.score})"
            )
            self._match_label.setStyleSheet(
                f"color: {theme.COLORS['success'] if match.exact else theme.COLORS['warning']};"
            )
            self._match_reasons.setText("\n".join(f"  • {r}" for r in match.reasons))
        else:
            self._match_label.setText(
                f"{self.state.definition.display_name}  —  chosen manually"
            )
            self._match_label.setStyleSheet(f"color: {theme.COLORS['info']};")
            self._match_reasons.setText(
                "Addresses from a definition written for a different build are "
                "very unlikely to be correct. Verify before trusting an edit."
            )

        definition = self.state.definition
        if definition is None:
            self._definition_stats.setText("")
            return
        stats = definition.stats()
        self._definition_stats.setText(
            f"{definition.id}: {stats['discovered']} of {stats['entries']} value(s) "
            f"located, {stats['tables_discovered']} of {stats['tables']} table(s) "
            f"located."
            + (f"\nFile: {definition.source_path}" if definition.source_path else "")
        )

    def _refresh_recent(self) -> None:
        self._recent_list.clear()
        for entry in self.state.settings.get("recent_roms", []):
            item = QListWidgetItem(Path(entry).name)
            item.setToolTip(entry)
            item.setData(Qt.UserRole, entry)
            if not Path(entry).exists():
                item.setText(item.text() + "  (missing)")
                item.setForeground(theme.color("text_faint"))
            self._recent_list.addItem(item)

    def _refresh_backups(self) -> None:
        self._backup_list.clear()
        for record in self.state.backups.backups()[:40]:
            label = f"{record.path.name}   {record.created_display}   {record.size / 1024:,.0f} KB"
            item = QListWidgetItem(label)
            item.setToolTip(f"From {record.source_path}\nSHA-1 {record.sha1}")
            item.setData(Qt.UserRole, record)
            if not record.exists:
                item.setForeground(theme.color("danger"))
                item.setText(label + "   (file missing)")
            self._backup_list.addItem(item)
