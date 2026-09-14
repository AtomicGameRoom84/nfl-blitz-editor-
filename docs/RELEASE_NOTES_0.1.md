# NFL Blitz Mod Suite 0.1.0 — preview

First build you can actually run. Download `NFLBlitzModSuite.exe` below, put it
anywhere, and double-click it. No installer, no Python needed.

You supply your own ROM. Nothing here contains game data.

---

## What works

**ROM handling**
- Opens `.z64`, `.v64` and `.n64`, detecting byte order from the header rather
  than the file extension
- Full N64 header read-out, CIC detection, and boot checksum verification —
  your USA cartridge dump reports `D094B170 / D7C4B5CC` and verifies clean
- Your original file is opened read-only and is never written to. **Save ROM
  As** refuses to overwrite it
- Backups offered on load, SHA-1 indexed so the same ROM is never duplicated
- Boot checksum recalculated on save, so a modified ROM still boots on real
  hardware

**Team Editor** — all 30 teams. City, nickname, both abbreviations, five rating
bars, overall value. Verified against a real USA dump.

**Roster Editor** — all 480 players (30 teams × 16). Names, jersey numbers,
positions, portrait IDs. Edit cells directly, bulk-adjust ratings, filter by
team, import/export CSV.

**Hex / Data Explorer** — the whole ROM, with a live data inspector, modified
bytes highlighted, search, go-to-address, and full undo.

**Value Search** — exact and range search for every integer and float type,
text, hex patterns, wildcards, plus iterative narrowing.

**ROM Comparison** — diff two dumps, with each difference decoded as every type
that fits. This is how you find things.

**Address Bookmarks** — record what you find, then promote a bookmark into the
game definition and it becomes a labelled control.

**GameShark Codes** — parse and explain N64 codes, generate them from a
catalogue of 42 known NFL Blitz runtime addresses, and read the code database
straight out of a GameShark firmware dump you own.

**Patch Builder** — IPS and BPS. Share a patch, never a ROM.

**Research Mode** — a lab notebook for what you tried and what happened.

---

## What does not work yet

Being blunt, because a tool that hides this is worse than useless:

- **No gameplay sliders.** Passing distance, throwing arc, running speed, ball
  gravity — none of these addresses have been found. They appear in the
  Gameplay pages as greyed-out rows marked *not discovered*, which is honest
  rather than broken. Nothing writes to a guessed address.
- **Graphics Editor does nothing.** NFL Blitz's texture layout is unknown and
  the ROM looks like it uses packed or compressed assets. The page says what it
  needs first.
- **The cheat codes are emulator-only.** Fast Passes, Infinite Turbo and the
  rest are *runtime* RAM addresses. You can copy them into an emulator and they
  work, but they cannot be baked into a saved ROM. The app tells you exactly
  why when you try.
- **Only NFL Blitz (USA) is mapped.** Blitz 2000, 2001 and Special Edition load
  fine for hex work but have no data definitions.

---

## Try it without a ROM

The Team, Roster and Gameplay editors all work against a synthetic demo
cartridge that ships with the source (`python tools/make_demo_rom.py demo.z64`).
It is not NFL Blitz and contains no copyrighted data.

---

## Known rough edges

- Windows may warn that the executable is unsigned — it is. There is no code
  signing certificate on this project.
- First launch takes a few seconds while the single-file build unpacks.
- The window expects roughly 1280×800 or larger.

## If it will not start

Run `NFLBlitzModSuite.exe --self-test` from a command prompt. It writes
`self-test-report.txt` next to itself saying what it found. That file is the
useful thing to report.

Settings, bookmarks and research notes live in
`%APPDATA%\NFLBlitzModSuite`.

---

## Helping

The single most valuable thing: **two dumps of the same ROM with exactly one
thing changed in between.** Load them into ROM Comparison and the changed
address falls out. That is how the gameplay constants get found, and it is the
one step that needs someone who can run the game.

See `docs/DISCOVERING_ADDRESSES.md`.
