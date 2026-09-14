#!/usr/bin/env python3
"""NFL Blitz Mod Suite -- application entry point.

Run with:

    python main.py [rom-file]
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# Allow running from anywhere without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from ui import theme  # noqa: E402
from ui.app_state import AppState  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402


#: The self-test writes here as well as to stdout. A windowed Windows build
#: has no console, so a report file is the only reliable way for CI -- or a
#: user chasing a startup problem -- to see what happened.
SELF_TEST_REPORT = "self-test-report.txt"


def self_test(rom_path: str | None = None) -> int:
    """Start up headlessly, exercise every page, then exit.

    A frozen build that cannot find its bundled game definitions, or that
    crashes while constructing a page, fails here rather than in a user's
    hands.
    """
    import os
    import traceback

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    lines: list[str] = []

    def record(text: str) -> None:
        lines.append(text)
        try:
            print(text, flush=True)
        except Exception:      # no console on a windowed build
            pass

    status = 1
    try:
        from core import paths
        from core.version import full_title

        record(f"build             : {full_title()}")
        record(f"frozen            : {bool(getattr(sys, 'frozen', False))}")
        record(f"project root      : {paths.PROJECT_ROOT}")

        app = QApplication([])
        theme.apply_theme(app)
        state = AppState()
        state.settings.set("auto_backup_on_load", False)
        window = MainWindow(state)

        definitions = len(state.address_db.definitions)
        record(f"game definitions  : {definitions}")
        record(f"pages             : {len(window._pages)}")

        if definitions == 0:
            record("FAIL: no game definitions were bundled with this build")
        elif state.address_db.load_errors:
            record(f"FAIL: definition load errors: {state.address_db.load_errors}")
        else:
            if rom_path and Path(rom_path).is_file():
                state.load_rom(rom_path)
                record(
                    f"loaded ROM        : {Path(rom_path).name} "
                    f"({state.rom.size} bytes)"
                )
                for key in list(window._pages):
                    window.navigate(key)
                    app.processEvents()
                record(f"visited all {len(window._pages)} pages")
                state.rom.close()
            record("self-test OK")
            status = 0
    except Exception:          # noqa: BLE001 - report, never mask
        record("FAIL: unhandled exception")
        lines.append(traceback.format_exc())

    try:
        Path(SELF_TEST_REPORT).write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass
    return status


def install_crash_handler() -> None:
    """Write unhandled exceptions to a log and tell the user where it is.

    Without this a frozen, windowed build simply vanishes, which leaves a
    bug report with nothing in it.
    """
    import traceback

    def hook(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        path = None
        try:
            from core import paths

            path = paths.user_data_dir() / "crash.log"
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"\n===== {datetime.now().isoformat()} =====\n{text}")
        except Exception:  # noqa: BLE001 - the handler must never raise
            pass
        try:
            print(text, file=sys.stderr, flush=True)
        except Exception:
            pass
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            if QApplication.instance() is not None:
                QMessageBox.critical(
                    None,
                    "Something went wrong",
                    "The suite hit an unexpected error.\n\n"
                    f"{exc_type.__name__}: {exc_value}\n\n"
                    + (f"A full report was written to:\n{path}" if path else "")
                    + "\n\nYour ROM file on disk has not been touched.",
                )
        except Exception:  # noqa: BLE001
            pass

    sys.excepthook = hook


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    if "--self-test" in argv:
        rest = [a for a in argv[1:] if a != "--self-test"]
        return self_test(rest[0] if rest else None)

    install_crash_handler()

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
