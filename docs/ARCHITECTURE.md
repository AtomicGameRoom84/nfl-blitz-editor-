# Architecture

## Layers

```
    ui/          PySide6. Pages, widgets, dialogs, theme, app state.
      │          Imports from every layer below. Nothing imports it.
      ▼
    editors/     Editor logic: tables, gameplay values, availability.
      │          Pairs a ROM with a game definition. No Qt.
      ▼
    tools/       Research: comparison, search, scanner, pointers, notes.
      │          No Qt.
      ▼
    core/        ROM loading, validation, byte orders, checksums, undo,
                 address database, bookmarks, patches. No Qt.

    games/       Data. Not code.
```

The rule that keeps this honest: **`core/`, `editors/` and `tools/` never
import Qt.** Everything except the widgets themselves is testable without a
display, which is why the test suite covers behaviour rather than just
construction.

## Key decisions

### Addresses are data, not code

`core/address_db.py` loads JSON game definitions; editors render whatever the
definition for the loaded ROM declares. No editor contains an address.

Consequences: supporting a new NFL Blitz build is a data change; a user's
discoveries get picked up by forking the definition into their data directory;
and a definition can declare a value it has *not* found (`"address": null`),
which renders as an inactive labelled row. That last one is why the suite can
publish a wanted list without pretending to know anything.

See [GAME_DEFINITIONS.md](GAME_DEFINITIONS.md).

### One working copy, one undo stack

`ROMManager` owns three things: `original` (the image exactly as loaded, never
written), `data` (the mutable working copy), and an `UndoRedoManager`.

Every mutation goes through a `Command`. Editors never write bytes directly —
they build a command and hand it over. That makes "every modification supports
undo" true by construction rather than by convention, and it is why a roster
CSV import, a patch application and a hand-typed hex nibble all land on the
same history.

`UndoRedoManager.transaction()` groups a block into one step and rolls the
whole block back if it raises, so a failed bulk import cannot leave the ROM
half-edited.

### The original file is untouchable

The source is read once and closed. `save_as()` raises if the destination is
the file that was loaded — enforced at the lowest level, not in the UI, so no
future code path can bypass it.

### Availability is a first-class result

`editors.base.Availability` carries `available`, a human `reason`, and a list
of what is `missing`. An editor that cannot run returns one instead of
throwing or rendering an empty page, and the UI turns it into a banner naming
exactly what still needs discovering.

> `Availability` is falsey when it reports a problem, so the internal
> `_require_*` helpers are tested with `is not None`, never `if blocked:`.

### `core` talks in callbacks, `ui` turns them into signals

`ROMManager`, `BookmarkDatabase` and `ResearchLog` notify plain callables.
`ui/app_state.py` is the single place that adapts them to Qt signals
(`romLoaded`, `romChanged`, `historyChanged`, `bookmarksChanged`,
`definitionChanged`, …). Pages connect to `AppState` and nothing else.

### The hex view is painted, not modelled

`ui/widgets/hex_view.py` is a `QAbstractScrollArea` that formats only the rows
currently on screen. A 64 MiB ROM scrolls identically to a 512 KiB one. Byte
highlighting (modified / bookmarked / search hit) is a per-byte lookup during
paint, so there is no per-byte widget anywhere.

### Tables are generic

`editors/table_editor.py` implements records, typed field access, undoable
writes and CSV round-tripping for *any* fixed-stride table described by a
definition. `TeamEditor` and `RosterEditor` are thin configuration on top —
colour handling and team labels, bulk edits and team moves respectively.

Adding the NFL Blitz roster format later is a JSON change, not new code.

## Data flow when a ROM is loaded

```
ROMManagerPage.load_rom
  └─ AppState.load_rom
       ├─ ROMManager.load_file
       │    ├─ ROMValidator.validate         → byte order, header, warnings
       │    ├─ ByteOrderConverter            → canonical big endian
       │    └─ original + working copy, history cleared
       ├─ ROMIdentity.from_bytes             → name, game code, CRCs, SHA-1
       ├─ AddressDatabase.best_match         → scored definition match
       └─ emits romLoaded + definitionChanged
            └─ every page rebuilds from the new definition
```

## Where user data lives

Nothing is written inside the installation directory. `core/paths.py` resolves
a per-platform data directory (overridable with `NFL_BLITZ_SUITE_HOME`, which
is how the tests stay hermetic) holding settings, backups, bookmarks, research
notes and user-edited game definitions.

## Testing

`tests/` covers each layer independently, with an autouse fixture pointing the
user data directory at a temporary folder. The demo cartridge is built once per
session from `games/demo_rom.json`, which means the editors are exercised
against real data with no copyrighted material involved.

`tests/test_ui_smoke.py` builds the real main window under
`QT_QPA_PLATFORM=offscreen` and drives every page. It skips itself if Qt cannot
start, so a machine without Qt's runtime libraries still runs everything else.
