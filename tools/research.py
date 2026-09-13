"""Research Mode: a lab notebook for ROM reverse engineering.

Finding out what an address does is an experimental process -- change one
value, run the game, write down what happened.  Doing that in a text file
loses the link between the note and the address; doing it in your head
loses it entirely.  An :class:`Experiment` records the address, the before
and after values, what you expected, and what actually happened.

Experiments are stored as JSON next to the bookmark database and can be
exported to share with other researchers.
"""

from __future__ import annotations

import csv
import json
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core import paths
from core.datatypes import DataType, Endian

#: Where an experiment stands.
OUTCOMES = ("untested", "no effect", "partial", "confirmed", "crashed", "inconclusive")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Experiment:
    """One recorded "I changed X and Y happened"."""

    name: str
    address: Optional[int] = None
    data_type: DataType = DataType.U16
    endian: Endian = Endian.BIG
    original_value: Optional[float] = None
    modified_value: Optional[float] = None
    hypothesis: str = ""
    result: str = ""
    outcome: str = "untested"
    notes: str = ""
    rom_key: str = ""
    rom_label: str = ""
    #: Optional link back to the bookmark this experiment is about.
    bookmark_id: str = ""
    tags: List[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created: str = field(default_factory=_now)
    updated: str = field(default_factory=_now)

    @property
    def address_hex(self) -> str:
        return f"0x{self.address:08X}" if self.address is not None else "-"

    @property
    def delta(self) -> Optional[float]:
        if self.original_value is None or self.modified_value is None:
            return None
        try:
            return self.modified_value - self.original_value
        except TypeError:
            return None

    def touched(self) -> "Experiment":
        return replace(self, updated=_now())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "address": self.address,
            "data_type": self.data_type.value,
            "endian": self.endian.value,
            "original_value": self.original_value,
            "modified_value": self.modified_value,
            "hypothesis": self.hypothesis,
            "result": self.result,
            "outcome": self.outcome,
            "notes": self.notes,
            "rom_key": self.rom_key,
            "rom_label": self.rom_label,
            "bookmark_id": self.bookmark_id,
            "tags": list(self.tags),
            "created": self.created,
            "updated": self.updated,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Experiment":
        address = payload.get("address")
        if isinstance(address, str) and address.strip():
            address = int(address, 0)
        return cls(
            name=payload.get("name", "Untitled experiment"),
            address=address if address is None else int(address),
            data_type=DataType.from_string(payload.get("data_type", "u16")),
            endian=Endian(payload.get("endian", "big")),
            original_value=payload.get("original_value"),
            modified_value=payload.get("modified_value"),
            hypothesis=payload.get("hypothesis", ""),
            result=payload.get("result", ""),
            outcome=payload.get("outcome", "untested"),
            notes=payload.get("notes", ""),
            rom_key=payload.get("rom_key", ""),
            rom_label=payload.get("rom_label", ""),
            bookmark_id=payload.get("bookmark_id", ""),
            tags=list(payload.get("tags", [])),
            id=payload.get("id") or uuid.uuid4().hex[:12],
            created=payload.get("created", _now()),
            updated=payload.get("updated", _now()),
        )


class ResearchLog:
    """A persisted collection of experiments."""

    FILE_FORMAT = "nfl-blitz-mod-suite/research"
    FILE_VERSION = 1

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else paths.research_dir() / "experiments.json"
        self._experiments: Dict[str, Experiment] = {}
        self._listeners: List[Any] = []

    def add_listener(self, callback) -> None:
        self._listeners.append(callback)

    def _notify(self) -> None:
        for callback in list(self._listeners):
            callback()

    # -- persistence -------------------------------------------------------

    def load(self) -> "ResearchLog":
        if not self.path.exists():
            return self
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self
        self._experiments = {}
        for entry in payload.get("experiments", []):
            try:
                experiment = Experiment.from_dict(entry)
            except (KeyError, ValueError):
                continue
            self._experiments[experiment.id] = experiment
        self._notify()
        return self

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "format": self.FILE_FORMAT,
                    "version": self.FILE_VERSION,
                    "saved": _now(),
                    "experiments": [e.to_dict() for e in self.sorted()],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return self.path

    # -- mutation ----------------------------------------------------------

    def add(self, experiment: Experiment) -> Experiment:
        self._experiments[experiment.id] = experiment
        self._notify()
        return experiment

    def update(self, experiment: Experiment) -> Experiment:
        experiment = experiment.touched()
        self._experiments[experiment.id] = experiment
        self._notify()
        return experiment

    def remove(self, experiment_id: str) -> bool:
        removed = self._experiments.pop(experiment_id, None) is not None
        if removed:
            self._notify()
        return removed

    # -- queries -----------------------------------------------------------

    def get(self, experiment_id: str) -> Optional[Experiment]:
        return self._experiments.get(experiment_id)

    def __len__(self) -> int:
        return len(self._experiments)

    def __iter__(self):
        return iter(self.sorted())

    def sorted(self) -> List[Experiment]:
        """Newest first -- a lab notebook reads backwards."""
        return sorted(self._experiments.values(), key=lambda e: e.created, reverse=True)

    def query(
        self,
        text: str = "",
        outcome: Optional[str] = None,
        rom_key: Optional[str] = None,
    ) -> List[Experiment]:
        needle = text.strip().lower()
        results = []
        for experiment in self.sorted():
            if outcome and experiment.outcome != outcome:
                continue
            if rom_key is not None and experiment.rom_key and experiment.rom_key != rom_key:
                continue
            if needle:
                haystack = " ".join(
                    [
                        experiment.name,
                        experiment.hypothesis,
                        experiment.result,
                        experiment.notes,
                        experiment.address_hex,
                        " ".join(experiment.tags),
                    ]
                ).lower()
                if needle not in haystack:
                    continue
            results.append(experiment)
        return results

    def for_address(self, address: int) -> List[Experiment]:
        return [e for e in self.sorted() if e.address == address]

    def stats(self) -> Dict[str, int]:
        counts = {outcome: 0 for outcome in OUTCOMES}
        for experiment in self._experiments.values():
            counts[experiment.outcome] = counts.get(experiment.outcome, 0) + 1
        counts["total"] = len(self._experiments)
        return counts

    # -- export ------------------------------------------------------------

    def export_markdown(self, path: str | Path) -> Path:
        """Write the log as Markdown -- the format research notes get shared in."""
        path = Path(path)
        lines = ["# ROM research log", "", f"Exported {_now()}", ""]
        for experiment in self.sorted():
            lines.append(f"## {experiment.name}")
            lines.append("")
            lines.append(f"- **Address:** {experiment.address_hex} "
                         f"({experiment.data_type.value}, {experiment.endian.value} endian)")
            lines.append(f"- **Original value:** {experiment.original_value}")
            lines.append(f"- **Modified value:** {experiment.modified_value}")
            lines.append(f"- **Outcome:** {experiment.outcome}")
            if experiment.rom_label:
                lines.append(f"- **ROM:** {experiment.rom_label}")
            if experiment.tags:
                lines.append(f"- **Tags:** {', '.join(experiment.tags)}")
            lines.append("")
            if experiment.hypothesis:
                lines.append(f"**Hypothesis:** {experiment.hypothesis}")
                lines.append("")
            if experiment.result:
                lines.append(f"**Result:** {experiment.result}")
                lines.append("")
            if experiment.notes:
                lines.append(f"**Notes:** {experiment.notes}")
                lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def export_csv(self, path: str | Path) -> Path:
        path = Path(path)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                ["Name", "Address", "Type", "Original", "Modified", "Outcome",
                 "Hypothesis", "Result", "Notes", "ROM", "Created"]
            )
            for e in self.sorted():
                writer.writerow(
                    [e.name, e.address_hex, e.data_type.value, e.original_value,
                     e.modified_value, e.outcome, e.hypothesis, e.result,
                     e.notes, e.rom_label or e.rom_key, e.created]
                )
        return path

    def import_json(self, path: str | Path, replace_existing: bool = False) -> int:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        added = 0
        for entry in payload.get("experiments", []):
            try:
                experiment = Experiment.from_dict(entry)
            except (KeyError, ValueError):
                continue
            if experiment.id in self._experiments and not replace_existing:
                continue
            self._experiments[experiment.id] = experiment
            added += 1
        if added:
            self._notify()
        return added
