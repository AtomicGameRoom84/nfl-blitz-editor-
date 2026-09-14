"""Graphics Editor page -- deliberately inert.

Nothing on this page pretends to work. It states what is missing, what the
plan is, and which tools to use in the meantime. See
:mod:`editors.graphics_editor` and ``docs/ROADMAP.md``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton

from editors.graphics_editor import GraphicsEditor
from ui.pages.base_page import Page, UnavailableBanner, card, hint


class GraphicsEditorPage(Page):
    page_key = "graphics"
    page_title = "Graphics Editor"
    page_subtitle = "Planned for a later phase — nothing here is implemented yet"
    scrollable = True

    def build(self) -> None:
        self.editor = GraphicsEditor(self.state.rom, self.state.definition)

        self._banner = UnavailableBanner()
        self.body.addWidget(self._banner)

        plan_card, plan_layout = card("WHAT THIS NEEDS FIRST")
        steps = QLabel(
            "1.  <b>Locate the asset data.</b> NFL Blitz's texture layout has not "
            "been reverse engineered here. N64 titles frequently keep graphics "
            "inside compressed or game-specific archives rather than as raw "
            "pixels at a fixed address, so this may need a container parser "
            "rather than a table of offsets.<br><br>"
            "2.  <b>Identify the formats actually in use.</b> "
            + ", ".join(GraphicsEditor.PLANNED_FORMATS)
            + " are all plausible. Assuming one format for everything would "
            "produce convincing-looking garbage, which is worse than showing "
            "nothing.<br><br>"
            "3.  <b>Work out repacking.</b> Imported PNGs have to go back in a "
            "form the game can load, respecting whatever container and size "
            "limits the originals live in."
        )
        steps.setWordWrap(True)
        steps.setTextFormat(Qt.RichText)
        plan_layout.addWidget(steps)
        self.body.addWidget(plan_card)

        tools_card, tools_layout = card("WHAT YOU CAN DO NOW")
        tools_layout.addWidget(
            hint(
                "Texture data usually looks distinctive in a hex view: long runs "
                "of structured, non-zero, non-ASCII bytes. Find a candidate "
                "region with the Hex/Data Explorer, bookmark it under the "
                "Graphics category, and record what you learn in Research Mode. "
                "When enough is known to describe a texture table in a game "
                "definition, this page gets built on top of it."
            )
        )
        buttons = QHBoxLayout()
        for label, key in (
            ("Open Hex/Data Explorer", "hex"),
            ("Open ROM Comparison", "compare"),
            ("Open Research Mode", "research"),
        ):
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, k=key: self.state.navigate(k))
            buttons.addWidget(button)
        buttons.addStretch(1)
        tools_layout.addLayout(buttons)
        self.body.addWidget(tools_card)
        self.body.addStretch(1)

        self.state.definitionChanged.connect(self.refresh)
        self.state.romLoaded.connect(self.refresh)
        self.state.romClosed.connect(self.refresh)
        self.refresh()

    def on_activated(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.editor.set_definition(self.state.definition)
        self.editor.rom = self.state.rom
        self._banner.show_status(
            self.editor.availability(), "Graphics editing is not implemented"
        )
