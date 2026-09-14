# NFL Blitz (N64, USA) — ROM map

Everything on this page was derived from a verified cartridge dump and
checked structurally. It is the data behind `games/nfl_blitz_1997.json`.

## The build this describes

| | |
| --- | --- |
| Internal name | `NFL BLITZ` |
| Game code | `NBZE` (cartridge ID `BZ`, region `E` = USA, revision 0) |
| Size | 16,777,216 bytes (16 MiB) |
| Byte order | Big endian (`.z64`) |
| CIC | 6102 |
| Boot checksum | `D094B170` / `D7C4B5CC` — verifies against the ROM contents |
| CRC32 | `9BCD670F` |
| SHA-1 | `2853afd9e38d63d913c8484f546804708c8ad712` |

Addresses below are **ROM file offsets** in the big endian image.

## RAM ↔ ROM mapping

```
rom_offset = ram_address - 0x80241368
ram_address = rom_offset + 0x80241368
```

Derived from the 30 roster pointers in the team table and confirmed against
all 30 — each one resolves exactly onto its own player block. Use it with the
Pointer Finder's *load base* field when chasing references.

## Team table — `0x000A7CD8`

30 records × `0x40` bytes, ending at `0x000A8458`. Ordered alphabetically by
city, which is also the order the roster blocks and the upper-case city table
use.

| Offset | Type | Field |
| --- | --- | --- |
| `+0x00` | u16 | Passing rating (0–5) |
| `+0x02` | u16 | Rushing rating (0–5) |
| `+0x04` | u16 | Team rating 3 (0–5) |
| `+0x06` | u16 | Team rating 4 (0–5) |
| `+0x08` | u16 | Team rating 5 (0–5) |
| `+0x0A` | u16 | Reserved — zero in all 30 records |
| `+0x0C` | u16 | Reserved — zero in all 30 records |
| `+0x0E` | u16 | Overall value (3–11) |
| `+0x10` | char[16] | Nickname, NUL padded (`Cardinals`) |
| `+0x20` | char[16] | City, NUL padded (`Arizona`) |
| `+0x30` | char[4] | City abbreviation (`ARZ`, `G.B`) |
| `+0x34` | char[4] | Nickname abbreviation (`CAR`) |
| `+0x38` | u32 | Roster pointer, KSEG0 RAM address |
| `+0x3C` | u8 | Unknown flag, 0 or 1 |

### On the rating bars

`+0x00` and `+0x02` are identified with high confidence from the 1997 season:
every elite-quarterback team scores 5 in the first (Miami/Marino,
SF/Young, GB/Favre, Denver/Elway, NE/Bledsoe, Dallas/Aikman) while Chicago and
Indianapolis score 0; Detroit — Barry Sanders' 2,053-yard season — scores 5 in
the second. The other three bars are located and editable, but which on-screen
bar each drives has **not** been confirmed; the definition names them
neutrally and says so.

`+0x0E` ranges 3–11 and tracks team strength (Green Bay 11; Chicago,
Indianapolis and St. Louis 3), but it is not the win total and its exact role
is unconfirmed.

`+0x3C` is 0 for 13 teams and 1 for 17. It is *not* the conference.

## Player table — `0x0009D070`

480 records × `0x5C` bytes: 30 teams × 16 players, one `0x5C0` block per team,
in team-table order. **There is no team field** — membership is positional, so
players cannot be moved between teams by editing a value.

| Offset | Type | Field |
| --- | --- | --- |
| `+0x00` | f32 | Model scale — `1.05` in all 480 records |
| `+0x04` | u32 | Unknown, 0 or 1 |
| `+0x08` | u32 | Unknown, 0 or 1 |
| `+0x0C` | u32 | **Jersey number, binary-coded decimal** |
| `+0x10` | u32 | Position code (see below) |
| `+0x14` | u32 | Portrait / head ID, 0 = generic |
| `+0x18` | u32 | 1 when the record carries a real name |
| `+0x1C` | u32 | Unknown, 0 or 1 |
| `+0x20` | u32 | Skill slot: 4 = QB, 5 = RB, 6 = WR1, 7 = WR2, else 0 |
| `+0x24` | char[16] | Last name, NUL padded |
| `+0x34` | char[16] | First name, NUL padded |
| `+0x44` | 24 bytes | Zero in all 480 records; not declared |

### Jersey numbers are BCD

`0x22` means 22, not 34. Verified twice over: all 480 values are valid BCD
(no nibble above 9), and they match the real 1998 numbers — Aikman `0x08`,
Emmitt Smith `0x22`, Irvin `0x88`, Favre `0x04`, Rice `0x80`, Marino `0x13`.

The suite handles this with a `bcd` field kind, so the editor shows and
accepts the number a human would write.

### Position codes

| Code | Position | Roster slots | Confirmed by |
| --- | --- | --- | --- |
| 0 | QB | 3 | Plummer, Chandler, Harbaugh |
| 1 | WR | 4–6 | Rob Moore, Mathis, Michael Jackson |
| 2 | RB | 4–6 | Murrell, Jamal Anderson, Thurman Thomas |
| 3 | TE | 4–6 | Shannon Sharpe, Tony Gonzalez, Ben Coates |
| 4 | OL | 0–2 | anonymous |
| 5 | K | 14–15 | Morten Andersen, Matt Stover, Kasay |
| 6 | LB | 10–13 | Tuggle, Boulware, Spielman |
| 7 | CB | 10–13 | Rod Woodson, Aeneas Williams, Starks |
| 8 | DL | 7–9 | anonymous |
| 9 | S | 10–13 | Eugene Robinson, Buchanan, Henry Jones |

270 of the 480 records carry names; the linemen are anonymous.

Slot layout per team: 0–2 offensive line, 3 quarterback, 4–6 skill players,
7–9 defensive line, 10–13 linebackers and defensive backs, 14–15 kickers.

## Upper-case city table — `0x000A8468`

30 records × `0x10` bytes, same order, used where the game needs a short
all-caps name. Three entries differ from the team table's city field:
`N.Y. GIANTS`, `N.Y. JETS` and `SAN FRAN.`.

## Still unmapped

- **Every gameplay constant.** Pass distance, speed, gravity and the rest are
  declared in the definition with a `null` address and marked `undiscovered`.
  Finding them needs before/after dumps taken around a single in-game change —
  see [DISCOVERING_ADDRESSES.md](DISCOVERING_ADDRESSES.md).
- **Graphics.** The ROM is 32% printable bytes, which points at compressed or
  packed assets rather than raw textures at fixed addresses. A filename table
  referencing Midway `.wms` assets sits around `0x00124C60` and is probably
  the way in.
- **Playbooks, audio, menu layout.**

## How this was found

1. String search for NFL nicknames located `Cardinals` at `0x000A7CE8`;
   neighbouring names gave the `0x40` stride immediately.
2. Walking the table produced exactly the 30 teams of the 1998 NFL in
   alphabetical order — strong structural confirmation.
3. The `0x802D…` values in each record were spaced exactly `0x5C0` apart,
   which made them roster pointers. Searching for player surnames put the
   roster data at `0x0009E000`-ish, and aligning Aikman's record so that
   `+0x0C` read `0x08` fixed both the record stride (`0x5C`) and the
   RAM↔ROM delta.
4. Every one of the 30 pointers then resolved onto its own block, and all 480
   jersey numbers came out as valid BCD. Two independent checks agreeing is
   what turns a plausible layout into a confirmed one.

Every step used the tools in this repository: the ROM Scanner, the Value
Search's text and string modes, and the Hex/Data Explorer.
