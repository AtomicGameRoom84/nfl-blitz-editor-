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


def test_blitz_definitions_claim_no_verified_addresses(builtin_games_dir):
    """The shipped NFL Blitz files must not contain guessed addresses."""
    database = AddressDatabase(builtin_dir=builtin_games_dir).load_all()
    for definition in database.all():
        if not definition.id.startswith("nfl_blitz"):
            continue
        assert definition.discovered_count == 0, (
            f"{definition.id} ships an address that has not been verified"
        )
        for entry in definition.entries:
            assert entry.confidence == "undiscovered"
        for table in definition.tables:
            assert not table.is_discovered


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
