#!/usr/bin/env python3
"""Build a standalone executable for whatever platform this runs on.

    python packaging/build.py

PyInstaller does not cross-compile, so running this on Linux produces a Linux
binary and running it on Windows produces ``NFLBlitzModSuite.exe``. To get a
Windows build without a Windows machine, use the GitHub Actions workflow in
``.github/workflows/windows-build.yml``.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging" / "nfl_blitz_suite.spec"


def run(command: list[str]) -> None:
    print("$", " ".join(command), flush=True)
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode:
        raise SystemExit(result.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-tests", action="store_true",
                        help="do not run the test suite first")
    parser.add_argument("--clean", action="store_true",
                        help="remove build/ and dist/ before building")
    args = parser.parse_args(argv)

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        raise SystemExit(
            "PyInstaller is not installed. Run: pip install pyinstaller"
        )

    if args.clean:
        for directory in ("build", "dist"):
            shutil.rmtree(ROOT / directory, ignore_errors=True)

    if not args.skip_tests:
        run([sys.executable, "-m", "pytest", "-q"])

    run([sys.executable, "-m", "PyInstaller", str(SPEC), "--noconfirm"])

    produced = sorted((ROOT / "dist").glob("NFLBlitzModSuite*"))
    if produced:
        print("\nBuilt:")
        for path in produced:
            size = path.stat().st_size / (1024 * 1024)
            print(f"  {path}  ({size:.1f} MiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
