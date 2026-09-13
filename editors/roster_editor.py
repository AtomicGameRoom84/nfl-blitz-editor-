"""Roster editor.

Players are a table of records, optionally keyed to a team by a ``team``
field.  Everything structural comes from
:class:`~editors.table_editor.TableEditor`; this class adds the roster-shaped
conveniences: filtering by team, moving a player between teams, and bulk
attribute edits.

As with the team editor, this is inert until a game definition declares a
``players`` table -- the NFL Blitz player table has not been located yet.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Optional

from editors.table_editor import Record, TableEditor

NAME = "name"
NUMBER = "number"
POSITION = "position"
TEAM = "team"


class RosterEditor(TableEditor):
    """Edits the player table declared by the game definition."""

    module_id = "roster"
    title = "Roster Editor"
    subtitle = "Player names, numbers, positions and attributes"
    table_id = "players"

    # -- queries -----------------------------------------------------------

    def players_for_team(self, team_index: int) -> List[Record]:
        """Records whose ``team`` field matches, or every record if untracked."""
        table = self._require_available()
        if table.field(TEAM) is None:
            return list(self.records())
        return [r for r in self.records() if r.get(TEAM) == team_index]

    def player_label(self, record: Record) -> str:
        number = record.get(NUMBER)
        name = str(record.get(NAME, "") or "").strip() or f"Player {record.index}"
        position = record.get(POSITION)
        parts = []
        if number is not None:
            parts.append(f"#{number}")
        parts.append(name)
        if position not in (None, ""):
            parts.append(f"({self.position_label(position)})")
        return " ".join(parts)

    def position_label(self, value: Any) -> str:
        """Map a raw position value through the definition's enum, if present."""
        table = self.table
        field = table.field(POSITION) if table else None
        if field and field.kind == "enum":
            options = field.options.get("values", {})
            return str(options.get(str(value), options.get(value, value)))
        return str(value)

    # -- editing -----------------------------------------------------------

    def move_to_team(self, player_index: int, team_index: int) -> None:
        """Reassign a player, if the definition tracks team membership."""
        table = self._require_available()
        if table.field(TEAM) is None:
            raise RuntimeError(
                f"The {table.name} table has no team field, so players cannot "
                "be moved between teams in this ROM."
            )
        self.write_field(player_index, TEAM, team_index)

    def bulk_set(
        self,
        indices: Iterable[int],
        field_id: str,
        value: Any,
        description: str = "",
    ) -> int:
        """Set one field on many players as a single undo step."""
        table = self._require_available()
        indices = list(indices)
        label = description or f"Set {field_id} = {value} on {len(indices)} player(s)"
        changed = 0
        with self.rom.undo.transaction(label):
            for index in indices:
                field = table.field(field_id)
                if field is None:
                    raise KeyError(f"no field {field_id!r} in {table.id!r}")
                if self.read_field(index, field) != value:
                    self.write_field(index, field_id, value)
                    changed += 1
        return changed

    def bulk_adjust(
        self,
        indices: Iterable[int],
        field_id: str,
        delta: float,
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
    ) -> int:
        """Add ``delta`` to a numeric field on many players, clamped to range."""
        table = self._require_available()
        field = table.field(field_id)
        if field is None:
            raise KeyError(f"no field {field_id!r} in {table.id!r}")
        if field.kind == "text":
            raise ValueError(f"{field.name} is text and cannot be adjusted numerically")
        low = minimum if minimum is not None else (
            field.minimum if field.minimum is not None else field.data_type.minimum
        )
        high = maximum if maximum is not None else (
            field.maximum if field.maximum is not None else field.data_type.maximum
        )
        changed = 0
        with self.rom.undo.transaction(
            f"Adjust {field.name} by {delta:+g} on selected players"
        ):
            for index in indices:
                current = self.read_field(index, field)
                updated = current + delta
                if low is not None:
                    updated = max(low, updated)
                if high is not None:
                    updated = min(high, updated)
                if not field.data_type.is_float:
                    updated = int(round(updated))
                if updated != current:
                    self.write_field(index, field_id, updated)
                    changed += 1
        return changed

    def attribute_fields(self) -> List[str]:
        """Numeric fields that are not structural -- i.e. the ratings."""
        structural = {NAME, NUMBER, POSITION, TEAM}
        return [
            f.id
            for f in self.fields()
            if f.id not in structural and f.kind == "number"
        ]
