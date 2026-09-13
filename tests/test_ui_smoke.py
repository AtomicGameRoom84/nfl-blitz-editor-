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

from PySide6.QtWidgets import QApplication  # noqa: E402

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
    assert window.windowTitle() == "NFL Blitz Mod Suite"
