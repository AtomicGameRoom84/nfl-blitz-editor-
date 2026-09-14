# Finding addresses in an unmapped ROM

This is the document the whole suite is built around.

## What is already mapped

For the **USA cartridge** (`NBZE`, boot CRC `D094B170/D7C4B5CC`) the team
table, player table and upper-case city table are mapped, verified and
editable — see [NFL_BLITZ_USA_MAP.md](NFL_BLITZ_USA_MAP.md). Load that ROM and
the Team and Roster editors just work.

What is **not** mapped, on any version: every gameplay constant — pass
distance, running speed, ball gravity, tackle power — plus all graphics, and
the whole of NFL Blitz 2000, 2001 and Special Edition. Those entries ship with
a null address and render as inactive rows rather than as sliders that would
quietly write to the wrong place.

This guide is how you close those gaps.

Useful starting point for the USA cartridge: `rom_offset = ram_address -
0x80241368`. The Pointer Finder takes that as a load base.

---

## The pipeline

```
    ROM Comparison  ─┐
                     ├─►  Bookmark  ─►  Definition entry  ─►  Editor control
    Value Search    ─┘        ▲                                     │
                              └──────── Research Mode ◄─────────────┘
                                        (what did it actually do?)
```

Every step is a button in the application. Nothing requires editing code.

---

## Method 1 — Comparison (the strongest tool you have)

This finds an address by making the game itself write it down for you.

1. **Dump your ROM twice, changing exactly one thing in between.** Any
   emulator that can write a modified ROM, or any other editor, will do. The
   discipline that matters is *one change at a time*.
2. Open **ROM Comparison** in the sidebar.
3. Put the unmodified dump in *Original* and the modified one in *Modified*.
   (Use **Use working copy** to compare your in-progress edits against the ROM
   as it was loaded.)
4. Press **Compare**.

Every differing region is a candidate. Read the results table:

| Column | What it tells you |
| --- | --- |
| Address | Where the difference is |
| Length | 1, 2 or 4 bytes almost always means a single value |
| Region | Header, boot code, or which megabyte of game data |
| Reads as | The region decoded as every type that fits — `u16 BE: 100 → 150` |

Set **Max length** to `4` to hide bulk data changes and leave only the
single-value candidates.

When you find a region that looks right, press **Bookmark selected
difference**. The bookmark is pre-filled with the address, a plausible type,
and a note recording which two ROMs it came from.

Two byte orders compare correctly: a `.v64` and a `.z64` dump of the same
cartridge are normalised before diffing, so they show as identical.

---

## Method 2 — Value search and narrowing

Use this when you know the number but not where it lives.

1. Open **Value Search**.
2. Search for a value you believe exists — `100` as a `u16`, say. You will get
   hundreds or thousands of hits. That is expected and fine.
3. Change the value in the game or in another dump, load that ROM, and use
   **Narrow the results**: keep addresses that *increased*, *decreased*,
   *changed*, or *stayed the same*.
4. Repeat. Each round throws away most of the remaining candidates.

Search modes available:

- **Exact value** and **Value range**, for `u8`…`s32` and `f32`, in either
  byte order, with alignment control (default: the type's own size; drop it to
  1 when hunting for values packed inside a structure).
- **Text**, case sensitive or not.
- **Hex bytes**, and **hex bytes with wildcards** (`DE ?? BE EF`) for when only
  part of a structure is known.
- **All printable strings**, which is how name and menu tables get found.

Tick **Skip header and boot code** (on by default) so the first 0x1000 bytes
do not clutter results.

---

## Method 3 — Structural survey

**Tools → ROM Scanner** reports measurable facts about an unknown ROM: where
printable text clusters (likely name or menu tables), the largest runs of
filler, how the data is distributed, and whether the boot checksum verifies.

It makes no claim about what anything *is*. It tells you where to look first.

**Tools → Pointer Finder** searches for 32-bit words that could reference an
address you have found — as a raw ROM offset, as a KSEG0 virtual address
(`0x80000000 | offset`), or relative to a load base you supply. Finding what
points at a table is usually how the neighbouring tables get found. Every
result is a candidate, not a proven reference.

---

## Method 4 — Reading bytes directly

**Hex / Data Explorer** gives you the raw image with a live **Data Inspector**
that decodes the cursor position as `u8`…`s32` and `f32` in both byte orders,
as bits, and as text. Modified bytes are highlighted against the ROM as it was
loaded, and bookmarked ranges are tinted.

Type hex digits to edit. Tab switches between the hex and ASCII columns.
Everything you type joins the same undo stack as every other editor.

---

## Recording what you learn

### Bookmarks

**Address Bookmarks** is your findings database: name, address, data type,
endianness, category, default value, suggested range, confidence
(`unknown` → `suspected` → `tested` → `confirmed`) and free-form notes.

Bookmarks are scoped to the ROM build they were found in, and stored as plain
JSON so they can be shared, diffed and version controlled. Import and export
are idempotent, so merging someone else's findings with yours is safe.

### Research Mode

A lab notebook. Each experiment records the address, the original and modified
values, what you expected, what actually happened, and an outcome
(`untested`, `no effect`, `partial`, `confirmed`, `crashed`, `inconclusive`).

**Write down the failures.** "Changing 0x1A40 did nothing visible" is what
stops the next person — or you, in three weeks — repeating the same test.
Export to Markdown to share.

---

## Turning a finding into an editor control

This is the payoff.

1. Select a bookmark you trust in **Address Bookmarks**.
2. Press **Promote to game definition**.
3. Choose a category: `movement`, `passing`, `physics`, `teams`, `rosters`,
   `graphics`, `audio`, `menus` or `misc`.

The suite forks the built-in definition into your user data directory (the
shipped file is never modified), adds the entry, and saves. The control
appears immediately on the matching gameplay page — a labelled slider with the
right range, the right type, your default value and a confidence badge that
carries over from the bookmark.

Categories map to pages like this:

| Category | Page |
| --- | --- |
| `movement`, `physics` | Physics & Movement |
| `passing` | Passing & Ball Physics |
| `misc` | Gameplay Values |
| `teams` | Team Editor (needs a table, not an entry — see below) |
| `rosters` | Roster Editor (likewise) |

### Making your ROM match exactly

On first load, a stub definition matches only by the ROM's internal name,
which is a guess. Open **ROM Manager** and press **Register this ROM's
fingerprint**: your dump's CRC pair and SHA-1 are written into your copy of
the definition, and from then on it is an exact match.

---

## Tables: teams and rosters

Scalar values are single entries. Teams and players are *tables* — arrays of
fixed-size records — and they need four facts before the editor will run:

- `base_address` — where the array starts
- `record_size` — the stride between records
- `record_count` — how many there are
- `fields` — the offset, type and kind of each column

Finding a table usually goes:

1. **ROM Scanner** or a string search finds a cluster of names.
2. The addresses of consecutive names give you the stride (`record_size`).
3. Count the names to get `record_count`.
4. Compare two dumps with one player's rating changed; the diff offset minus
   the record start gives you that field's offset.

Then edit your definition file (see
[GAME_DEFINITIONS.md](GAME_DEFINITIONS.md)) and press **Tools → Reload game
definitions**. The Team and Roster editors light up with no code changes —
`games/demo_rom.json` is a complete worked example of exactly this.

---

## Working safely

- The original file is opened read-only and never written to. Saving always
  goes through **Save ROM As**, which refuses to overwrite the file you loaded.
- Automatic backups are offered on load, indexed by SHA-1 so the same ROM is
  never backed up twice.
- Every modification is undoable, including bulk imports and patch
  application, which each collapse to a single step.
- **Edit → Revert all changes** restores the working copy in one step (itself
  undoable).
- A real N64 cartridge checks its boot checksum. **Save ROM As** recalculates
  CRC1/CRC2 by default so a modified ROM still boots on hardware and on strict
  flash carts. Emulators generally do not care.

---

## When you have something worth sharing

Share the **patch**, never the ROM. Patch Builder produces:

- **BPS** — recommended for N64. No size limit, and it stores CRC32 checksums
  of the source and target so applying it to the wrong ROM is detected rather
  than silently corrupting it. Patch name, version, author and description are
  stored inside the file.
- **IPS** — widest tool compatibility, but it cannot address past 16 MiB. The
  builder refuses rather than writing a broken patch, and since IPS has no
  metadata block, your patch details are written to a `.json` file beside it.

Also worth sharing: your **bookmark export** and your **research log**. Those
are how the next person gets further than you did.
