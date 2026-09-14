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


def self_test(rom_path: str | None = None) -> int:
    """Start up headlessly, then exit. Used by the packaging smoke test.

    A frozen build that cannot find its bundled game definitions, or that
    crashes while constructing a page, fails here rather than in a user's
    hands.
    """
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from core import paths

    app = QApplication([])
    theme.apply_theme(app)
    state = AppState()
    state.settings.set("auto_backup_on_load", False)
    window = MainWindow(state)

    definitions = len(state.address_db.definitions)
    print(f"project root      : {paths.PROJECT_ROOT}")
    print(f"game definitions  : {definitions}")
    print(f"pages             : {len(window._pages)}")
    if definitions == 0:
        print("FAIL: no game definitions were bundled with this build")
        return 1
    if state.address_db.load_errors:
        print("FAIL: definition load errors:", state.address_db.load_errors)
        return 1

    if rom_path and Path(rom_path).is_file():
        try:
            state.load_rom(rom_path)
        except Exception as exc:  # noqa: BLE001 - report, do not mask
            print(f"FAIL: could not load {rom_path}: {exc}")
            return 1
        print(f"loaded ROM        : {Path(rom_path).name} ({state.rom.size} bytes)")
        for key in list(window._pages):
            window.navigate(key)
            app.processEvents()
        print(f"visited all {len(window._pages)} pages")
        state.rom.close()

    print("self-test OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    if "--self-test" in argv:
        rest = [a for a in argv[1:] if a != "--self-test"]
        return self_test(rest[0] if rest else None)

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
