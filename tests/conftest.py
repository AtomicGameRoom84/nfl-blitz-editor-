"""Shared fixtures.

Every test runs against a throwaway user data directory so a test run can
never touch (or be influenced by) the developer's real bookmarks, settings
or game definitions.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core import paths  # noqa: E402
from core.address_db import GameDefinition  # noqa: E402
from core.rom_manager import ROMManager  # noqa: E402
from tools.make_demo_rom import DEFINITION_PATH, build_rom  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_user_data(tmp_path, monkeypatch):
    """Point the whole suite's user data directory at a temporary folder."""
    home = tmp_path / "suite-home"
    home.mkdir()
    monkeypatch.setenv(paths.ENV_OVERRIDE, str(home))
    return home


@pytest.fixture(scope="session")
def demo_definition() -> GameDefinition:
    """The bundled definition describing the synthetic demo cartridge."""
    return GameDefinition.load(DEFINITION_PATH)


@pytest.fixture(scope="session")
def demo_rom_bytes(demo_definition) -> bytes:
    """A synthetic but structurally valid N64 ROM, built once per session."""
    return build_rom(demo_definition)


@pytest.fixture
def demo_rom_path(tmp_path, demo_rom_bytes) -> Path:
    path = tmp_path / "demo.z64"
    path.write_bytes(demo_rom_bytes)
    return path


@pytest.fixture
def rom(demo_rom_path) -> ROMManager:
    """A :class:`ROMManager` with the demo cartridge loaded."""
    manager = ROMManager()
    manager.load_file(demo_rom_path)
    return manager


@pytest.fixture
def builtin_games_dir() -> Path:
    return PROJECT_ROOT / "games"
