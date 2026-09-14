"""Game definitions, ROM identification and the discovery pipeline."""

from __future__ import annotations

import json

import pytest

from core.address_db import (
    AddressDatabase,
    GameDefinition,
    Identification,
    ValueEntry,
    entry_from_bookmark,
)
from core.bookmarks import Bookmark
from core.datatypes import DataType
from core.identity import ROMIdentity


def test_bundled_definitions_all_load(builtin_games_dir):
    database = AddressDatabase(builtin_dir=builtin_games_dir).load_all()
    assert database.load_errors == []
    assert "demo_rom" in database.definitions
    assert "nfl_blitz_1997" in database.definitions


def test_no_definition_ships_a_guessed_gameplay_address(builtin_games_dir):
    """Scalar gameplay entries must never carry an unverified address."""
    database = AddressDatabase(builtin_dir=builtin_games_dir).load_all()
    for definition in database.all():
        if definition.id == "demo_rom":
            continue  # the demo ROM is generated from its own definition
        for entry in definition.entries:
            if entry.address is None:
                assert entry.confidence == "undiscovered"
            else:
                assert entry.confidence != "undiscovered", (
                    f"{definition.id}:{entry.id} has an address but is unmarked"
                )


def test_discovered_tables_are_backed_by_a_real_dump(builtin_games_dir):
    """A table may only claim to be located if its ROM was fingerprinted.

    This is what stops a plausible-looking guess being shipped: to mark a
    table discovered you must also have recorded the SHA-1 or boot CRC of the
    dump you verified it against.
    """
    database = AddressDatabase(builtin_dir=builtin_games_dir).load_all()
    for definition in database.all():
        if definition.id == "demo_rom":
            continue
        located = [t for t in definition.tables if t.is_discovered]
        if not located:
            continue
        fingerprinted = bool(
            definition.identification.sha1 or definition.identification.crc_pairs
        )
        assert fingerprinted, (
            f"{definition.id} marks {len(located)} table(s) located but carries "
            "no verified ROM fingerprint"
        )
        for table in located:
            assert table.confidence == "confirmed"
            assert table.notes.strip(), f"{definition.id}:{table.id} needs notes"


def test_unmapped_blitz_versions_stay_empty(builtin_games_dir):
    """The versions nobody has dumped here must still declare nothing."""
    database = AddressDatabase(builtin_dir=builtin_games_dir).load_all()
    for definition_id in ("nfl_blitz_2000", "nfl_blitz_2001",
                          "nfl_blitz_special_edition"):
        definition = database.get(definition_id)
        assert definition.discovered_count == 0
        assert all(not t.is_discovered for t in definition.tables)
        assert not definition.identification.sha1


def test_nfl_blitz_usa_tables_are_described(builtin_games_dir):
    """The structure verified against a real USA cartridge dump."""
    definition = AddressDatabase(builtin_dir=builtin_games_dir).load_all().get(
        "nfl_blitz_1997"
    )
    assert definition.identification.crc_pairs == [[0xD094B170, 0xD7C4B5CC]]

    teams = definition.table("teams")
    assert (teams.base_address, teams.record_size, teams.record_count) == (
        0x000A7CD8, 0x40, 30
    )
    players = definition.table("players")
    assert (players.base_address, players.record_size, players.record_count) == (
        0x0009D070, 0x5C, 480
    )
    # 30 teams x 16 players, grouped positionally.
    assert players.group_size == 16
    assert players.group_count == 30
    assert players.group_of(7 * 16 + 3) == 7

    # The team table's roster pointers must land on the player table, using
    # the RAM-to-ROM delta recorded in the definition's notes.
    assert "0x80241368" in definition.notes

    number = players.field("number")
    assert number.kind == "bcd"
    position = players.field("position")
    assert position.options["values"]["0"] == "QB"
    assert position.options["values"]["3"] == "TE"

    # Player fields must stop before the team table, which begins immediately
    # after the last player record's declared data.
    last_record = players.base_address + players.record_size * (players.record_count - 1)
    end_of_fields = last_record + max(f.offset + f.size for f in players.fields)
    assert end_of_fields <= teams.base_address


def test_every_shipped_definition_is_structurally_valid(builtin_games_dir):
    database = AddressDatabase(builtin_dir=builtin_games_dir).load_all()
    assert database.load_errors == []
    for definition in database.all():
        assert definition.validate() == [], definition.id


def test_validator_catches_overlapping_and_overrunning_fields():
    from core.address_db import FieldDefinition, TableDefinition

    definition = GameDefinition(
        id="x",
        game="X",
        tables=[
            TableDefinition(
                id="t", name="T", base_address=0, record_size=8, record_count=4,
                group_size=3,
                fields=[
                    FieldDefinition(id="a", name="A", offset=0, data_type=DataType.U32),
                    FieldDefinition(id="b", name="B", offset=2, data_type=DataType.U32),
                    FieldDefinition(id="c", name="C", offset=6, data_type=DataType.U32),
                ],
            )
        ],
    )
    problems = " | ".join(definition.validate())
    assert "overlap" in problems
    assert "past the" in problems
    assert "does not divide" in problems


def test_validator_rejects_an_address_free_entry_claiming_confidence():
    definition = GameDefinition(
        id="x", game="X",
        entries=[ValueEntry(id="e", name="E", address=None, confidence="confirmed")],
    )
    assert any("no address but claims confidence" in p for p in definition.validate())


def test_demo_definition_matches_the_demo_rom(builtin_games_dir, demo_rom_bytes):
    database = AddressDatabase(builtin_dir=builtin_games_dir).load_all()
    identity = ROMIdentity.from_bytes(demo_rom_bytes)
    match = database.best_match(identity)
    assert match is not None
    assert match.definition.id == "demo_rom"
    assert match.reasons


def test_unknown_rom_matches_nothing(builtin_games_dir):
    database = AddressDatabase(builtin_dir=builtin_games_dir).load_all()
    identity = ROMIdentity(
        image_name="SOME OTHER GAME",
        game_code="NXXJ",
        crc1=1,
        crc2=2,
        size=1024,
        file_crc32=3,
        sha1="0" * 40,
    )
    assert database.best_match(identity) is None


def test_specific_versions_outrank_the_base_game(builtin_games_dir):
    database = AddressDatabase(builtin_dir=builtin_games_dir).load_all()
    identity = ROMIdentity(
        image_name="NFL BLITZ 2000",
        game_code="NB2E",
        crc1=0,
        crc2=0,
        size=0,
        file_crc32=0,
        sha1="0" * 40,
    )
    match = database.best_match(identity)
    assert match is not None
    assert match.definition.id == "nfl_blitz_2000"


def test_fingerprint_match_outranks_a_name_match():
    definition = GameDefinition(
        id="x",
        game="X",
        identification=Identification(
            crc_pairs=[[0xAAAA, 0xBBBB]], internal_name_matches=["X"]
        ),
    )
    identity = ROMIdentity("X", "NXXE", 0xAAAA, 0xBBBB, 100, 0, "0" * 40)
    result = definition.match(identity)
    assert result is not None and result.exact


def test_undiscovered_entries_are_reported_as_such():
    entry = ValueEntry(id="speed", name="Speed")
    assert not entry.is_discovered
    assert entry.address_hex == "-"
    assert not entry.is_verified


def test_registering_a_fingerprint_forks_into_user_data(builtin_games_dir, demo_rom_bytes):
    database = AddressDatabase(builtin_dir=builtin_games_dir).load_all()
    definition = database.get("demo_rom")
    assert not definition.user_defined

    identity = ROMIdentity.from_bytes(demo_rom_bytes)
    updated = database.register_fingerprint(definition, identity)

    assert updated.user_defined
    assert updated.source_path.parent == database.user_dir
    assert [identity.crc1, identity.crc2] in updated.identification.crc_pairs
    assert identity.sha1 in updated.identification.sha1

    # The bundled file is untouched.
    original = json.loads((builtin_games_dir / "demo_rom.json").read_text())
    assert original["identification"]["crc_pairs"] == []

    # And on reload the user copy wins, now as an exact match.
    reloaded = AddressDatabase(
        builtin_dir=builtin_games_dir, user_dir=database.user_dir
    ).load_all()
    assert reloaded.best_match(identity).exact


def test_promoting_a_bookmark_creates_an_editable_entry(builtin_games_dir):
    database = AddressDatabase(builtin_dir=builtin_games_dir).load_all()
    definition = database.get("nfl_blitz_1997")
    assert definition.discovered_count == 0

    bookmark = Bookmark(
        name="Player running speed",
        address=0x1234,
        data_type=DataType.U16,
        category="Movement",
        confidence="tested",
        default_value=100,
        notes="Found by comparing two dumps.",
    )
    updated = database.add_entry(definition, entry_from_bookmark(bookmark, "movement"))

    entry = updated.entry("player_running_speed")
    assert entry is not None
    assert entry.address == 0x1234
    assert entry.category == "movement"
    assert entry.confidence == "tested"
    assert updated.user_defined
    assert updated.discovered_count == 1

    # The shipped stub is still address-free.
    shipped = GameDefinition.load(builtin_games_dir / "nfl_blitz_1997.json")
    assert shipped.discovered_count == 0


def test_removing_an_entry(builtin_games_dir):
    database = AddressDatabase(builtin_dir=builtin_games_dir).load_all()
    definition = database.get("demo_rom")
    updated = database.remove_entry(definition, "player_run_speed")
    assert updated.entry("player_run_speed") is None


def test_future_schema_versions_are_refused(tmp_path):
    path = tmp_path / "future.json"
    path.write_text(json.dumps({"schema_version": 99, "id": "future", "game": "Future"}))
    with pytest.raises(ValueError, match="schema version"):
        GameDefinition.load(path)


def test_broken_definition_files_are_reported_not_fatal(tmp_path, builtin_games_dir):
    (tmp_path / "broken.json").write_text("{ not json")
    database = AddressDatabase(builtin_dir=builtin_games_dir, user_dir=tmp_path).load_all()
    assert any("broken.json" in error for error in database.load_errors)
    assert "demo_rom" in database.definitions  # the good ones still loaded


def test_entry_bounds_fall_back_to_the_data_type():
    entry = ValueEntry(id="x", name="X", data_type=DataType.U8)
    assert entry.effective_bounds() == (0.0, 255.0)
    entry.minimum, entry.maximum = 10, 20
    assert entry.effective_bounds() == (10.0, 20.0)


def test_table_record_offsets():
    from core.address_db import TableDefinition

    table = TableDefinition(
        id="t", name="T", base_address=0x1000, record_size=16, record_count=4
    )
    assert table.record_offset(2) == 0x1020
    with pytest.raises(IndexError):
        table.record_offset(4)
