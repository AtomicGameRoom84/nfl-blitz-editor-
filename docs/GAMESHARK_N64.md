# N64 GameShark codes, and what they mean for ROM hacking

A GameShark is a pass-through cartridge that patches the console's **RAM**
while the game runs. That distinction drives everything below: a code is not
a ROM edit, and most codes cannot be turned into one.

The suite supports codes because the published corpus is decades of other
people's reverse engineering. Someone already found the address — the work
left is deciding what it means and whether it can be made permanent.

## Code format

A code is two hex words:

```
802997E3 0003
^^                type
  ^^^^^^          24-bit address operand
         ^^^^     value
```

The address operand is the low 24 bits; the type supplies the base, normally
KSEG0 (`0x80000000`), the cached, unmapped view of RDRAM. So `802997E3` means
RAM address `0x802997E3`.

### Types the suite implements

| Type | Meaning | Writes memory |
| --- | --- | --- |
| `80` | 8-bit constant write, every frame | yes |
| `81` | 16-bit constant write, every frame | yes |
| `A0` | 8-bit write through uncached KSEG1 | yes |
| `A1` | 16-bit write through uncached KSEG1 | yes |
| `88` | 8-bit write when the GS button is pressed | yes |
| `89` | 16-bit write when the GS button is pressed | yes |
| `F0` | 8-bit write once, at boot | yes |
| `F1` | 16-bit write once, at boot | yes |
| `D0` | run the next code if the byte equals the value | no |
| `D1` | run the next code if the halfword equals the value | no |
| `D2` | run the next code if the byte differs | no |
| `D3` | run the next code if the halfword differs | no |
| `50` | serial repeater: repeat the next write, stepping address and value | no |
| `EE` | disable the Expansion Pak (device directive) | no |
| `DE` | set the executable entry point (device directive) | no |
| `FF` | set where the device stores active codes | no |
| `CC` | device directive | no |

Anything else is reported as **unsupported** rather than guessed at. A
mis-applied code writes to the wrong place, and on a ROM that is silent
corruption.

### The float trick

N64 games keep a lot of gameplay state in 32-bit floats. A published code
often writes only the *upper halfword* with an `81`, because that is enough to
set the exponent and the top mantissa bits.

NFL Blitz's "Infinite Turbo" is exactly this:

```
812ADD6C 42C8      ; 0x42C80000 is 100.0f
```

The suite generates codes in the same form (`float_high_half` on a catalogue
entry), and the Data Inspector will show you the whole float once you find its
ROM counterpart.

## Why a code usually is not a ROM patch

Three things have to be true before a code can become a permanent edit:

1. **The address must be in RAM that came from the ROM.** An N64 game DMAs
   several segments to different addresses, plus a heap and a stack. Only the
   copied segments have a ROM counterpart.
2. **You must know the mapping for that segment.** One global "RAM minus
   delta" is almost always wrong — see below.
3. **The game must not recompute the value.** A `80`-type code rewrites its
   address every frame precisely *because* the game keeps overwriting it.
   Patching the ROM changes the initial value only.

Point 3 is the one that catches people. A score, a timer, a per-frame flag:
patching the ROM does nothing, because the game writes that memory itself
during play.

### The suite's position on this

`games/*.json` keeps two separate sections, and the UI never blurs them:

- **`ram_map`** — RAM windows *verified* to mirror ROM content, as explicit
  ranges. The GameShark page converts an address only if it falls in one.
- **`ram_codes`** — catalogued runtime addresses. These are labelled as RAM,
  shown with generated codes to paste into an emulator, and are *not*
  presented as ROM offsets.

When a code cannot be converted, the page says which of the reasons applies
rather than quietly skipping it.

## NFL Blitz (USA): what is mapped

One verified range:

```
RAM 0x802DE3D8 .. 0x802E9058   ->   ROM 0x09D070 .. 0x0A7CF0
delta 0x80241368
```

That is the roster and team data region, confirmed by all 30 roster pointers
in the team table resolving exactly onto their own blocks.

**The delta does not generalise.** Extending it ROM-wide by checking whether
pointers land on string starts did not hold up — a wrong delta scored *better*
than the right one, and several pointers landed mid-string. That is the
signature of multiple segments at different offsets, so the definition records
one range and the converter refuses everything outside it.

This is why the published Blitz cheat codes at `0x802997xx` are catalogued but
**not** convertible: that address region is not in the verified window, and the
cheat flags are runtime state the game fills in from the VS screen anyway.

## Reading a GameShark cartridge's own database

If you own a GameShark, its firmware contains the code database it shipped
with — a much better source than a fan-site transcription, since the names and
values are the device's own.

**GameShark Codes → Import from a GameShark ROM…** reads one.

The record format, reverse engineered from GameShark Pro (USA) v3.3:

```
<game name> 00 <entry count>
  ( <description> 00 <flags> <N * 6-byte code> [FF]... )*

6-byte code:  TT AAAAAA VVVV
```

`flags` holds the code count in its low seven bits; the top bit marks the head
of a linked group (a Home/Away pair, say), and `FF` bytes separate groups.

The parser stops the moment a record fails to validate — every code type must
be one the device implements — so a wrong starting offset yields nothing
rather than plausible nonsense. On the v3.3 dump the NFL Blitz record at
`0x037012` declares 106 entries and parses to exactly 106, which is the
check that the format above is right.

## Using codes for discovery

Even an unconvertible code is a lead:

1. **Import the code** and read what the page says about it.
2. **Bookmark the convertible ones** — the page does this in one click, with
   the RAM address recorded in the note.
3. **For the rest, hunt the ROM counterpart.** You know the value the game
   holds at runtime; search the ROM for it with Value Search, then narrow.
   The RAM address's alignment and its offset relative to a known structure
   are both useful hints.
4. **Record the result in Research Mode**, including the failures.

## Sources

The code-type table was cross-checked against the EnHacklopedia N64 reference
and the GameShark Wiki, then validated against an actual GameShark Pro v3.3
firmware dump — every one of the 106 NFL Blitz entries in that dump uses a
type from the table above, which is what makes the parse self-validating.

- [EnHacklopedia — Hacking Nintendo 64](https://doc.kodewerx.org/hacking_n64.html)
- [GameShark Wiki — Nintendo 64](https://gameshark.fandom.com/wiki/Nintendo_64)
- [GameHacking.org — N64 GameShark Handbook](https://wiki.gamehacking.org/Nintendo_64_Game_Shark_Handbook)
