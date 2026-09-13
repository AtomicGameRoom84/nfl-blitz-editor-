"""Bookmarks, the research log and ROM identity."""

from __future__ import annotations

import pytest

from core.bookmarks import Bookmark, BookmarkDatabase
from core.datatypes import DataType, Endian
from core.identity import ROMIdentity
from tools.research import Experiment, ResearchLog


@pytest.fixture
def database(tmp_path) -> BookmarkDatabase:
    return BookmarkDatabase(tmp_path / "bookmarks.json")


def make(name="Speed", address=0x1000, **kwargs) -> Bookmark:
    kwargs.setdefault("data_type", DataType.U16)
    return Bookmark(name=name, address=address, **kwargs)


def test_add_query_and_remove(database):
    bookmark = database.add(make())
    assert len(database) == 1
    assert database.get(bookmark.id) is bookmark
    assert database.remove(bookmark.id)
    assert len(database) == 0


def test_persistence_round_trip(tmp_path):
    path = tmp_path / "bookmarks.json"
    first = BookmarkDatabase(path)
    first.add(make(notes="found by diffing", category="Movement", confidence="tested"))
    first.save()

    second = BookmarkDatabase(path).load()
    assert len(second) == 1
    restored = second.sorted()[0]
    assert restored.notes == "found by diffing"
    assert restored.category == "Movement"
    assert restored.data_type is DataType.U16


def test_query_filters(database):
    database.add(make("Run speed", 0x100, category="Movement"))
    database.add(make("Pass distance", 0x200, category="Passing", rom_key="AAA"))
    database.add(make("Other", 0x300, category="Passing", rom_key="BBB"))

    assert len(database.query(text="speed")) == 1
    assert len(database.query(category="Passing")) == 2
    # Unscoped bookmarks are always visible; the other ROM's are not.
    assert len(database.query(rom_key="AAA")) == 2
    assert len(database.query(rom_key="AAA", include_unscoped=False)) == 1


def test_at_address_covers_the_whole_value(database):
    database.add(make(address=0x100, data_type=DataType.U32))
    assert database.at_address(0x102)
    assert not database.at_address(0x104)


def test_reading_a_bookmark_out_of_a_rom(rom):
    bookmark = Bookmark(name="Run speed", address=0x8000, data_type=DataType.U16)
    assert bookmark.read_from(rom.data) == 100
    bookmark.endian = Endian.LITTLE
    assert bookmark.read_from(rom.data) != 100


def test_reading_past_the_end_is_an_error(rom):
    bookmark = Bookmark(name="Bad", address=rom.size - 1, data_type=DataType.U32)
    with pytest.raises(IndexError, match="past the end"):
        bookmark.read_from(rom.data)


def test_import_is_idempotent(tmp_path, database):
    database.add(make())
    export = database.export_json(tmp_path / "export.json")

    other = BookmarkDatabase(tmp_path / "other.json")
    assert other.import_json(export) == 1
    assert other.import_json(export) == 0  # same ids, already present
    assert len(other) == 1


def test_malformed_rows_are_skipped_not_fatal(tmp_path):
    path = tmp_path / "bookmarks.json"
    path.write_text(
        '{"bookmarks": [{"name": "good", "address": 16, "data_type": "u8"}, '
        '{"name": "bad"}]}'
    )
    database = BookmarkDatabase(path).load()
    assert len(database) == 1


def test_csv_export(tmp_path, database):
    database.add(make("Run speed", 0x100))
    text = database.export_csv(tmp_path / "out.csv").read_text()
    assert "Run speed" in text
    assert "0x00000100" in text


# -- research log ---------------------------------------------------------


def test_research_round_trip(tmp_path):
    path = tmp_path / "experiments.json"
    log = ResearchLog(path)
    log.add(
        Experiment(
            name="Increase player speed",
            address=0x8000,
            original_value=100,
            modified_value=125,
            outcome="confirmed",
            result="Players are visibly faster.",
        )
    )
    log.save()

    reloaded = ResearchLog(path).load()
    assert len(reloaded) == 1
    experiment = reloaded.sorted()[0]
    assert experiment.delta == 25
    assert experiment.outcome == "confirmed"


def test_research_query_and_stats(tmp_path):
    log = ResearchLog(tmp_path / "r.json")
    log.add(Experiment(name="One", outcome="confirmed"))
    log.add(Experiment(name="Two", outcome="no effect"))
    assert len(log.query(outcome="confirmed")) == 1
    assert len(log.query(text="two")) == 1
    assert log.stats()["total"] == 2


def test_research_markdown_export(tmp_path):
    log = ResearchLog(tmp_path / "r.json")
    log.add(
        Experiment(
            name="Ball gravity",
            address=0x8020,
            hypothesis="Lower values float the ball",
            result="Confirmed in game",
            outcome="confirmed",
        )
    )
    text = log.export_markdown(tmp_path / "log.md").read_text()
    assert "## Ball gravity" in text
    assert "0x00008020" in text
    assert "Lower values float the ball" in text


# -- identity -------------------------------------------------------------


def test_identity_is_stable_and_distinguishing(demo_rom_bytes):
    identity = ROMIdentity.from_bytes(demo_rom_bytes)
    assert identity == ROMIdentity.from_bytes(demo_rom_bytes)
    assert identity.game_code == "NDME"
    assert identity.short.startswith("NDME-")

    changed = bytearray(demo_rom_bytes)
    changed[0x2000] ^= 0xFF
    other = ROMIdentity.from_bytes(bytes(changed))
    # The header fingerprint still matches (the edit is in the payload), but
    # the strict file identity does not.
    assert identity.matches(other)
    assert not identity.matches(other, strict=True)
