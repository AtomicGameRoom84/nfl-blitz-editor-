# NFL Blitz Mod Suite

A desktop ROM-hacking workbench for the Nintendo 64 version of **NFL Blitz**,
built with Python and PySide6.

Load a legally obtained cartridge dump, explore and edit it without touching
hex by hand, and share your work as an IPS or BPS patch.

> **Teams and rosters for the USA cartridge are mapped and working.** The
> team table (30 teams: names, cities, abbreviations, rating bars) and the
> player table (480 players: names, jersey numbers, positions) were reverse
> engineered from a verified dump and are fully editable — see
> [docs/NFL_BLITZ_USA_MAP.md](docs/NFL_BLITZ_USA_MAP.md).
>
> **Gameplay constants are not mapped, and the suite ships no guesses.**
> Pass distance, speed, gravity and the rest are declared with a null address
> and marked `undiscovered`, so they render as inactive labelled rows rather
> than sliders that quietly write to the wrong place. Finding them is what the
> ROM Comparison, Value Search, Bookmark and Research tools are for — and once
> you find one, promoting a bookmark into a definition turns it into a
> labelled slider with no code changes.
> See [docs/DISCOVERING_ADDRESSES.md](docs/DISCOVERING_ADDRESSES.md).

---

## Windows executable

**[⬇ Download the latest release](../../releases/latest)** — grab
`NFLBlitzModSuite.exe`, double-click it. No installer, no Python required.

Every push is built, tested and smoke-tested on a Windows runner; a successful
build publishes the release automatically, tagged from the version in
`core/version.py`. Individual builds are also kept as Actions artifacts if you
want a specific commit.

New to it? Start with [docs/QUICKSTART.md](docs/QUICKSTART.md).

To build it yourself on a Windows machine:

```bat
packaging\build_windows.bat
```

That installs the dependencies, runs the tests, and writes
`dist\NFLBlitzModSuite.exe`. On any platform, `python packaging/build.py`
does the same for that platform — PyInstaller does not cross-compile, so a
Windows binary has to be built on Windows (which is what the CI workflow is
for).

`NFLBlitzModSuite.exe --self-test` starts the app headlessly and checks it can
find its bundled game definitions; CI runs it against a generated demo ROM so
a broken bundle fails the build rather than reaching a user.

## Running from source

Requires Python 3.10 or newer.

```bash
pip install -r requirements.txt
python main.py
```

You can also pass a ROM on the command line:

```bash
python main.py /path/to/your/nfl-blitz.z64
```

### Try it without a ROM

The repository includes a synthetic demo cartridge generator. It is **not**
NFL Blitz and contains no copyrighted data — it is a structurally valid N64
image built from `games/demo_rom.json` so every editor can be exercised:

```bash
python tools/make_demo_rom.py demo.z64
python main.py demo.z64
```

Open the Team, Roster and Gameplay editors and they work end to end, because
the demo definition genuinely describes where its data lives. It doubles as a
worked example of the definition format.

### Tests

```bash
pip install pytest
python -m pytest
```

The Qt smoke tests run headless (`QT_QPA_PLATFORM=offscreen`) and skip
themselves if PySide6 cannot start.

The unit tests use a small synthetic ROM, so they can run anywhere. For the
other half — the real application driven against a real cartridge — point the
functional audit at your own dump:

```bash
python -m tools.audit "NFL Blitz (USA).z64"
```

It builds the actual main window and works through 15 areas the way a person
would: loading and identifying the ROM, editing a team, filtering and editing
the roster, hex editing, searching, bookmarking and promoting a bookmark to a
definition entry, diffing, GameShark codes, building a patch and applying it
back, saving and reloading, and undo. It exits non-zero if any check fails.

---

## Project layout

```
main.py                     Application entry point
pyproject.toml              Packaging and pytest configuration

core/                       No Qt imports — all independently testable
  byte_order.py             .z64 / .v64 / .n64 detection and conversion
  rom_header.py             The 64-byte N64 cartridge header
  rom_validator.py          Advisory validation with warnings
  crc.py                    N64 boot checksum (CRC1/CRC2) and CIC detection
  identity.py               Fingerprinting one specific ROM image
  datatypes.py              Typed views over raw bytes, number parsing
  undo.py                   Command stack, transactions, dirty tracking
  rom_manager.py            The working copy and every edit made to it
  backup.py                 Timestamped backups of original ROMs
  address_db.py             Game definitions: addresses live in data, not code
  bookmarks.py              The address bookmark database
  patch.py                  IPS and BPS creation and application
  paths.py, settings.py     User data locations and preferences

editors/                    Editor logic, still no Qt
  base.py                   The availability contract
  table_editor.py           Generic fixed-stride record table editor
  team_editor.py            Teams (colours, names) on top of TableEditor
  roster_editor.py          Players (bulk edits, team moves) on top of it
  gameplay_editor.py        Scalar constants driven by the address database
  graphics_editor.py        Not implemented — states what it needs first

tools/                      Research and analysis, no Qt
  gameshark.py              N64 code parsing, generation, RAM->ROM conversion
  gameshark_db.py           Reads the database inside a GameShark firmware dump
  comparator.py             Binary diffing between two ROMs
  search.py                 Value, range, text, pattern and masked search
  scanner.py                Structural survey of an unknown ROM
  pointer_finder.py         Candidate references to an address
  research.py               The experiment log (Research Mode)
  make_demo_rom.py          Builds the synthetic demo cartridge
  audit.py                  End-to-end audit of the app against a real ROM

ui/                         Everything Qt
  theme.py                  Dark palette and stylesheet
  app_state.py              Shared state; bridges core callbacks to signals
  main_window.py            Sidebar, menus, save workflow
  widgets/                  Hex view, data inspector, value row
  pages/                    One module per sidebar page
  dialogs/                  Bookmark, scanner, pointer finder, save summary

games/                      Game definition files (data, not code)
  demo_rom.json             Fully populated — describes the demo cartridge
  nfl_blitz_1997.json       USA cartridge: teams and rosters mapped and
                            fingerprinted; gameplay constants still undiscovered
  nfl_blitz_2000.json       Stub — not yet dumped and mapped
  nfl_blitz_2001.json       Stub
  nfl_blitz_special_edition.json   Stub

packaging/                  PyInstaller spec and build scripts
.github/workflows/          CI: builds and smoke-tests the Windows executable
docs/                       Architecture, discovery guide, roadmap, features
tests/                      206 tests covering core, tools, editors and UI
```

Your bookmarks, research notes, settings, backups and edited game definitions
live in your user data directory, never in this folder:

| Platform | Location |
| --- | --- |
| Windows | `%APPDATA%\NFLBlitzModSuite` |
| macOS | `~/Library/Application Support/NFLBlitzModSuite` |
| Linux | `~/.local/share/NFLBlitzModSuite` |

Override it with the `NFL_BLITZ_SUITE_HOME` environment variable.

---

## Documentation

| Document | What it covers |
| --- | --- |
| [docs/QUICKSTART.md](docs/QUICKSTART.md) | Five minutes from download to a modified ROM |
| [docs/NFL_BLITZ_USA_MAP.md](docs/NFL_BLITZ_USA_MAP.md) | The reverse-engineered ROM map: tables, offsets, field layouts |
| [docs/FEATURES.md](docs/FEATURES.md) | What works today versus what is planned |
| [docs/DISCOVERING_ADDRESSES.md](docs/DISCOVERING_ADDRESSES.md) | How to find the addresses this suite does not yet know |
| [docs/GAME_DEFINITIONS.md](docs/GAME_DEFINITIONS.md) | The definition file format, field by field |
| [docs/GAMESHARK_N64.md](docs/GAMESHARK_N64.md) | N64 GameShark code format, and why a code is usually not a ROM patch |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the layers fit together and why |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Phases, and the plan for reverse engineering the rest |

---

## Legal

You must supply your own ROM, dumped from a cartridge you own. This project
contains no game data, distributes no ROMs, and includes no tools for
obtaining one.

Share modifications as **patches** (IPS/BPS), never as ROM files. A patch
contains only your changes; the person applying it supplies their own dump.
The Patch Builder is built around that rule.

NFL Blitz is a trademark of its respective owners. This project is
unaffiliated fan tooling.
