"""Backups, the ROM scanner and the pointer finder."""

from __future__ import annotations

import pytest

from core.backup import BackupManager
from core.settings import Settings
from tools.pointer_finder import KSEG0_BASE, PointerFinder
from tools.scanner import ROMScanner


# -- backups --------------------------------------------------------------


def test_backup_creates_a_copy(tmp_path, demo_rom_path):
    manager = BackupManager(tmp_path / "backups")
    record = manager.create_backup(demo_rom_path, note="before editing")
    assert record is not None
    assert record.path.read_bytes() == demo_rom_path.read_bytes()
    assert record.note == "before editing"
    assert manager.has_backup_of(demo_rom_path)


def test_identical_backups_are_not_duplicated(tmp_path, demo_rom_path):
    manager = BackupManager(tmp_path / "backups")
    assert manager.create_backup(demo_rom_path) is not None
    assert manager.create_backup(demo_rom_path) is None
    assert len(manager.backups()) == 1


def test_backup_index_survives_a_restart(tmp_path, demo_rom_path):
    directory = tmp_path / "backups"
    BackupManager(directory).create_backup(demo_rom_path)
    assert len(BackupManager(directory).backups()) == 1


def test_restore_writes_where_asked(tmp_path, demo_rom_path):
    manager = BackupManager(tmp_path / "backups")
    record = manager.create_backup(demo_rom_path)
    destination = manager.restore(record, tmp_path / "restored.z64")
    assert destination.read_bytes() == demo_rom_path.read_bytes()
    assert demo_rom_path.exists(), "restoring must not disturb the source"


def test_prune_keeps_the_newest(tmp_path):
    manager = BackupManager(tmp_path / "backups")
    for index in range(5):
        source = tmp_path / f"rom{index}.z64"
        source.write_bytes(bytes([index]) * 1024)
        manager.create_backup(source)
    assert manager.prune(keep=2) == 3
    assert len(manager.backups()) == 2


def test_backing_up_a_missing_file_is_an_error(tmp_path):
    manager = BackupManager(tmp_path / "backups")
    with pytest.raises(FileNotFoundError):
        manager.create_backup(tmp_path / "nope.z64")


# -- settings -------------------------------------------------------------


def test_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(path)
    settings.set("hex_bytes_per_row", 32)
    settings.push_recent_rom(tmp_path / "a.z64")
    settings.save()

    reloaded = Settings(path)
    assert reloaded.get("hex_bytes_per_row") == 32
    assert reloaded.get("recent_roms")[0].endswith("a.z64")


def test_corrupt_settings_fall_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{ this is not json")
    assert Settings(path).get("hex_bytes_per_row") == 16


def test_recent_roms_deduplicate_and_cap(tmp_path):
    settings = Settings(tmp_path / "s.json")
    settings.set("max_recent_roms", 3)
    for index in range(5):
        settings.push_recent_rom(tmp_path / f"rom{index}.z64")
    settings.push_recent_rom(tmp_path / "rom4.z64")
    recent = settings.get("recent_roms")
    assert len(recent) == 3
    assert recent[0].endswith("rom4.z64")


# -- scanner --------------------------------------------------------------


def test_scanner_reports_the_demo_rom_structure(demo_rom_bytes):
    report = ROMScanner().scan(demo_rom_bytes)
    assert report.size == len(demo_rom_bytes)
    assert report.header.image_name == "MOD SUITE DEMO"
    assert report.cic is None  # synthetic boot code, correctly unrecognised
    assert report.total_strings > 0
    assert report.text_clusters, "the team and player name tables should cluster"
    assert report.filler_regions, "a mostly empty ROM has large filler runs"

    text = "\n".join(report.lines())
    assert "MOD SUITE DEMO" in text
    assert "Nothing above identifies game data" in text


def test_scanner_finds_the_player_name_table(demo_rom_bytes):
    report = ROMScanner().scan(demo_rom_bytes)
    starts = [cluster.start for cluster in report.text_clusters]
    # Players live at 0x4000 in the demo definition.
    assert any(0x4000 <= start < 0x5000 for start in starts)


# -- pointer finder -------------------------------------------------------


def test_pointer_finder_matches_both_encodings():
    data = bytearray(0x1000)
    data[0x10:0x14] = (0x800).to_bytes(4, "big")                    # raw offset
    data[0x20:0x24] = (KSEG0_BASE | 0x800).to_bytes(4, "big")       # KSEG0
    hits = PointerFinder(bytes(data)).candidates_for(0x800)
    addresses = {hit.address for hit in hits}
    assert {0x10, 0x20} <= addresses


def test_pointer_finder_honours_a_load_base():
    data = bytearray(0x1000)
    data[0x30:0x34] = (0x80000400 + 0x100).to_bytes(4, "big")
    hits = PointerFinder(bytes(data)).candidates_for(0x100, load_base=0x80000400)
    assert any(hit.address == 0x30 for hit in hits)


def test_pointer_finder_respects_alignment():
    data = bytearray(0x1000)
    data[0x11:0x15] = (0x800).to_bytes(4, "big")  # deliberately unaligned
    assert not PointerFinder(bytes(data)).candidates_for(0x800, alignment=4)
    assert PointerFinder(bytes(data)).candidates_for(0x800, alignment=1)


# -- versioning -----------------------------------------------------------


def test_version_matches_pyproject():
    """A release tag, pyproject and the About box must not drift apart."""
    import tomllib
    from pathlib import Path

    from core.version import __version__

    root = Path(__file__).resolve().parent.parent
    pyproject = tomllib.loads((root / "pyproject.toml").read_text())
    assert pyproject["project"]["version"] == __version__


def test_release_notes_exist_for_the_current_version():
    from pathlib import Path

    from core.version import __version__

    root = Path(__file__).resolve().parent.parent
    major_minor = ".".join(__version__.split(".")[:2])
    notes = root / "docs" / f"RELEASE_NOTES_{major_minor}.md"
    assert notes.is_file(), f"{notes.name} is missing"
    text = notes.read_text()
    # The notes must keep stating what is not finished.
    assert "What does not work yet" in text
    assert "No gameplay sliders" in text
