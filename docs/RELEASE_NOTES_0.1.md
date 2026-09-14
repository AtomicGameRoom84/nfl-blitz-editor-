# NFL Blitz Mod Suite 0.1.3 — preview

## Fixed in 0.1.3

Both found by extending the audit to the Tools menu, which nothing had been
exercising.

- **A mistyped address showed a Python error.** Every box that takes an
  address or a value — Go To, Pointer Finder, search, bookmarks, 18 places in
  all — reported `invalid literal for int() with base 10: 'x'`, which tells
  you nothing about what to type instead. It now says what was rejected and
  what is accepted: decimal, `0x`/`$` hex, or `0b` binary.
- **The ROM Scanner looked hung.** Surveying a 16 MiB cartridge takes about
  four seconds with the window frozen. It now shows a wait cursor.

Audit: 51 checks, all passing. Unit tests: 284 passing.

---

## Fixed in 0.1.2

**You could build a patch but not apply it.** Creating a patch worked,
inspecting it worked, applying it failed — a BPS reported *"this patch is for
a different ROM"* and an IPS silently reported *"makes no change"*.

Cause: **Apply Patch** ran the patch against your *working copy* — the ROM
with your edits already in it — instead of against the ROM as loaded. A patch
records the difference from an original, so feeding it a file that already
contains those edits is the one input guaranteed not to match. Patches now
apply to the ROM as loaded, which is what every other patcher does.

Two related improvements came out of it:

- **If a patch really is for a different ROM, it now says so precisely** —
  the CRC32 the patch expects, the CRC32 of the ROM you have open, and what
  that means. Before, you got a bare mismatch error with nothing to act on.
- **Applying a patch over unsaved edits asks first.** Applying replaces the
  working copy, so edits you have not saved would be discarded silently. It
  now warns and lets you cancel.

Regression tests build a patch through the UI and apply it back, in both
formats — verified to fail on the old code and pass on the new.

**A full functional audit.** `python -m tools.audit "NFL Blitz (USA).z64"`
builds the real main window and works through all 15 areas of the app against
a real cartridge — 48 checks covering ROM loading, both editors, search,
bookmarks, comparison, GameShark, patches, save/reload, and undo. All 48 pass.
Unit tests: 281 passing.

The audit also confirms what is *not* claimed: the Graphics, Gameplay, Physics
and Passing editors report their entries as undiscovered and refuse to write,
and the Team Editor shows no colour swatches because NFL Blitz team colours
have not been located.

---

## Fixed in 0.1.1

**The Roster Editor froze the application.** Opening it against a real NFL
Blitz ROM took **167 seconds** — Windows showed *Not Responding* and there was
nothing to do but kill it.

Cause: the table header was set to `ResizeToContents`, which re-measures every
cell in a column on each insert. Filling the 480-row roster made 5,760 cell
inserts at 29 ms each. Columns are now sized once, after the rows are in.

**Opening the Roster Editor: 167s → 0.16s.**

Three more things came out of the same investigation:

- **A refused cell edit hung the app permanently.** Typing a name too long for
  the field, or a jersey number out of range, rebuilt the table from inside
  the cell-changed signal — which deletes the item Qt is still signalling on
  and re-enters the handler. Rejections are now deferred: you get a warning
  and the cell reverts. The GameShark page had the same flaw.
- **Every single edit cost ~3 seconds.** The status bar counted changed bytes
  with a Python loop over all 16.7 million of them, and the Patch Builder
  re-diffed the whole ROM even while hidden. **One edit: 3.14s → 0.30s.**
- **Crashes now leave evidence.** An unhandled error writes
  `%APPDATA%\NFLBlitzModSuite\crash.log` and shows a dialog saying where it
  went, instead of the window vanishing.

Regression tests pin the actual mechanism, not a timing threshold — verified
to fail on the old code and pass on the new.

---

## 0.1.0

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
