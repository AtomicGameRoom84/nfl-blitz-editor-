"""Generic editor over a fixed-stride table of records.

Rosters, team lists, playbooks -- almost every editable structure in a
sports ROM is an array of same-sized records.  Rather than writing that
logic once per editor, :class:`TableEditor` reads a
:class:`~core.address_db.TableDefinition` and provides records, typed field
access, undoable writes and CSV round-tripping for any of them.

:class:`~editors.team_editor.TeamEditor` and
:class:`~editors.roster_editor.RosterEditor` are thin configuration on top
of this class, which is why adding the NFL Blitz roster format later is a
JSON change rather than new code.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from core.address_db import FieldDefinition, GameDefinition, TableDefinition
from core.rom_manager import ROMManager
from editors.base import AVAILABLE, Availability, EditorModule


@dataclass
class Record:
    """One row of a table, decoded."""

    index: int
    offset: int
    values: Dict[str, Any]

    def get(self, field_id: str, default: Any = None) -> Any:
        return self.values.get(field_id, default)


class TableEditor(EditorModule):
    """Reads and writes the records of one table."""

    module_id = "table"
    title = "Table Editor"
    #: Set by subclasses; the id of the table in the game definition.
    table_id: str = ""

    def __init__(
        self,
        rom: ROMManager,
        definition: Optional[GameDefinition] = None,
        table_id: Optional[str] = None,
    ) -> None:
        super().__init__(rom, definition)
        if table_id:
            self.table_id = table_id

    # -- availability ------------------------------------------------------

    @property
    def table(self) -> Optional[TableDefinition]:
        if self.definition is None:
            return None
        return self.definition.table(self.table_id)

    def availability(self) -> Availability:
        blocked = self._require_definition()
        if blocked is not None:
            return blocked
        table = self.table
        if table is None:
            return Availability(
                False,
                f"The definition for {self.definition.display_name} does not "
                f"describe a {self.table_id!r} table yet.",
                (f"the location and layout of the {self.table_id} table",),
            )
        if not table.is_discovered:
            missing = []
            if table.base_address is None:
                missing.append("base address")
            if table.record_size <= 0:
                missing.append("record size")
            if table.record_count <= 0:
                missing.append("record count")
            if not table.fields:
                missing.append("field layout")
            return Availability(
                False,
                f"The {table.name} table is declared but not yet located: "
                f"missing {', '.join(missing)}.",
                tuple(missing),
            )
        if table.base_address + table.record_size * table.record_count > self.rom.size:
            return Availability(
                False,
                f"The {table.name} table runs past the end of this ROM "
                f"({self.rom.size} bytes). The definition may be for a "
                "different build.",
                ("a definition matching this ROM build",),
            )
        return AVAILABLE

    def _require_available(self) -> TableDefinition:
        status = self.availability()
        if not status:
            raise RuntimeError(status.reason)
        assert self.table is not None
        return self.table

    # -- reading -----------------------------------------------------------

    @property
    def record_count(self) -> int:
        table = self.table
        return table.record_count if table and table.is_discovered else 0

    def fields(self) -> List[FieldDefinition]:
        table = self.table
        return list(table.fields) if table else []

    def read_field(self, index: int, field: FieldDefinition) -> Any:
        table = self._require_available()
        offset = table.record_offset(index) + field.offset
        if field.kind == "text":
            return self.rom.read_text(offset, field.size)
        return self.rom.read_value(offset, field.data_type, field.endian)

    def read_record(self, index: int) -> Record:
        table = self._require_available()
        return Record(
            index=index,
            offset=table.record_offset(index),
            values={f.id: self.read_field(index, f) for f in table.fields},
        )

    def records(self) -> Iterator[Record]:
        for index in range(self.record_count):
            yield self.read_record(index)

    # -- writing -----------------------------------------------------------

    def write_field(self, index: int, field_id: str, value: Any) -> None:
        """Write one field of one record, as a single undo step."""
        table = self._require_available()
        field = table.field(field_id)
        if field is None:
            raise KeyError(f"table {table.id!r} has no field {field_id!r}")
        offset = table.record_offset(index) + field.offset
        label = f"{table.name} #{index}: {field.name} = {value}"
        if field.kind == "text":
            self.rom.write_text(offset, str(value), field.size, description=label)
        else:
            self.rom.write_value(
                offset, value, field.data_type, field.endian, description=label
            )

    def write_record(self, index: int, values: Dict[str, Any]) -> None:
        """Write several fields of one record as a single undo step."""
        table = self._require_available()
        with self.rom.undo.transaction(f"Edit {table.name} record #{index}"):
            for field_id, value in values.items():
                self.write_field(index, field_id, value)

    # -- CSV ---------------------------------------------------------------

    def export_csv(self, path: str | Path) -> Path:
        """Write every record to CSV, one column per field."""
        table = self._require_available()
        path = Path(path)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Index"] + [f.name for f in table.fields])
            for record in self.records():
                writer.writerow(
                    [record.index] + [record.values[f.id] for f in table.fields]
                )
        return path

    def import_csv(self, path: str | Path) -> int:
        """Read a CSV back in.  Returns how many records were changed.

        Columns are matched by field *name* (the header this class writes)
        and unknown columns are ignored, so a spreadsheet with extra notes
        columns still imports.  The whole import is one undo step; if any row
        fails, nothing is written.
        """
        table = self._require_available()
        path = Path(path)
        by_name = {f.name: f for f in table.fields}
        changed = 0
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))

        with self.rom.undo.transaction(f"Import {path.name} into {table.name}"):
            for row_number, row in enumerate(rows, start=2):
                raw_index = (row.get("Index") or "").strip()
                if not raw_index:
                    continue
                try:
                    index = int(raw_index)
                except ValueError as exc:
                    raise ValueError(
                        f"{path.name} line {row_number}: {raw_index!r} is not a "
                        "record index"
                    ) from exc
                if not 0 <= index < table.record_count:
                    raise ValueError(
                        f"{path.name} line {row_number}: record index {index} is "
                        f"outside 0..{table.record_count - 1}"
                    )
                values: Dict[str, Any] = {}
                for column, raw in row.items():
                    field = by_name.get(column)
                    if field is None or raw is None:
                        continue
                    values[field.id] = parse_field_cell(field, raw, path.name, row_number)
                before = self.read_record(index).values
                if any(before.get(k) != v for k, v in values.items()):
                    for field_id, value in values.items():
                        self.write_field(index, field_id, value)
                    changed += 1
        return changed


def parse_field_cell(field: FieldDefinition, raw: str, source: str, line: int) -> Any:
    """Convert one CSV cell into the value the field expects."""
    raw = raw.strip()
    if field.kind == "text":
        return raw
    if not raw:
        return 0
    try:
        if field.data_type.is_float:
            return float(raw)
        return int(raw, 0)
    except ValueError as exc:
        raise ValueError(
            f"{source} line {line}: {raw!r} is not a valid value for "
            f"{field.name} ({field.data_type.value})"
        ) from exc
