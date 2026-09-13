#!/usr/bin/env python3
"""NFL Blitz Mod Suite -- application entry point.

Run with:

    python main.py [rom-file]
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from anywhere without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from ui import theme  # noqa: E402
from ui.app_state import AppState  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    app = QApplication(argv)
    app.setApplicationName("NFL Blitz Mod Suite")
    app.setOrganizationName("NFLBlitzModSuite")
    theme.apply_theme(app)

    state = AppState()
    window = MainWindow(state)
    window.show()

    if len(argv) > 1 and Path(argv[1]).is_file():
        window.page("rom").load_rom(argv[1])

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
