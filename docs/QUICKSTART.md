# Quick start

Five minutes from download to a modified ROM running in an emulator.

## 0. What you need

- `NFLBlitzModSuite.exe` — from the repository's **Actions** tab, newest green
  *Windows build* run, artifact `NFLBlitzModSuite-windows`. Unzip it anywhere.
- **Your own NFL Blitz ROM.** The suite ships no game data. A USA cartridge
  dump (`NFL Blitz (USA).z64`, 16 MiB) is the version whose teams and rosters
  are mapped.
- An N64 emulator to test in (Project64, Mupen64Plus, RetroArch…).

Double-click the exe. No installer. Windows may warn that it is unsigned — it
is; there is no signing certificate on this project.

---

## 1. Open your ROM

**ROM Manager** is the page you land on.

1. Click **Open ROM…** and pick your `.z64` / `.v64` / `.n64` file.
2. It offers to make a backup. Say yes — it costs nothing and a personal
   cartridge dump is hard to replace.
3. Check the **ROM STATUS** card. For a good USA dump you should see:

   ```
   Loaded      NFL BLITZ
   Region      USA (0x45)
   Size        16,384 KB
   Boot CRC    D094B170 / D7C4B5CC   ✓ matches contents
   CIC chip    6102
   Status      Ready for editing
   ```

4. **DETECTED GAME VERSION** should say *exact fingerprint match*. If it says
   *heuristic match*, your dump differs from the one that was mapped — the
   editors will still open but the addresses may not line up. Click
   **Register this ROM's fingerprint** only once you have confirmed the data
   looks right in the Roster Editor.

> Your original file is opened read-only and is **never** written to. Saving
> always goes through *Save ROM As*, which refuses to overwrite it.

---

## 2. Edit a roster

**Roster Editor** in the sidebar.

- Pick a team from the **Team** drop-down (all 30 are there).
- The table shows that team's 16 players. Click any cell and type.
  - **First name / Last name** — plain text. Must fit the field the ROM
    allocates (16 bytes); a name that is too long is refused rather than
    silently cut off.
  - **Jersey number** — type the number as you would write it (`22`, not
    `0x22`). The ROM stores these as binary-coded decimal; the editor handles
    that.
  - **Position** — type the label (`QB`, `RB`, `WR`, `TE`, `OL`, `K`, `LB`,
    `CB`, `DL`, `S`) or the raw number.
- Select several rows and use **BULK EDIT SELECTED PLAYERS** to shift a rating
  across a whole unit — set *Field* to `Speed`, *Adjust by* to `5`, then
  **Apply adjustment**.
- **Ctrl+Z** undoes anything, including a whole bulk edit in one step.

Players cannot be moved between teams: in this ROM a player's team is decided
by their slot in the table, so "moving" one would mean swapping records. The
app tells you this rather than pretending.

### Roster CSV

**Export roster CSV…** writes every player out. Edit in Excel or Sheets, then
**Import roster CSV…**. Match by the `Index` column. If any row is invalid the
whole import is rejected and nothing is written — no half-applied rosters.

---

## 3. Edit a team

**Team Editor**.

Pick a team, change **City**, **Nickname**, **City abbreviation** (3
characters, e.g. `ARZ`) or the rating bars, then click **Save Team**. Unlike
the roster table, the team form only commits when you press that button.

- **Reset Changes** re-reads the form from the working copy.
- **Revert this team to the original ROM** undoes everything for that team.

The five rating bars run 0–5. Only the first two are identified — *Passing*
and *Rushing* — the rest are labelled neutrally because their on-screen meaning
was never confirmed.

---

## 4. Save and test

**File → Save ROM As…** (or the button on ROM Manager).

1. A **MODIFICATION SUMMARY** appears: how many regions and bytes changed.
2. Leave **Recalculate the N64 boot checksum** ticked. Emulators mostly do not
   care; real hardware and strict flash carts do.
3. Pick a *new* filename. It will not let you overwrite the ROM you loaded.
4. Open the result in your emulator.

---

## 5. Share it as a patch, not a ROM

**Patch Builder**.

1. Leave the first option selected: *the loaded ROM as opened → your working
   copy*.
2. Fill in **Patch name**, **Version**, **Author**.
3. Format: **BPS** (recommended — it stores checksums, so applying it to the
   wrong ROM is caught).
4. **Export patch…**

Send that file. The person applying it supplies their own cartridge dump. Never
distribute the ROM itself.

---

## 6. Cheats you can use right now

**GameShark Codes** in the sidebar.

The top table lists 42 known NFL Blitz runtime addresses taken from the
GameShark Pro device database — *Fast Passes*, *Infinite Turbo*, *Big Football*,
the hidden characters, and so on. Edit the **Value** column (`1` = player 1,
`2` = player 2, `3` = both), select the rows you want, and
**Copy codes for selected rows**. Paste into your emulator's cheat window.

For example, Fast Passes for both players:

```
802997E3 0003
```

**These are RAM addresses, not ROM offsets.** They change the game while it
runs; they cannot be baked into a saved ROM. If you paste codes into the
**IMPORT CODES** box and press **Analyse**, the page tells you for each one
whether it can become a permanent ROM edit and, when it cannot, exactly why.

If you own a GameShark cartridge dump, **Import from a GameShark ROM…** reads
its whole built-in code database.

---

## 7. Finding things nobody has found yet

This is the part that needs you, because it needs someone who can run the game.

**The gameplay constants — passing distance, throwing arc, running speed, ball
gravity — have not been located.** They show on the Gameplay pages as
greyed-out rows marked *not discovered*. Nothing writes to a guessed address.

The way to find one:

1. Get two dumps of the ROM that differ by **exactly one thing**. Change a
   single value in an emulator's memory editor mid-game and dump RAM, or make
   one change with another tool and save.
2. **ROM Comparison** → put the original in *Original*, the changed one in
   *Modified* → **Compare**.
3. Set **Max length** to `4` to hide bulk changes. A single gameplay constant
   shows up as a 1, 2 or 4 byte region, and the **Reads as** column decodes it
   for you: `u16 BE: 100 → 150`.
4. **Bookmark selected difference**, give it a real name.
5. In **Address Bookmarks**, select it and click **Promote to game
   definition**. It becomes a labelled slider on the matching Gameplay page —
   no code changes.
6. Record what happened in **Research Mode**, including the failures. "Changing
   0x1A40 did nothing" is what stops the next person repeating the test.

One change at a time is the whole discipline. Two changes and you cannot tell
which byte did what.

---

## Handy things

| | |
| --- | --- |
| Undo / redo | **Ctrl+Z** / **Ctrl+Y**, across every editor |
| Revert everything | **Edit → Revert all changes to the original ROM** (itself undoable) |
| See what you changed | **Edit → Show edit history…** |
| Survey an unknown ROM | **Tools → ROM Scanner…** |
| Jump to an address | **Hex / Data Explorer**, type into *Go to address* |
| Where settings live | `%APPDATA%\NFLBlitzModSuite` |

## If it will not start

Open a Command Prompt in the folder and run:

```
NFLBlitzModSuite.exe --self-test
```

It writes `self-test-report.txt` next to the exe saying what it found. That
file is the useful thing to report.
