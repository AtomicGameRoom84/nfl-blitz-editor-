"""Team editor.

Teams in a sports ROM are a table of records (city, nickname, abbreviation,
colours, logo id).  The editing machinery is inherited from
:class:`~editors.table_editor.TableEditor`; this class only names the table
and adds team-specific conveniences such as colour handling and a display
label for the team picker.

No NFL Blitz team table has been located yet, so on a stock ROM this editor
correctly reports itself unavailable.  Populating ``teams`` in the game
definition is all that is needed to bring it to life -- see
``docs/DISCOVERING_ADDRESSES.md``.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from editors.table_editor import Record, TableEditor

#: Field ids this editor understands.  A definition may declare any subset;
#: the UI renders whatever is present.
CITY = "city"
NICKNAME = "nickname"
ABBREVIATION = "abbreviation"
PRIMARY_COLOR = "primary_color"
SECONDARY_COLOR = "secondary_color"
LOGO_ID = "logo_id"
UNIFORM_ID = "uniform_id"


class TeamEditor(TableEditor):
    """Edits the team table declared by the game definition."""

    module_id = "teams"
    title = "Team Editor"
    subtitle = "Names, abbreviations, colours and logo references"
    table_id = "teams"

    def team_label(self, record: Record) -> str:
        """Best available human name for a team record."""
        city = str(record.get(CITY, "") or "").strip()
        nickname = str(record.get(NICKNAME, "") or "").strip()
        abbreviation = str(record.get(ABBREVIATION, "") or "").strip()
        name = " ".join(part for part in (city, nickname) if part)
        if not name:
            name = abbreviation or f"Team {record.index}"
        return f"{record.index:02d}  {name}"

    def team_labels(self) -> List[str]:
        return [self.team_label(record) for record in self.records()]

    # -- colours -----------------------------------------------------------

    def read_color(self, index: int, field_id: str) -> Optional[Tuple[int, int, int]]:
        """Decode a colour field to RGB.

        Two encodings are supported and are chosen by the field's declared
        size: two bytes are RGBA5551 (the N64's usual 16-bit colour) and four
        bytes are RGBA8888.  Anything else returns ``None`` rather than
        guessing.
        """
        table = self._require_available()
        field = table.field(field_id)
        if field is None:
            return None
        raw = self.read_field(index, field)
        if field.size == 2:
            value = int(raw)
            red = (value >> 11) & 0x1F
            green = (value >> 6) & 0x1F
            blue = (value >> 1) & 0x1F
            return (red * 255 // 31, green * 255 // 31, blue * 255 // 31)
        if field.size == 4:
            value = int(raw)
            return ((value >> 24) & 0xFF, (value >> 16) & 0xFF, (value >> 8) & 0xFF)
        return None

    def write_color(self, index: int, field_id: str, rgb: Tuple[int, int, int]) -> None:
        """Encode an RGB triple back into a colour field."""
        table = self._require_available()
        field = table.field(field_id)
        if field is None:
            raise KeyError(f"no colour field {field_id!r} in {table.id!r}")
        red, green, blue = (max(0, min(255, component)) for component in rgb)
        if field.size == 2:
            value = (
                ((red * 31 // 255) << 11)
                | ((green * 31 // 255) << 6)
                | ((blue * 31 // 255) << 1)
                | 1  # alpha bit: opaque
            )
        elif field.size == 4:
            value = (red << 24) | (green << 16) | (blue << 8) | 0xFF
        else:
            raise ValueError(
                f"colour field {field_id!r} is {field.size} bytes; only 2 "
                "(RGBA5551) and 4 (RGBA8888) are supported"
            )
        self.write_field(index, field_id, value)
