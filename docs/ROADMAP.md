# Roadmap

## Where the project stands

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | Application shell, ROM loading, validation, backups, Save As | **Done** |
| 2 | Hex/Data Explorer, search, bookmarks, byte editing, undo/redo | **Done** |
| 3 | Team and Roster editors, data models, CSV, address database | **Done** — and live on the USA cartridge |
| 4 | Gameplay Values editor, sliders, bookmarking, definitions | **Done** — inert until constants are located |
| 5 | Graphics editor, texture extraction and conversion | **Not started** — blocked on asset discovery |
| 6 | ROM comparison and Patch Builder | **Done** |
| 7 | NFL Blitz-specific reverse-engineered definitions | **In progress** — teams and rosters mapped; gameplay constants outstanding |

Phases 3, 4 and 6 were pulled forward past the original Phase 1–2 brief
because ROM comparison plus bookmarks is what makes the discovery work
possible at all, and because the editors are worthless without somewhere for
discoveries to land. All of it is exercised end to end against the synthetic
demo cartridge, so when Blitz addresses are found they drop into working code.

---

## Phase 7 — reverse engineering NFL Blitz

**Done so far** (USA cartridge, see [NFL_BLITZ_USA_MAP.md](NFL_BLITZ_USA_MAP.md)):
the team table at `0x000A7CD8`, the player table at `0x0009D070`, the
upper-case city table at `0x000A8468`, and the RAM↔ROM delta `0x80241368`.
Steps 1–3 below are complete for that build.

**Outstanding**: the gameplay constants (step 4), graphics (Phase 5), and
every other NFL Blitz version.

This is a research project rather than a programming one. A sensible order:

### 1. Establish a baseline

Register your dump's fingerprint (ROM Manager → **Register this ROM's
fingerprint**) so the definition matches exactly, then run **Tools → ROM
Scanner** and read the text clusters. In a sports game these are almost always
team names, player names and menu strings, and they are the easiest structures
in the ROM to identify.

Record the dump's SHA-1 and CRC pair in your notes. Everything downstream is
only valid for that exact build.

### 2. Text tables: teams first

Team names are few, ordered and predictable, which makes them the best first
target.

- Find the cluster of city or nickname strings.
- Consecutive name addresses give you the record stride.
- Count the entries to get the record count.
- Change one team's name in a hex editor, run the game, confirm it changed on
  screen. Now the table is confirmed, not suspected.
- Diff a dump before and after changing one colour to find the colour field's
  offset, and check whether it decodes as RGBA5551 (2 bytes) or RGBA8888 (4).

Fill in the `teams` table in your definition and the Team Editor works.

### 3. Player records

Same method, larger table. The extra questions are:

- Is there a `team` field in each player record, or is team membership implied
  by position in the array? (The Roster Editor handles both; declare the field
  only if it exists.)
- Which byte is which rating? Change one player's speed in game — or in
  another editor — and diff. The offset of the difference within the record is
  the field offset.
- Are ratings 0–99, 0–255, or a packed nibble pair? The Data Inspector and a
  couple of test edits will tell you.

### 4. Gameplay constants

Hardest, because there is no text to anchor on. Two approaches:

- **Comparison.** Change one thing that has a visible effect, diff, and look at
  short regions. This is the reliable route.
- **Narrowing search.** Search for a plausible value, change it, re-search with
  a refinement. Slower but works when you cannot produce a modified dump.

Expect false positives. Record the failures in Research Mode; a list of
addresses that turned out to do nothing is genuinely valuable.

### 5. Publish

Export your bookmarks and research log and share them. A definition file with
confirmed addresses is the single most useful thing anyone can contribute to
this project — it is pure data, carries no copyrighted content, and turns the
editors on for everyone with the same build.

---

## Phase 5 — graphics

Deliberately not started, because doing it before the assets are located would
mean shipping a texture viewer that renders convincing garbage.

The order it will need to happen in:

1. **Locate asset data.** N64 titles frequently store graphics inside
   compressed or game-specific archives rather than as raw pixels at fixed
   addresses. If Blitz does, this needs a container parser before anything
   else. The Hex Explorer and ROM Scanner are the tools for finding out;
   texture data looks distinctive — long runs of structured, non-zero,
   non-ASCII bytes.
2. **Identify the formats in use.** RGBA16, RGBA32, IA4/IA8/IA16, I4/I8, CI4
   and CI8 (with palettes) are all plausible, and a single game usually mixes
   several. Assuming one format everywhere would be wrong.
3. **Build the codec.** Self-contained and unit-testable: decode to RGBA,
   encode from PNG via Pillow. This part is straightforward once (1) and (2)
   are answered.
4. **Build the discovery tool.** Pick an address, a format and a size; preview
   the decoded image. This is how formats get confirmed in practice, and it
   can ship before any Blitz texture table is known.
5. **Repacking.** Imports must fit whatever container and size limits the
   originals live in.

Item 4 is arguably worth building before item 1 — a generic "decode bytes at
this address as this format" previewer is useful on any ROM and would speed up
step 1 considerably. It is the most likely next piece of work.

---

## Other planned work

| Item | Notes |
| --- | --- |
| Emulator memory watching | Read live RAM while the game runs, so values can be identified by watching them change during play. Needs an emulator with a debug API. |
| Table relocation | Adding teams or players beyond the existing count means moving a table and fixing up everything that points at it. The Pointer Finder is the first half of this. |
| Definition sharing | A simple import/merge flow for community definition files, with conflict reporting. |
| Audio and menu editing | Blocked on the same discovery work as graphics. |
| Other Blitz versions | The architecture already supports them; `nfl_blitz_2000`, `nfl_blitz_2001` and `nfl_blitz_special_edition` stubs exist and need the same Phase 7 treatment. |
| Other platforms | The arcade and PlayStation versions would need their own loaders; the editor, definition and patch layers are platform-agnostic already. |
