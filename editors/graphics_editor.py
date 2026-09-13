"""Graphics editor -- not yet implemented.

This module exists so the sidebar entry, the routing and the availability
reporting are real, and so the eventual implementation drops into a shaped
hole rather than requiring the application to be rearranged.

What is genuinely required before this can work, in order:

1. Locating texture data in the ROM.  NFL Blitz's asset layout has not been
   reverse engineered here, and N64 games commonly store textures inside
   compressed or game-specific archives rather than as raw pixel data at a
   fixed address.
2. Determining the texture formats actually used (RGBA16, RGBA32, IA8, CI4,
   CI8 and their palettes are all plausible; assuming one format for
   everything would be wrong).
3. A repacking strategy that respects whatever container the assets live in.

Until step 1 is done there is nothing honest for this editor to show, so it
reports itself unavailable and points at the discovery tools.  See
``docs/ROADMAP.md`` for the planned approach.
"""

from __future__ import annotations

from editors.base import Availability, EditorModule


class GraphicsEditor(EditorModule):
    """Placeholder that reports what is missing rather than faking a preview."""

    module_id = "graphics"
    title = "Graphics Editor"
    subtitle = "Planned - texture locations and formats are not yet known"

    #: Formats the decoder will need to support once assets are located.
    PLANNED_FORMATS = ("RGBA16", "RGBA32", "IA4", "IA8", "IA16", "I4", "I8", "CI4", "CI8")

    def availability(self) -> Availability:
        blocked = self._require_rom()
        if blocked is not None:
            return blocked
        missing = self.missing_tables("textures")
        return Availability(
            False,
            "Graphics editing is not implemented yet. No NFL Blitz texture "
            "table has been located, and this suite will not guess at one. "
            "Use the Hex/Data Explorer and ROM Comparison to locate asset "
            "data; the roadmap in docs/ROADMAP.md describes the plan.",
            tuple(missing) or ("a texture table in the game definition",),
        )
