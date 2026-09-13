# Game definition files

A game definition is a JSON document describing where data lives in one build
of one game. **No editor in this suite contains a ROM address** — they render
whatever the definition for the loaded ROM declares. Supporting a new NFL
Blitz build is therefore a data change, not a code change.

Definitions are loaded from two places:

| Location | Purpose |
| --- | --- |
| `games/` in this repository | Shipped, read-only |
| `games/` in your user data directory | Yours; overrides a shipped file with the same `id` |

The application never modifies a shipped file. The first time you add a
discovered address, the definition is forked into your user directory and that
copy takes precedence from then on.

`games/demo_rom.json` is a complete, working example — read it alongside this
document.

---

## Top level

```json
{
  "schema_version": 1,
  "id": "nfl_blitz_1997",
  "game": "NFL Blitz",
  "version_label": "N64 (USA) - unverified",
  "platform": "N64",
  "notes": "Free-form. Say what is verified and what is not.",
  "identification": { ... },
  "entries": [ ... ],
  "tables": [ ... ]
}
```

`id` must be unique and stable — it is the key a user definition uses to
override a shipped one.

---

## `identification`

How the suite decides a definition applies to a loaded ROM. Every rule is
optional and scores independently; the highest total wins.

```json
"identification": {
  "sha1": [],
  "crc_pairs": [],
  "cartridge_ids": ["BL"],
  "region_codes": ["E"],
  "internal_name_matches": ["(?i)^\\s*(nfl\\s*)?blitz\\s*$", "(?i)blitz"],
  "rom_sizes": [16777216]
}
```

| Rule | Score | Notes |
| --- | --- | --- |
| `sha1` | 120 | Exact file. |
| `crc_pairs` | 100 | `[crc1, crc2]` from the header, as numbers or `"0x…"` strings. |
| `cartridge_ids` | 30 | The two-character ID at header offset `0x3C`. |
| `region_codes` | 10 | One character: `E` USA, `P` Europe, `J` Japan. |
| `internal_name_matches` | 25, 15, 5… | Python regexes against the header's internal name. |
| `rom_sizes` | 5 | Exact byte counts. |

A match scoring 100 or more is reported as an **exact fingerprint match**;
anything lower is reported as a **heuristic match** and the UI says so.

Name patterns are scored by position — the first pattern scores highest — so a
specific definition beats a general one. That is why a ROM named
`NFL BLITZ 2000` matches `nfl_blitz_2000` rather than tying with the base
game's catch-all `(?i)blitz`.

The shipped NFL Blitz files carry **no** `sha1` or `crc_pairs`, because this
project has not verified any dump. Use **ROM Manager → Register this ROM's
fingerprint** to add your own.

---

## `entries` — single scalar values

Each entry becomes one slider-and-spinbox row on a gameplay page.

```json
{
  "id": "player_run_speed",
  "name": "Player running speed",
  "category": "movement",
  "group": "Running",
  "address": 32768,
  "data_type": "u16",
  "endian": "big",
  "default": 100,
  "minimum": 0,
  "maximum": 200,
  "step": 1.0,
  "scale": 1.0,
  "unit": "",
  "confidence": "confirmed",
  "source": "Found by diffing two dumps, 2026-03-14",
  "notes": "Affects all players, not just the ball carrier."
}
```

| Field | Meaning |
| --- | --- |
| `id` | Unique within the definition; used to match rows on reload. |
| `category` | `movement`, `passing`, `physics`, `teams`, `rosters`, `graphics`, `audio`, `menus`, `misc`. Decides which page shows it. |
| `group` | Card heading within the page. Free text. |
| `address` | **`null` means "not discovered yet"** — see below. Accepts `"0x8000"` strings. |
| `data_type` | `u8` `s8` `u16` `s16` `u32` `s32` `u64` `s64` `f32` `f64`. |
| `endian` | `big` (the N64's native order) or `little`. |
| `default` | The stock value. Drives **Restore**; falls back to the loaded ROM's own value when absent. |
| `minimum` / `maximum` | Edit bounds. Omitted, the data type's full range is used. |
| `scale` | Displayed value = raw × scale. Lets a raw fixed-point value show in game units. |
| `unit` | Suffix in the spin box (`yd`, `%`, `s`, `deg`). |
| `confidence` | `undiscovered`, `guess`, `experimental`, `tested`, `confirmed`. Shown as a coloured badge. |
| `source` | How it was found. Please fill this in. |

### Declaring what you have *not* found

An entry with `"address": null` and `"confidence": "undiscovered"` is valid and
useful: it renders as a greyed-out row labelled *"address not discovered yet"*.
That is how the shipped NFL Blitz definitions publish a wanted list —
`Short pass maximum distance`, `Ball gravity`, `Sprint speed multiplier` and so
on — without pretending to know where they are.

Writing to an undiscovered entry raises an error rather than writing somewhere
arbitrary.

---

## `tables` — arrays of records

Teams, rosters and anything else stored as a fixed-stride array.

```json
{
  "id": "players",
  "name": "Players",
  "base_address": 16384,
  "record_size": 24,
  "record_count": 64,
  "confidence": "confirmed",
  "notes": "",
  "fields": [
    { "id": "name",   "name": "Name",   "offset": 0,  "kind": "text", "length": 16 },
    { "id": "number", "name": "Number", "offset": 16, "data_type": "u8",
      "minimum": 0, "maximum": 99 },
    { "id": "position", "name": "Position", "offset": 17, "data_type": "u8",
      "kind": "enum", "options": { "values": { "0": "QB", "1": "RB", "2": "WR" } } },
    { "id": "team",  "name": "Team",  "offset": 18, "data_type": "u8" },
    { "id": "speed", "name": "Speed", "offset": 19, "data_type": "u8",
      "minimum": 0, "maximum": 99 }
  ]
}
```

A table is only used when `base_address`, `record_size`, `record_count` and
`fields` are all present; otherwise the editor reports exactly which of the
four is missing. A table that would run past the end of the loaded ROM is also
refused, since that means the definition is for a different build.

### Field `kind`

| `kind` | Rendered as | Notes |
| --- | --- | --- |
| `number` (default) | Spin box / editable cell | Clamped to `minimum`/`maximum`. |
| `text` | Line edit | Needs `length` (bytes). Written in place, NUL padded; a value that does not fit is **refused**, not truncated. |
| `enum` | Drop-down / label | `options.values` maps the raw number (as a string key) to a label. Roster cells accept either the label or the number. |
| `color` | Colour picker | 2 bytes = RGBA5551, 4 bytes = RGBA8888. Any other size is refused rather than guessed. |

### Table ids the editors look for

| `id` | Editor | Fields it understands |
| --- | --- | --- |
| `teams` | Team Editor | `city`, `nickname`, `abbreviation`, `primary_color`, `secondary_color`, `logo_id`, `uniform_id` |
| `players` | Roster Editor | `name`, `number`, `position`, `team`, plus any other numeric field as a rating |
| `textures` | Graphics Editor | Reserved; the editor is not implemented yet |

Any subset works — the UI renders whatever is declared. A table with extra
columns beyond the recognised names is fine; roster bulk edits treat every
numeric non-structural field as a rating automatically.

---

## Adding a new game

1. Copy a stub, e.g. `games/nfl_blitz_2000.json`.
2. Give it a unique `id` and a useful `version_label`.
3. Fill in `identification` — at minimum an `internal_name_matches` pattern.
4. Add entries and tables as you discover them.
5. **Tools → Reload game definitions**, or restart.

Files with a `schema_version` higher than this build understands are refused
with a clear message rather than half-parsed, and a malformed file is reported
in ROM Manager without stopping the others from loading.
