"""Single source of truth for the application version."""

from __future__ import annotations

#: Semantic version. Keep in step with ``pyproject.toml`` and the git tag.
__version__ = "0.1.0"

#: Shown in the title bar and the About box.
APP_NAME = "NFL Blitz Mod Suite"

#: A short label describing how finished this build is.
RELEASE_STAGE = "preview"


def version_string() -> str:
    return f"{__version__} {RELEASE_STAGE}".strip()


def full_title() -> str:
    return f"{APP_NAME} {version_string()}"
