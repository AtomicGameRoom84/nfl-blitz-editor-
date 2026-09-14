"""Smoke tests for the Qt layer.

These do not try to test widget internals; they check that every page can be
built, shown and driven for a loaded ROM without raising -- which is what
catches the layout and signal-wiring mistakes that unit tests on ``core``
never see.

The tests are skipped when Qt cannot start (no display and no offscreen
platform plugin), so a headless CI box without Qt's runtime libraries still
runs the rest of the suite.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 is not installed")

from PySide6.QtWidgets import QApplication, QSpinBox  # noqa: E402

from core.bookmarks import Bookmark  # noqa: E402
from core.datatypes import DataType  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    from ui import theme

    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception as exc:  # pragma: no cover - environment dependent
            pytest.skip(f"cannot start Qt: {exc}")
    theme.apply_theme(app)
    return app


@pytest.fixture
def window(qt_app, demo_rom_path):
    from ui.app_state import AppState
    from ui.main_window import MainWindow

    state = AppState()
    state.settings.set("auto_backup_on_load", False)
    window = MainWindow(state)
    window.resize(1280, 800)
    window.page("rom").load_rom(str(demo_rom_path))
    yield window
    # Discard the ROM first: closeEvent puts up a modal "unsaved changes"
    # dialog for a dirty working copy, which would hang a headless run.
    window.state.rom.close()
    window.close()


def test_every_page_builds_and_activates(window, qt_app):
    for key in list(window._pages):
        window.navigate(key)
        qt_app.processEvents()
        assert window.stack.currentWidget() is window.page(key)


def test_rom_is_identified_in_the_ui(window):
    assert window.state.rom.is_loaded
    assert window.state.definition is not None
    assert window.state.definition.id == "demo_rom"
    assert "demo.z64" in window.windowTitle()


def test_hex_view_navigation_and_inspector(window, qt_app):
    window.navigate("hex")
    page = window.page("hex")
    page.show_address(0x8000, 2)
    qt_app.processEvents()
    assert page.hex_view.cursor_offset == 0x8000
    assert page.hex_view.selection == (0x8000, 0x8002)

    page._find_edit.setText('"MOD SUITE DEMO CARTRIDGE"')
    page.find_next()
    assert page.hex_view.cursor_offset == 0x9000


def test_hex_editing_goes_through_undo(window, qt_app):
    window.navigate("hex")
    page = window.page("hex")
    page.show_address(0x2000, 1)
    before = window.state.rom.read_bytes(0x2000, 1)
    page.hex_view._write_byte(0x2000, 0xAB)
    assert window.state.rom.read_bytes(0x2000, 1) == b"\xab"
    window.undo()
    assert window.state.rom.read_bytes(0x2000, 1) == before


def test_gameplay_page_renders_rows_and_edits(window, qt_app):
    window.navigate("passing")
    page = window.page("passing")
    qt_app.processEvents()
    assert "pass_max_long" in page._rows

    entry = window.state.definition.entry("pass_max_long")
    page._value_changed(entry, 99)
    assert window.state.rom.read_value(entry.address, entry.data_type, entry.endian) == 99


def test_gameplay_page_shows_a_banner_for_an_unsupported_rom(window, qt_app, builtin_games_dir):
    from core.address_db import GameDefinition

    window.state.set_definition(GameDefinition.load(builtin_games_dir / "nfl_blitz_1997.json"))
    window.navigate("passing")
    qt_app.processEvents()
    page = window.page("passing")
    assert page._banner.isVisible() or not page._banner.isHidden()


def test_team_page_edits_a_record(window, qt_app):
    window.navigate("teams")
    page = window.page("teams")
    qt_app.processEvents()
    page._team_picker.setCurrentIndex(1)
    page.load_team()
    page._controls["nickname"].setText("Rockets")
    page.save_team()
    assert page.editor.read_record(1).values["nickname"] == "Rockets"


def test_roster_page_lists_players_and_shows_enum_labels(window, qt_app):
    window.navigate("roster")
    page = window.page("roster")
    qt_app.processEvents()
    assert page._table.rowCount() == 64
    position_column = page._field_ids.index("position") + 1
    assert page._table.item(0, position_column).text() == "QB"


def test_search_page_finds_a_known_value(window, qt_app):
    window.navigate("search")
    page = window.page("search")
    page._mode.setCurrentIndex(0)
    page._mode_changed()
    page._value_edit.setText("100")
    page._type.setCurrentIndex(2)  # u16
    page.run_search()
    assert "match(es)" in page._summary.text()
    assert page._table.rowCount() > 0


def test_compare_page_diffs_the_working_copy(window, qt_app, demo_rom_path):
    window.state.rom.write_value(0x8000, 1024, DataType.U16)
    window.navigate("compare")
    page = window.page("compare")
    page._left_edit.setText(str(demo_rom_path))
    page._use_working_copy()
    page.run_comparison()
    qt_app.processEvents()
    assert page._table.rowCount() == 1
    assert "1 differing region" in page._summary.text()


def test_bookmarks_page_lists_and_promotes(window, qt_app):
    window.state.bookmarks.add(
        Bookmark(
            name="Test speed",
            address=0x8000,
            data_type=DataType.U16,
            category="Movement",
            confidence="tested",
            rom_key=window.state.rom_key,
        )
    )
    window.navigate("bookmarks")
    page = window.page("bookmarks")
    qt_app.processEvents()
    assert page._table.rowCount() == 1
    # The current value is read live out of the ROM.
    assert page._table.item(0, 4).text() == "100"


def test_patch_page_estimates_and_builds(window, qt_app, tmp_path):
    from core.patch import PatchBuilder

    window.state.rom.write_value(0x8000, 150, DataType.U16)
    window.navigate("patch")
    page = window.page("patch")
    page._refresh_estimate()
    assert "changed region" in page._estimate.text()

    built = PatchBuilder(page._metadata()).build_to_file(
        window.state.rom.original, bytes(window.state.rom.data), tmp_path / "m.bps"
    )
    assert PatchBuilder.apply(window.state.rom.original, built.read_bytes()) == bytes(
        window.state.rom.data
    )


def test_graphics_page_states_that_it_is_unimplemented(window, qt_app):
    window.navigate("graphics")
    qt_app.processEvents()
    page = window.page("graphics")
    assert not page.editor.availability()


def test_pages_survive_closing_the_rom(window, qt_app):
    window.state.close_rom()
    for key in list(window._pages):
        window.navigate(key)
        qt_app.processEvents()
    assert not window.state.rom.is_loaded
    # With no ROM open the title falls back to the versioned application name.
    from core.version import full_title

    assert window.windowTitle() == full_title()


# -- wide integer fields --------------------------------------------------


def test_wide_fields_do_not_use_a_spin_box(qt_app):
    """An unsigned 32-bit field must not go through a QSpinBox.

    Qt spin boxes top out at 2**31-1, so a KSEG0 pointer like 0x802DE3D8
    would be clamped and the ROM corrupted on save.
    """
    from ui.widgets.number_edit import NumberEdit, fits_in_spinbox

    assert fits_in_spinbox(0, 99)
    assert fits_in_spinbox(-100, 100)
    assert not fits_in_spinbox(0, 0xFFFFFFFF)

    edit = NumberEdit()
    edit.setValue(0x802DE3D8)
    assert edit.text() == "0x802DE3D8"
    assert edit.value() == 0x802DE3D8
    edit.setText("2148274136")
    assert edit.value() == 2148274136


def test_wide_field_reports_a_typo_instead_of_writing_zero(qt_app):
    from ui.widgets.number_edit import NumberEdit

    edit = NumberEdit()
    edit.setText("not a number")
    with pytest.raises(ValueError):
        edit.value()


def test_team_page_uses_a_number_edit_for_a_pointer_field(window, qt_app, builtin_games_dir):
    """Drive the real NFL Blitz table layout through the Team Editor form."""
    from core.address_db import GameDefinition
    from ui.widgets.number_edit import NumberEdit

    blitz = GameDefinition.load(builtin_games_dir / "nfl_blitz_1997.json")
    # Point the team table somewhere inside the demo ROM so the editor runs;
    # the values read are meaningless, the widget wiring is what is under test.
    blitz.table("teams").base_address = 0x2000
    blitz.table("teams").record_count = 4
    blitz.table("players").base_address = 0x4000
    blitz.table("players").record_count = 16
    blitz.table("cities_uppercase").base_address = 0x9000
    blitz.table("cities_uppercase").record_count = 1
    window.state.set_definition(blitz)
    window.navigate("teams")
    qt_app.processEvents()

    page = window.page("teams")
    assert page.editor.availability()
    assert isinstance(page._controls["roster_pointer"], NumberEdit)
    assert isinstance(page._controls["rating_passing"], QSpinBox)


def test_about_box_reports_the_version_and_the_caveats(qt_app):
    """The About box must state the version and what is not finished."""
    from PySide6.QtWidgets import QLabel

    from core.version import version_string
    from ui.dialogs.common import AboutDialog

    dialog = AboutDialog()
    text = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert version_string() in text
    assert "not yet located" in text
    assert "not implemented" in text


# -- big-table performance and edit safety --------------------------------
#
# The demo ROM has 64 players, so none of the tests above exercised the size
# that actually mattered: the real NFL Blitz roster is 480 records, and
# filling it through a ResizeToContents header took over two and a half
# minutes, which reads as a frozen application. These tests pin the shape of
# the problem rather than the exact timing.


def _big_roster_definition(builtin_games_dir):
    """A 480-record roster laid over the demo ROM, matching the real size."""
    from core.address_db import GameDefinition

    definition = GameDefinition.load(builtin_games_dir / "demo_rom.json")
    players = definition.table("players")
    players.record_count = 480
    players.base_address = 0x1000
    players.group_size = 16
    return definition


def test_roster_never_fills_a_table_in_resize_to_contents_mode(
    window, qt_app, builtin_games_dir, monkeypatch
):
    """The precise mechanism behind the 167-second roster freeze.

    QHeaderView.ResizeToContents re-measures every cell in a column on each
    insert. Filling the real 480-row roster made 5,760 setItem calls at 29 ms
    each. A wall-clock assertion does not reproduce this reliably on a
    smaller table, so this pins the cause directly: no insert may happen
    while the header is in that mode.
    """
    from PySide6.QtWidgets import QHeaderView, QTableWidget

    observed = []
    original_set_item = QTableWidget.setItem

    def spy(self, row, column, item):
        header = self.horizontalHeader()
        if header.count():
            observed.append(header.sectionResizeMode(column))
        return original_set_item(self, row, column, item)

    monkeypatch.setattr(QTableWidget, "setItem", spy)

    window.state.set_definition(_big_roster_definition(builtin_games_dir))
    window.navigate("roster")
    qt_app.processEvents()
    page = window.page("roster")
    page.rebuild()
    qt_app.processEvents()

    assert page._table.rowCount() == 480
    assert observed, "no cells were inserted, so nothing was actually tested"
    assert QHeaderView.ResizeToContents not in observed, (
        "cells were inserted while the header was in ResizeToContents mode, "
        "which is what made the roster take minutes to open"
    )


def test_large_roster_opens_promptly(window, qt_app, builtin_games_dir):
    """Loose upper bound, as a backstop to the mechanism test above."""
    import time

    window.state.set_definition(_big_roster_definition(builtin_games_dir))
    window.navigate("roster")
    qt_app.processEvents()

    page = window.page("roster")
    started = time.monotonic()
    page.rebuild()
    qt_app.processEvents()
    elapsed = time.monotonic() - started

    assert page._table.rowCount() == 480
    assert elapsed < 10.0, f"filling 480 rows took {elapsed:.1f}s"


def test_editing_a_large_roster_cell_is_prompt(window, qt_app, builtin_games_dir):
    import time

    window.state.set_definition(_big_roster_definition(builtin_games_dir))
    window.navigate("roster")
    qt_app.processEvents()
    page = window.page("roster")

    name_column = page._field_ids.index("name") + 1
    started = time.monotonic()
    page._table.item(0, name_column).setText("SMITH")
    qt_app.processEvents()
    elapsed = time.monotonic() - started

    assert page.editor.read_record(0).values["name"] == "SMITH"
    assert elapsed < 5.0, f"one cell edit took {elapsed:.1f}s"


def test_rejected_cell_edit_does_not_reenter_the_table(window, qt_app, builtin_games_dir, monkeypatch):
    """A refused edit must warn and revert, not rebuild from inside the signal.

    Rebuilding the table inside ``itemChanged`` deletes the item Qt is
    mid-signal on, which previously hung the application.
    """
    from PySide6.QtWidgets import QMessageBox

    warnings = []
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a))
    )

    window.state.set_definition(_big_roster_definition(builtin_games_dir))
    window.navigate("roster")
    qt_app.processEvents()
    page = window.page("roster")

    name_column = page._field_ids.index("name") + 1
    before = page.editor.read_record(0).values["name"]

    # 40 characters cannot fit the 16-byte field.
    page._table.item(0, name_column).setText("A" * 40)
    qt_app.processEvents()
    qt_app.processEvents()      # let the deferred handler run

    assert warnings, "the user was never told the edit was refused"
    assert page.editor.read_record(0).values["name"] == before
    assert page._table.item(0, name_column).text() == before


def test_bad_number_in_a_cell_is_refused_cleanly(window, qt_app, builtin_games_dir, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    warnings = []
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a))
    )
    window.state.set_definition(_big_roster_definition(builtin_games_dir))
    window.navigate("roster")
    qt_app.processEvents()
    page = window.page("roster")

    number_column = page._field_ids.index("number") + 1
    before = page.editor.read_record(1).values["number"]
    page._table.item(1, number_column).setText("banana")
    qt_app.processEvents()
    qt_app.processEvents()

    assert warnings
    assert page.editor.read_record(1).values["number"] == before


def test_bulk_update_suspends_resize_to_contents(qt_app):
    """The helper must neutralise the mode even if the caller set it."""
    from PySide6.QtWidgets import QHeaderView, QTableWidget

    from ui.widgets.table_utils import bulk_update

    table = QTableWidget(3, 2)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    with bulk_update(table):
        assert table.horizontalHeader().sectionResizeMode(0) != (
            QHeaderView.ResizeToContents
        )


def test_table_helpers_restore_state(qt_app):
    from PySide6.QtWidgets import QTableWidget

    from ui.widgets.table_utils import bulk_update, fit_columns

    table = QTableWidget(3, 2)
    assert not table.signalsBlocked()
    with bulk_update(table):
        assert table.signalsBlocked()
    assert not table.signalsBlocked()

    # Even when the body raises, the table must not be left mute.
    with pytest.raises(RuntimeError):
        with bulk_update(table):
            raise RuntimeError("boom")
    assert not table.signalsBlocked()

    fit_columns(table, stretch_column=1)


# -- patch round trip through the UI --------------------------------------


@pytest.mark.parametrize("fmt", ["bps", "ips"])
def test_patch_created_in_the_ui_can_be_applied_back(
    window, qt_app, tmp_path, demo_rom_path, fmt, monkeypatch
):
    """Create a patch from edits, reload clean, apply it, get the edits back.

    This is the flow that was broken: apply_patch fed the *working copy* to
    the patcher instead of the ROM as loaded, so a BPS failed its source
    checksum and an IPS looked like a no-op.
    """
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from core.datatypes import DataType
    from core.patch import PatchBuilder

    messages = []
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: messages.append(a))
    )
    monkeypatch.setattr(
        QMessageBox, "critical",
        staticmethod(lambda *a, **k: pytest.fail(f"apply reported an error: {a}")),
    )
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes)
    )

    state = window.state
    state.rom.write_value(0x8000, 4242, DataType.U16)
    target = bytes(state.rom.data)

    patch_path = tmp_path / f"mod.{fmt}"
    PatchBuilder().build_to_file(state.rom.original, target, patch_path, fmt)
    assert patch_path.stat().st_size > 0

    # Crucially, do NOT reload: apply while the working copy still has edits.
    # That is the condition the bug needed -- feeding the working copy to the
    # patcher made a BPS fail its source checksum and an IPS a silent no-op.
    # A second, unrelated edit keeps the working copy distinct from both the
    # original and the patch's target.
    state.rom.write_value(0x9000, 1111, DataType.U16)
    assert state.rom.is_modified
    assert bytes(state.rom.data) != target

    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(patch_path), "")),
    )
    window.navigate("patch")
    qt_app.processEvents()
    window.page("patch").apply_patch()
    qt_app.processEvents()

    assert bytes(state.rom.data) == target, "the patch did not reproduce the edits"
    assert state.rom.read_value(0x8000, DataType.U16) == 4242
    # The unrelated edit is gone: a patch applies to the ROM as loaded.
    assert state.rom.read_value(0x9000, DataType.U16) != 1111
    assert messages, "the user was told nothing"

    # And it is one undoable step. Undoing restores the working copy exactly
    # as it stood before the patch, including the unrelated edit; the earlier
    # 0x8000 edit is a separate step and stays applied.
    window.undo()
    assert state.rom.read_value(0x9000, DataType.U16) == 1111
    assert state.rom.read_value(0x8000, DataType.U16) == 4242


def test_applying_a_patch_for_another_rom_is_refused_clearly(
    window, qt_app, tmp_path, monkeypatch
):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from core.patch import create_bps

    errors = []
    monkeypatch.setattr(
        QMessageBox, "critical", staticmethod(lambda *a, **k: errors.append(a[2]))
    )
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes)
    )

    # A patch built against a completely different source.
    other = bytes(range(256)) * 64
    patch_path = tmp_path / "wrong.bps"
    patch_path.write_bytes(create_bps(other, bytes(reversed(other))))

    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(patch_path), "")),
    )
    window.navigate("patch")
    qt_app.processEvents()
    before = bytes(window.state.rom.data)
    window.page("patch").apply_patch()
    qt_app.processEvents()

    assert bytes(window.state.rom.data) == before, "the ROM was modified anyway"
    assert errors, "the user was not told the patch was rejected"
    assert "CRC32" in errors[0]
