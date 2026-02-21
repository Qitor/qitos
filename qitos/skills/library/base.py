"""Skill library primitives for Voyager-style agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class SkillArtifact:
    name: str
    description: str
    source: str
    summary: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    version: int = 1
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    active: bool = True

    def __post_init__(self) -> None:
        if self.summary is None:
            self.summary = self.description


class BaseSkillLibrary:
    def add_or_update(self, artifact: SkillArtifact) -> SkillArtifact:  # pragma: no cover - interface
        raise NotImplementedError

    def get(self, name: str) -> Optional[SkillArtifact]:  # pragma: no cover - interface
        raise NotImplementedError

    def search(self, query: str, top_k: int = 5) -> List[SkillArtifact]:  # pragma: no cover - interface
        raise NotImplementedError

    def list_active(self) -> List[SkillArtifact]:  # pragma: no cover - interface
        raise NotImplementedError

    def deprecate(self, name: str) -> bool:  # pragma: no cover - interface
        raise NotImplementedError
