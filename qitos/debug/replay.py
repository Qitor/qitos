"""Replay and time-travel debugger for trace artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .breakpoints import Breakpoint
from .inspector import build_inspector_payload, compare_steps


@dataclass
class ReplaySnapshot:
    cursor: int
    current_event: Optional[Dict[str, Any]]
    current_step: Optional[Dict[str, Any]]


class ReplaySession:
    """Load and replay a run from trace artifacts."""

    def __init__(self, run_dir: str):
        self.run_dir = Path(run_dir)
        self.events = self._load_jsonl(self.run_dir / "events.jsonl")
        self.steps = self._load_jsonl(self.run_dir / "steps.jsonl")
        self.manifest = self._load_json(self.run_dir / "manifest.json")
        self.cursor = 0

    def reset(self) -> None:
        self.cursor = 0

    def has_next(self) -> bool:
        return self.cursor < len(self.events)

    def step_into(self) -> ReplaySnapshot:
        if not self.has_next():
            return ReplaySnapshot(cursor=self.cursor, current_event=None, current_step=None)

        event = self.events[self.cursor]
        self.cursor += 1
        step = self._find_step(event.get("step_id"))
        return ReplaySnapshot(cursor=self.cursor, current_event=event, current_step=step)

    def step_over(self) -> ReplaySnapshot:
        if not self.has_next():
            return ReplaySnapshot(cursor=self.cursor, current_event=None, current_step=None)

        start_step = self.events[self.cursor].get("step_id")
        last_event = None
        while self.has_next() and self.events[self.cursor].get("step_id") == start_step:
            last_event = self.events[self.cursor]
            self.cursor += 1

        step = self._find_step(start_step)
        return ReplaySnapshot(cursor=self.cursor, current_event=last_event, current_step=step)

    def run_until_breakpoint(self, breakpoints: List[Breakpoint]) -> ReplaySnapshot:
        while self.has_next():
            snapshot = self.step_into()
            event = snapshot.current_event
            if event is None:
                return snapshot

            if any(bp.matches(event) for bp in breakpoints):
                return snapshot

        return ReplaySnapshot(cursor=self.cursor, current_event=None, current_step=None)

    def fork_with_step_override(self, step_id: int, decision_override: Dict[str, Any]) -> Dict[str, Any]:
        """Return in-memory forked replay view with modified decision for the target step."""
        forked_steps = [dict(s) for s in self.steps]
        for step in forked_steps:
            if int(step.get("step_id", -1)) == step_id:
                step["decision"] = decision_override
                break
        return {
            "manifest": dict(self.manifest),
            "events": [dict(e) for e in self.events],
            "steps": forked_steps,
        }

    def inspect_step(self, step_id: int) -> Optional[Dict[str, Any]]:
        step = self._find_step(step_id)
        if step is None:
            return None
        return build_inspector_payload(step, self.manifest).to_dict()

    def compare_steps(self, step_a: int, step_b: int) -> Optional[Dict[str, Any]]:
        a = self._find_step(step_a)
        b = self._find_step(step_b)
        if a is None or b is None:
            return None
        return compare_steps(a, b)

    def _find_step(self, step_id: Any) -> Optional[Dict[str, Any]]:
        if step_id is None:
            return None
        for step in self.steps:
            if int(step.get("step_id", -1)) == int(step_id):
                return step
        return None

    def _load_jsonl(self, path: Path) -> List[Dict[str, Any]]:
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def _load_json(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
