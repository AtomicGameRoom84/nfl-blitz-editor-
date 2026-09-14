"""Patch Builder: share a mod without sharing a ROM."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
)

from core.patch import (
    PatchBuilder,
    PatchError,
    PatchMetadata,
    PatchMismatchError,
    PatchTooLargeError,
)
from core.undo import CompositeCommand, WriteBytesCommand
from tools.comparator import diff_buffers
from ui import theme
from ui.pages.base_page import Page, card, field_row, hint

ROM_FILTER = "N64 ROMs (*.z64 *.v64 *.n64 *.rom *.bin);;All files (*)"
PATCH_FILTER = "Patches (*.bps *.ips);;BPS patch (*.bps);;IPS patch (*.ips);;All files (*)"


class PatchPage(Page):
    page_key = "patch"
    page_title = "Patch Builder"
    page_subtitle = (
        "Create an IPS or BPS patch containing only your changes. A patch "
        "carries no game data, so it can be shared freely; the recipient "
        "supplies their own cartridge dump."
    )
    scrollable = True

    def build(self) -> None:
        source_card, source_layout = card("WHAT TO COMPARE")
        self._source_working = QRadioButton(
            "The loaded ROM as opened  →  your working copy (recommended)"
        )
        self._source_working.setChecked(True)
        self._source_working.toggled.connect(lambda _: self._refresh_estimate())
        self._source_files = QRadioButton("Two files on disk")
        self._source_files.toggled.connect(lambda _: self._refresh_estimate())
        source_layout.addWidget(self._source_working)
        source_layout.addWidget(self._source_files)

        file_row = QHBoxLayout()
        self._original_edit = QLineEdit()
        self._original_edit.setPlaceholderText("Original ROM")
        original_browse = QPushButton("…")
        original_browse.setMaximumWidth(36)
        original_browse.clicked.connect(lambda: self._browse(self._original_edit))
        self._modified_edit = QLineEdit()
        self._modified_edit.setPlaceholderText("Modified ROM")
        modified_browse = QPushButton("…")
        modified_browse.setMaximumWidth(36)
        modified_browse.clicked.connect(lambda: self._browse(self._modified_edit))
        file_row.addWidget(self._original_edit, 1)
        file_row.addWidget(original_browse)
        file_row.addWidget(QLabel("→"))
        file_row.addWidget(self._modified_edit, 1)
        file_row.addWidget(modified_browse)
        source_layout.addLayout(file_row)

        self._estimate = QLabel("")
        self._estimate.setWordWrap(True)
        source_layout.addWidget(self._estimate)
        refresh_button = QPushButton("Refresh estimate")
        refresh_button.clicked.connect(self._refresh_estimate)
        source_layout.addWidget(refresh_button)
        self.body.addWidget(source_card)

        # -- metadata ------------------------------------------------------
        meta_card, meta_layout = card("PATCH DETAILS")
        self._name = QLineEdit()
        self._version = QLineEdit("1.0")
        self._author = QLineEdit()
        self._description = QPlainTextEdit()
        self._description.setMaximumHeight(80)
        meta_layout.addWidget(field_row("Patch name", self._name))
        meta_layout.addWidget(field_row("Version", self._version))
        meta_layout.addWidget(field_row("Author", self._author))
        meta_layout.addWidget(field_row("Description", self._description))
        meta_layout.addWidget(
            hint(
                "BPS stores these details inside the patch. IPS has no metadata "
                "field, so they are written to a .json file beside the patch "
                "instead of being discarded."
            )
        )
        self.body.addWidget(meta_card)

        # -- create --------------------------------------------------------
        create_card, create_layout = card("CREATE")
        format_row = QHBoxLayout()
        format_row.addWidget(QLabel("Format"))
        self._format = QComboBox()
        self._format.addItem("BPS — recommended for N64 (checksummed, no size limit)", "bps")
        self._format.addItem("IPS — widest compatibility, 16 MiB limit", "ips")
        format_row.addWidget(self._format, 1)
        create_button = QPushButton("Export patch…")
        create_button.setObjectName("Primary")
        create_button.clicked.connect(self.create_patch)
        format_row.addWidget(create_button)
        create_layout.addLayout(format_row)
        self.body.addWidget(create_card)

        # -- apply ---------------------------------------------------------
        apply_card, apply_layout = card("APPLY A PATCH")
        apply_layout.addWidget(
            hint(
                "Applies a patch to the loaded ROM's working copy as a single "
                "undoable step. Your file on disk is untouched until you save."
            )
        )
        apply_row = QHBoxLayout()
        inspect_button = QPushButton("Inspect patch…")
        inspect_button.clicked.connect(self.inspect_patch)
        apply_button = QPushButton("Import and apply patch…")
        apply_button.clicked.connect(self.apply_patch)
        apply_row.addWidget(inspect_button)
        apply_row.addWidget(apply_button)
        apply_row.addStretch(1)
        apply_layout.addLayout(apply_row)
        self.body.addWidget(apply_card)

        self.body.addWidget(
            hint(
                "Never distribute a ROM file. Distributing a patch is what keeps "
                "a mod legal to share."
            )
        )

        self.state.romLoaded.connect(self._refresh_estimate)
        self.state.romChanged.connect(self._rom_changed)

    # -- helpers -----------------------------------------------------------

    def _rom_changed(self, _ranges) -> None:
        # Estimating a patch diffs the whole ROM. Only worth doing when the
        # page is on screen; on_activated refreshes it when it appears.
        if self.isVisible():
            self._refresh_estimate()

    def on_activated(self) -> None:
        self._refresh_estimate()
        if not self._name.text() and self.state.rom.header is not None:
            self._name.setText(f"{self.state.rom.header.image_name.title()} mod")

    def _browse(self, target: QLineEdit) -> None:
        start = self.state.settings.get("last_directory", "") or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Select ROM", start, ROM_FILTER)
        if path:
            target.setText(path)
            self._refresh_estimate()

    def _buffers(self) -> Optional[tuple[bytes, bytes]]:
        """The ``(source, target)`` pair the current settings describe."""
        if self._source_working.isChecked():
            if not self.state.rom.is_loaded:
                return None
            return self.state.rom.original, bytes(self.state.rom.data)
        from tools.comparator import ROMComparator

        original = self._original_edit.text().strip()
        modified = self._modified_edit.text().strip()
        if not original or not modified:
            return None
        left, _ = ROMComparator.load_normalised(original)
        right, _ = ROMComparator.load_normalised(modified)
        return left, right

    def _refresh_estimate(self) -> None:
        try:
            buffers = self._buffers()
        except OSError as exc:
            self._estimate.setText(str(exc))
            self._estimate.setStyleSheet(f"color: {theme.COLORS['danger']};")
            return
        if buffers is None:
            self._estimate.setText("Choose what to compare.")
            self._estimate.setStyleSheet(f"color: {theme.COLORS['text_dim']};")
            return
        source, target = buffers
        estimate = PatchBuilder.estimate(source, target)
        if estimate["changed_bytes"] == 0 and not estimate["size_changed"]:
            self._estimate.setText(
                "No differences — a patch would be empty. Make some edits first."
            )
            self._estimate.setStyleSheet(f"color: {theme.COLORS['warning']};")
            return
        text = (
            f"{estimate['regions']:,} changed region(s), "
            f"{estimate['changed_bytes']:,} byte(s), highest change at "
            f"0x{estimate['highest_offset']:X}."
        )
        if estimate["size_changed"]:
            text += f"  ROM size changes: {len(source):,} → {len(target):,} bytes."
        if not estimate["ips_possible"]:
            text += "\nIPS cannot represent these changes (past 16 MiB). Use BPS."
        self._estimate.setText(text)
        self._estimate.setStyleSheet(f"color: {theme.COLORS['text']};")

    def _metadata(self) -> PatchMetadata:
        return PatchMetadata(
            name=self._name.text().strip(),
            version=self._version.text().strip(),
            description=self._description.toPlainText().strip(),
            author=self._author.text().strip(),
            game=(
                self.state.definition.display_name
                if self.state.definition
                else (self.state.rom.header.image_name if self.state.rom.is_loaded else "")
            ),
        )

    # -- actions -----------------------------------------------------------

    def create_patch(self) -> None:
        try:
            buffers = self._buffers()
        except OSError as exc:
            QMessageBox.critical(self, "Patch Builder", str(exc))
            return
        if buffers is None:
            QMessageBox.information(
                self, "Patch Builder", "Choose an original and a modified ROM."
            )
            return
        source, target = buffers
        if source == target:
            QMessageBox.information(
                self,
                "Nothing to patch",
                "The two ROMs are identical, so the patch would be empty.",
            )
            return

        fmt = self._format.currentData()
        suggested = (self._name.text().strip() or "patch").replace(" ", "-").lower()
        path, _ = QFileDialog.getSaveFileName(
            self, "Export patch", f"{suggested}.{fmt}", PATCH_FILTER
        )
        if not path:
            return
        if not Path(path).suffix:
            path = f"{path}.{fmt}"

        builder = PatchBuilder(self._metadata())
        try:
            builder.build_to_file(source, target, path, fmt)
        except PatchTooLargeError as exc:
            QMessageBox.critical(
                self,
                "Cannot create IPS patch",
                f"{exc}\n\nSwitch the format to BPS and try again.",
            )
            return
        except (PatchError, OSError) as exc:
            QMessageBox.critical(self, "Patch creation failed", str(exc))
            return

        size = Path(path).stat().st_size
        QMessageBox.information(
            self,
            "Patch created",
            f"Wrote {path}\n({size:,} bytes)\n\n"
            "Share this file, not the ROM.",
        )
        self.state.status(f"Patch written to {path}", 6000)

    def inspect_patch(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Inspect patch", "", PATCH_FILTER)
        if not path:
            return
        try:
            info = PatchBuilder.describe(Path(path).read_bytes())
        except (PatchError, OSError) as exc:
            QMessageBox.critical(self, "Cannot read patch", str(exc))
            return
        lines = [f"{key}: {value}" for key, value in info.items() if value is not None]
        QMessageBox.information(self, Path(path).name, "\n".join(lines))

    def _mismatch_help(self, payload: bytes, exc: Exception) -> str:
        """Explain a source-checksum mismatch concretely."""
        import zlib

        rom = self.state.rom
        lines = [str(exc), ""]
        loaded = zlib.crc32(rom.original) & 0xFFFFFFFF
        lines.append(f"The ROM you have loaded has CRC32 {loaded:08X}.")
        try:
            described = PatchBuilder.describe(payload)
            expected = described.get("source_crc32")
            if expected:
                lines.append(f"This patch expects a source ROM with CRC32 {expected}.")
            if described.get("source_size") and described["source_size"] != rom.size:
                lines.append(
                    f"It also expects a {described['source_size']:,} byte ROM; "
                    f"yours is {rom.size:,} bytes."
                )
        except PatchError:
            pass
        lines += [
            "",
            "That usually means the patch was built against a different dump "
            "\u2014 another region, revision, or an already-modified ROM.",
        ]
        return "\n".join(lines)

    def apply_patch(self) -> None:
        if not self.state.rom.is_loaded:
            QMessageBox.information(
                self, "Apply patch", "Load the ROM you want to patch first."
            )
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import patch", "", PATCH_FILTER)
        if not path:
            return

        rom = self.state.rom
        # A patch's source is the ROM *as loaded*, never the working copy.
        # Applying it on top of your own edits is what a patch is defined not
        # to mean: a BPS would fail its source checksum, and an IPS would
        # quietly look like a no-op because the edits are already the target.
        if rom.is_modified:
            answer = QMessageBox.question(
                self,
                "Replace your current edits?",
                "A patch applies to the ROM as it was loaded, not on top of "
                "your edits.\n\nApplying it will replace the working copy with "
                "the original ROM plus this patch. Your unsaved changes will be "
                "undone (Ctrl+Z brings them back).\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        try:
            payload = Path(path).read_bytes()
            patched = PatchBuilder.apply(rom.original, payload)
        except PatchMismatchError as exc:
            QMessageBox.critical(
                self, "This patch is for a different ROM", self._mismatch_help(payload, exc)
            )
            return
        except (PatchError, OSError) as exc:
            QMessageBox.critical(self, "Could not apply patch", str(exc))
            return

        if len(patched) != self.state.rom.size:
            QMessageBox.critical(
                self,
                "Cannot apply in place",
                "This patch changes the ROM's size, which the in-place editor "
                "cannot represent. Apply it to a file with a standalone patcher "
                "instead, then open the result here.",
            )
            return

        current = bytes(rom.data)
        ranges = diff_buffers(current, patched, merge_gap=16)
        if not ranges:
            QMessageBox.information(
                self,
                "Nothing to do",
                "The working copy already matches this patch exactly, so there "
                "is nothing to apply.",
            )
            return

        commands = [
            WriteBytesCommand(
                start,
                patched[start:end],
                current[start:end],
                f"Patch 0x{start:06X}",
            )
            for start, end in ranges
        ]
        self.state.rom.apply_command(
            CompositeCommand(commands, f"Apply patch {Path(path).name}")
        )
        QMessageBox.information(
            self,
            "Patch applied",
            f"Applied {len(ranges)} change region(s) to the working copy.\n\n"
            "Use Edit → Undo to reverse it, or File → Save ROM As to keep it.",
        )
