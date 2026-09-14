# Implemented vs planned

Status as of this build. Anything marked **Not implemented** does nothing and
says so in the application — no placeholder that looks functional.

## Implemented

### ROM handling
- [x] Open `.z64`, `.v64`, `.n64` (and word-swapped) images; byte order detected
      from the header magic, not the file extension
- [x] Converted to big endian internally; can be saved back in any order
- [x] N64 header parsing: internal name, game code, region, media, revision,
      boot address, libultra release, CRC1/CRC2
- [x] Advisory validation — refuses non-ROMs, warns about (but still opens)
      odd sizes, unknown boot code, mismatched checksums
- [x] N64 boot checksum (CRC1/CRC2) calculation and CIC chip detection;
      recalculated on save so modified ROMs boot on real hardware
- [x] Original file opened read-only and never written to; **Save ROM As**
      refuses to overwrite the file that was loaded
- [x] Automatic backup offer on load, SHA-1 indexed so duplicates are skipped;
      restore and prune
- [x] Modification summary before saving
- [x] Recent ROMs list

### Hex / Data Explorer
- [x] Virtualised hex/ASCII view — only visible rows are formatted, so a
      64 MiB ROM scrolls as fast as a 512 KiB one
- [x] Nibble-accurate hex typing, ASCII typing, selection, keyboard navigation
- [x] Live data inspector: `u8`…`s32` and `f32` in both byte orders, bits, text
- [x] Modified bytes, bookmarks and search hits highlighted
- [x] Go to address, find bytes or text, copy/paste hex, fill selection,
      revert selection to original
- [x] Configurable bytes per row, font size, hex case

### Search and analysis
- [x] Exact-value and range search for `u8`…`s32` and `f32`, either byte order,
      with alignment control
- [x] Text search, case sensitive or insensitive
- [x] Hex byte search, and masked search with wildcards (`DE ?? BE EF`)
- [x] Printable-string listing
- [x] Iterative narrowing: keep addresses that stayed the same, changed,
      increased, decreased, or equal a value
- [x] ROM Scanner — structural survey of an unknown image
- [x] Pointer Finder — candidate references as raw offsets, KSEG0 addresses,
      or relative to a load base

### ROM comparison
- [x] Byte-for-byte diff of two files, or of the working copy against the
      loaded image
- [x] Byte orders normalised first, so `.v64` vs `.z64` of the same cartridge
      compares as identical
- [x] Configurable region merging, structural labelling, length filtering
- [x] Each difference decoded as every type that fits, with before/after/delta
- [x] Bookmark a difference in one click; export CSV or JSON

### Bookmarks and research
- [x] Named, typed, categorised bookmarks with defaults, ranges, confidence
      levels and notes, scoped to the ROM build they were found in
- [x] JSON storage, idempotent import/export, CSV export
- [x] **Promote to game definition** — turns a bookmark into a working editor
      control with no code changes
- [x] Research Mode: experiments recording address, before/after values,
      hypothesis, result and outcome; Markdown and CSV export

### Editing
- [x] Address database: every editor reads addresses from JSON definitions
- [x] Gameplay Values / Physics & Movement / Passing & Ball Physics —
      sliders and numeric entry driven entirely by the loaded ROM's definition,
      with scaling, units, per-value and bulk **Restore defaults**
- [x] Undiscovered values render as labelled, inactive rows rather than being
      hidden
- [x] Team Editor — form generated from the definition's team table; text,
      numeric, enum and colour (RGBA5551 / RGBA8888) fields; CSV import/export
- [x] Roster Editor — spreadsheet over the player table, inline editing, team
      filtering, bulk adjust and bulk set, move between teams, revert selected,
      CSV import/export
- [x] Undo/redo across every editor, with bulk operations collapsing to one
      step and failed imports rolling back completely
- [x] Revert a range, a record, or the whole ROM

### Patches
- [x] BPS creation and application, with source/target/patch CRC32
      verification and embedded name/version/author/description
- [x] IPS creation and application, including RLE records and the truncate
      extension; refuses rather than writing an unrepresentable patch, and
      writes metadata to a sidecar `.json`
- [x] Patch inspection, change estimation, and in-place application to the
      working copy as a single undoable step

### NFL Blitz (N64, USA) data
- [x] ROM identified by exact fingerprint (SHA-1 and boot CRC pair)
- [x] Team table mapped: 30 teams — city, nickname, two abbreviations, five
      rating bars, overall value, roster pointer
- [x] Player table mapped: 480 players — names, jersey numbers, positions,
      portrait IDs, skill slots
- [x] Jersey numbers decoded as binary-coded decimal, so the editor shows 22
      rather than 34
- [x] Upper-case city table mapped
- [x] RAM ↔ ROM address mapping recorded for further research
- [x] Positional team membership (16 players per block, no team field)
- [x] Full details in [NFL_BLITZ_USA_MAP.md](NFL_BLITZ_USA_MAP.md)

### GameShark codes
- [x] Parse and explain N64 codes: `80`/`81`/`A0`/`A1` writes, `88`/`89` button
      writes, `F0`/`F1` boot writes, `D0`–`D3` conditionals, `50` repeater and
      the device directives; unknown types are reported, never guessed
- [x] Generate codes from catalogued runtime addresses, including the
      upper-halfword float form published codes use
- [x] Convert codes to permanent ROM edits **only** where the address falls in
      a verified RAM-to-ROM range, applied as one undoable step
- [x] Say exactly why a code could not be converted
- [x] Bookmark convertible codes for follow-up research
- [x] Read the code database out of a GameShark firmware dump you own
- [x] NFL Blitz (USA) catalogue of 42 runtime addresses taken from the
      GameShark Pro v3.3 device database, including Fast Passes and the
      hidden-character roster

### Packaging
- [x] PyInstaller spec producing a single executable
- [x] `packaging/build_windows.bat` and a cross-platform `packaging/build.py`
- [x] GitHub Actions workflow building, testing and smoke-testing a Windows
      `.exe` on a hosted runner, uploaded as an artifact and attached to tagged
      releases
- [x] `--self-test` mode that proves a frozen build finds its bundled data

### Other
- [x] Dark themed PySide6 interface with sidebar navigation and full menus
- [x] Settings persisted outside the installation directory
- [x] Synthetic demo cartridge generator so every editor can be exercised
      without a real ROM
- [x] 206 unit and headless-UI tests

## Not implemented

- [ ] **NFL Blitz gameplay constants.** Pass distance, speed, gravity, tackle
      power and the rest are declared but every one still has a null address
      and is marked `undiscovered`. No guesses are shipped.
- [ ] **NFL Blitz 2000 / 2001 / Special Edition data.** Those definitions are
      still stubs; nobody has dumped and mapped them here.
- [ ] **Graphics Editor.** Texture locations and formats in NFL Blitz are
      unknown, and N64 titles often store graphics inside compressed archives
      rather than at fixed addresses. The page states what it needs first.
- [ ] Texture decoding/encoding (RGBA16, RGBA32, IA4/8/16, I4/8, CI4/CI8) —
      the codec is planned but pointless before assets are located
- [ ] Adding new teams or players beyond the existing table size (would
      require relocating tables and fixing up pointers)
- [ ] Live emulator memory watching
- [ ] A verified RAM-to-ROM map beyond the roster region (only one range is
      confirmed; the delta does not generalise)
- [ ] Audio and menu editing
- [ ] Support for the arcade or PlayStation versions

See [ROADMAP.md](ROADMAP.md) for how the gaps get closed.
