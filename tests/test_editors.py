"""Editors, including the honesty contract: no data means unavailable."""

from __future__ import annotations

import pytest

from core.address_db import GameDefinition
from editors.gameplay_editor import GameplayEditor
from editors.graphics_editor import GraphicsEditor
from editors.roster_editor import RosterEditor
from editors.table_editor import TableEditor
from editors.team_editor import TeamEditor


# -- availability ---------------------------------------------------------


def test_editors_are_unavailable_without_a_rom(demo_definition):
    from core.rom_manager import ROMManager

    empty = ROMManager()
    for editor in (
        TeamEditor(empty, demo_definition),
        RosterEditor(empty, demo_definition),
        GameplayEditor(empty, demo_definition, "passing"),
    ):
        status = editor.availability()
        assert not status
        assert "No ROM is loaded" in status.reason


def test_editors_are_unavailable_without_a_definition(rom):
    status = TeamEditor(rom, None).availability()
    assert not status
    assert "not yet supported" in status.reason
    assert "Hex/Data Explorer" in status.reason


def test_unlocated_table_reports_what_is_missing(rom, builtin_games_dir):
    # NFL Blitz 2000 has not been dumped and mapped here, so its team table is
    # declared but empty.
    blitz = GameDefinition.load(builtin_games_dir / "nfl_blitz_2000.json")
    status = TeamEditor(rom, blitz).availability()
    assert not status
    assert "not yet located" in status.reason
    assert "base address" in status.missing


def test_undiscovered_values_report_what_is_wanted(rom, builtin_games_dir):
    # Gameplay constants are unmapped for every NFL Blitz build, including the
    # USA cartridge whose tables *are* mapped.
    blitz = GameDefinition.load(builtin_games_dir / "nfl_blitz_1997.json")
    editor = GameplayEditor(rom, blitz, "passing")
    status = editor.availability()
    assert not status
    assert "none have been located" in status.reason
    # The wanted list is still exposed, so the UI can show what to look for.
    assert "Short pass maximum distance" in status.missing
    assert len(editor.entries()) > 0
    assert all(not state.available for state in editor.states())


def test_graphics_editor_is_honest_about_being_unimplemented(rom, demo_definition):
    status = GraphicsEditor(rom, demo_definition).availability()
    assert not status
    assert "not implemented yet" in status.reason


def test_table_running_past_the_rom_is_refused(rom, demo_definition):
    broken = GameDefinition.from_dict(demo_definition.to_dict())
    table = broken.table("teams")
    table.base_address = rom.size - 8
    status = TeamEditor(rom, broken).availability()
    assert not status
    assert "past the end of this ROM" in status.reason


# -- team editor ----------------------------------------------------------


def test_team_editor_reads_the_demo_table(rom, demo_definition):
    editor = TeamEditor(rom, demo_definition)
    assert editor.availability()
    assert editor.record_count == 8
    labels = editor.team_labels()
    assert labels[0].endswith("Ashford Anchors")


def test_team_editor_writes_are_undoable(rom, demo_definition):
    editor = TeamEditor(rom, demo_definition)
    editor.write_field(0, "nickname", "Rockets")
    assert editor.read_record(0).values["nickname"] == "Rockets"
    rom.undo_last()
    assert editor.read_record(0).values["nickname"] == "Anchors"


def test_team_record_write_is_one_undo_step(rom, demo_definition):
    editor = TeamEditor(rom, demo_definition)
    editor.write_record(0, {"city": "Zenith", "nickname": "Rockets"})
    assert len(rom.undo.history) == 1
    rom.undo_last()
    assert editor.read_record(0).values["city"] == "Ashford"


def test_colour_round_trip(rom, demo_definition):
    editor = TeamEditor(rom, demo_definition)
    editor.write_color(0, "primary_color", (0, 0, 255))
    red, green, blue = editor.read_color(0, "primary_color")
    # RGBA5551 keeps five bits per channel, so exact blue survives and the
    # other channels stay at zero.
    assert (red, green) == (0, 0)
    assert blue > 240


def test_oversized_team_name_is_refused(rom, demo_definition):
    editor = TeamEditor(rom, demo_definition)
    with pytest.raises(ValueError, match="field holds"):
        editor.write_field(0, "city", "A city name far longer than twelve")


# -- roster editor --------------------------------------------------------


def test_roster_reads_players_and_positions(rom, demo_definition):
    editor = RosterEditor(rom, demo_definition)
    assert editor.record_count == 64
    record = editor.read_record(0)
    assert record.values["name"] == "PLAYER 00"
    assert editor.position_label(record.values["position"]) == "QB"


def test_players_for_team(rom, demo_definition):
    editor = RosterEditor(rom, demo_definition)
    team_zero = editor.players_for_team(0)
    assert len(team_zero) == 8
    assert all(record.values["team"] == 0 for record in team_zero)


def test_move_to_team(rom, demo_definition):
    editor = RosterEditor(rom, demo_definition)
    editor.move_to_team(0, 3)
    assert editor.read_record(0).values["team"] == 3


def test_bulk_adjust_clamps_and_is_one_step(rom, demo_definition):
    editor = RosterEditor(rom, demo_definition)
    indices = list(range(8))
    before = [editor.read_record(i).values["speed"] for i in indices]
    changed = editor.bulk_adjust(indices, "speed", 500)
    assert changed > 0
    assert len(rom.undo.history) == 1
    after = [editor.read_record(i).values["speed"] for i in indices]
    assert all(value == 99 for value in after), "must clamp to the declared maximum"

    rom.undo_last()
    assert [editor.read_record(i).values["speed"] for i in indices] == before


def test_bulk_set(rom, demo_definition):
    editor = RosterEditor(rom, demo_definition)
    editor.bulk_set([0, 1, 2], "strength", 77)
    assert [editor.read_record(i).values["strength"] for i in range(3)] == [77, 77, 77]


def test_attribute_fields_excludes_structural_columns(rom, demo_definition):
    editor = RosterEditor(rom, demo_definition)
    fields = editor.attribute_fields()
    assert "speed" in fields
    assert "name" not in fields and "team" not in fields


def test_csv_round_trip(rom, demo_definition, tmp_path):
    editor = RosterEditor(rom, demo_definition)
    path = editor.export_csv(tmp_path / "roster.csv")
    assert editor.import_csv(path) == 0, "re-importing unchanged data changes nothing"

    rows = path.read_text().splitlines()
    rows[1] = rows[1].replace("PLAYER 00", "NEW NAME")
    path.write_text("\n".join(rows))
    assert editor.import_csv(path) == 1
    assert editor.read_record(0).values["name"] == "NEW NAME"


def test_csv_import_rejects_a_bad_row_without_writing_anything(
    rom, demo_definition, tmp_path
):
    editor = RosterEditor(rom, demo_definition)
    path = editor.export_csv(tmp_path / "roster.csv")
    rows = path.read_text().splitlines()
    rows[1] = rows[1].replace("PLAYER 00", "FIRST EDIT")
    rows[2] = rows[2].split(",")[0] + ",X,not-a-number,0,0,0,0,0,0,0"
    path.write_text("\n".join(rows))

    with pytest.raises(ValueError, match="not a valid value"):
        editor.import_csv(path)
    assert editor.read_record(0).values["name"] == "PLAYER 00", (
        "a failed import must roll back completely"
    )


def test_csv_import_rejects_out_of_range_indices(rom, demo_definition, tmp_path):
    path = tmp_path / "roster.csv"
    path.write_text("Index,Name\n999,NOBODY\n")
    editor = RosterEditor(rom, demo_definition)
    with pytest.raises(ValueError, match="outside 0"):
        editor.import_csv(path)


# -- gameplay editor ------------------------------------------------------


def test_gameplay_reads_and_writes(rom, demo_definition):
    editor = GameplayEditor(rom, demo_definition, "passing")
    assert editor.availability()

    entry = demo_definition.entry("pass_max_long")
    state = editor.state_for(entry)
    assert state.current == 60
    assert state.default_value == 60
    assert not state.modified

    editor.set_value(entry, 99)
    assert editor.state_for(entry).current == 99
    assert editor.state_for(entry).modified
    assert editor.modified_count() == 1


def test_gameplay_respects_declared_bounds(rom, demo_definition):
    editor = GameplayEditor(rom, demo_definition, "passing")
    entry = demo_definition.entry("pass_max_long")
    with pytest.raises(ValueError, match="outside the allowed range"):
        editor.set_value(entry, 500)


def test_gameplay_scaling(rom, demo_definition):
    editor = GameplayEditor(rom, demo_definition, "movement")
    entry = demo_definition.entry("sprint_multiplier")
    assert entry.scale == 0.01
    assert editor.state_for(entry).display_value == pytest.approx(1.5)

    editor.set_display_value(entry, 2.0)
    assert editor.state_for(entry).current == 200


def test_restore_defaults(rom, demo_definition):
    editor = GameplayEditor(rom, demo_definition, "passing")
    entry = demo_definition.entry("pass_max_long")
    editor.set_value(entry, 99)
    editor.restore_default(entry)
    assert editor.state_for(entry).current == 60

    editor.set_value(entry, 99)
    editor.set_value(demo_definition.entry("pass_max_short"), 5)
    assert editor.restore_all_defaults() == 2
    assert editor.modified_count() == 0


def test_undiscovered_entries_cannot_be_written(rom, builtin_games_dir):
    blitz = GameDefinition.load(builtin_games_dir / "nfl_blitz_1997.json")
    editor = GameplayEditor(rom, blitz, "passing")
    entry = blitz.entry("pass_max_long")
    with pytest.raises(ValueError, match="no known address"):
        editor.set_value(entry, 10)


def test_generic_table_editor_works_for_any_declared_table(rom, demo_definition):
    editor = TableEditor(rom, demo_definition, table_id="players")
    assert editor.availability()
    assert editor.record_count == 64

    missing = TableEditor(rom, demo_definition, table_id="nonexistent")
    status = missing.availability()
    assert not status
    assert "does not describe" in status.reason


# -- BCD fields and positional team membership ----------------------------


def _grouped_bcd_definition(rom):
    """A definition shaped like NFL Blitz's roster: BCD numbers, no team field."""
    from core.address_db import FieldDefinition, GameDefinition, TableDefinition
    from core.datatypes import DataType

    return GameDefinition(
        id="grouped",
        game="Grouped",
        tables=[
            TableDefinition(
                id="players",
                name="Players",
                base_address=0x4000,
                record_size=24,
                record_count=64,
                group_size=16,
                confidence="confirmed",
                fields=[
                    FieldDefinition(
                        id="name", name="Name", offset=0, kind="text", length=16
                    ),
                    FieldDefinition(
                        id="number", name="Number", offset=16,
                        data_type=DataType.U8, kind="bcd", minimum=0, maximum=99,
                    ),
                    FieldDefinition(
                        id="speed", name="Speed", offset=19, data_type=DataType.U8
                    ),
                ],
            )
        ],
    )


def test_bcd_field_reads_as_the_displayed_number(rom):
    editor = RosterEditor(rom, _grouped_bcd_definition(rom))
    # 0x22 must read as 22, not 34.
    rom.write_bytes(0x4000 + 16, bytes([0x22]))
    assert editor.read_record(0).values["number"] == 22


def test_bcd_field_writes_back_as_bcd(rom):
    editor = RosterEditor(rom, _grouped_bcd_definition(rom))
    editor.write_field(0, "number", 88)
    assert rom.read_bytes(0x4000 + 16, 1) == b"\x88"
    assert editor.read_record(0).values["number"] == 88


def test_bcd_field_respects_declared_bounds(rom):
    editor = RosterEditor(rom, _grouped_bcd_definition(rom))
    with pytest.raises(ValueError, match="outside the allowed range"):
        editor.write_field(0, "number", 150)


def test_bcd_field_survives_corrupt_data(rom):
    """A nibble above 9 must not stop the record being displayed."""
    editor = RosterEditor(rom, _grouped_bcd_definition(rom))
    rom.write_bytes(0x4000 + 16, bytes([0xAB]))
    assert editor.read_record(0).values["number"] == 0xAB


def test_positional_team_membership(rom):
    editor = RosterEditor(rom, _grouped_bcd_definition(rom))
    assert editor.record_count == 64
    assert [r.index for r in editor.players_for_team(0)] == list(range(16))
    assert [r.index for r in editor.players_for_team(2)] == list(range(32, 48))
    assert editor.team_of(35) == 2


def test_positional_membership_cannot_be_reassigned(rom):
    editor = RosterEditor(rom, _grouped_bcd_definition(rom))
    with pytest.raises(RuntimeError, match="positional"):
        editor.move_to_team(0, 3)


def test_bcd_csv_round_trip(rom, tmp_path):
    editor = RosterEditor(rom, _grouped_bcd_definition(rom))
    editor.write_field(0, "number", 7)
    path = editor.export_csv(tmp_path / "players.csv")
    # A BCD cell is written as the number it displays, and a leading zero must
    # not be misread as an octal prefix on the way back in.
    assert ",7," in path.read_text().splitlines()[1] + ","
    rows = path.read_text().splitlines()
    rows[1] = rows[1].replace(",7,", ",09,")
    path.write_text("\n".join(rows))
    editor.import_csv(path)
    assert editor.read_record(0).values["number"] == 9
