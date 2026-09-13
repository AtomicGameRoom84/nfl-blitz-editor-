"""Where the suite keeps user data.

User data (bookmarks, research notes, custom game definitions, settings)
lives outside the installation directory so it survives updates and so the
application never needs write access to its own source tree.

The location can be overridden with ``NFL_BLITZ_SUITE_HOME``, which the test
suite uses to keep runs hermetic.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "NFLBlitzModSuite"
ENV_OVERRIDE = "NFL_BLITZ_SUITE_HOME"

#: Directory of the installed/checked-out application.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: Game definition files shipped with the application (read only).
BUILTIN_GAMES_DIR = PROJECT_ROOT / "games"


def user_data_dir() -> Path:
    """Return (and create) the per-user data directory."""
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        base = Path(override).expanduser()
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_NAME
    elif os.uname().sysname == "Darwin":  # pragma: no cover - platform specific
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = Path(
            os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
        ) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def _subdir(name: str) -> Path:
    path = user_data_dir() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def backups_dir() -> Path:
    """Default destination for automatic ROM backups."""
    return _subdir("backups")


def user_games_dir() -> Path:
    """User-authored / user-edited game definition files.

    Definitions here override built-ins with the same ``id``, which is how
    a researcher's discoveries get picked up without editing the repository.
    """
    return _subdir("games")


def bookmarks_dir() -> Path:
    return _subdir("bookmarks")


def research_dir() -> Path:
    return _subdir("research")


def settings_file() -> Path:
    return user_data_dir() / "settings.json"
