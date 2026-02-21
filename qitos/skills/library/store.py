"""In-memory skill library with simple versioning and retrieval."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from .base import BaseSkillLibrary, SkillArtifact


class InMemorySkillLibrary(BaseSkillLibrary):
    def __init__(self):
        self._skills: Dict[str, SkillArtifact] = {}

    def add_or_update(self, artifact: SkillArtifact) -> SkillArtifact:
        existing = self._skills.get(artifact.name)
        if existing:
            artifact.version = existing.version + 1
            artifact.created_at = existing.created_at
        artifact.updated_at = datetime.now(timezone.utc).isoformat()
        self._skills[artifact.name] = artifact
        return artifact

    def get(self, name: str) -> Optional[SkillArtifact]:
        return self._skills.get(name)

    def search(self, query: str, top_k: int = 5) -> List[SkillArtifact]:
        q = query.lower().strip()
        if not q:
            return self.list_active()[:top_k]

        scored = []
        for art in self._skills.values():
            if not art.active:
                continue
            hay = " ".join([art.name, art.description, " ".join(art.tags)]).lower()
            score = hay.count(q)
            if score > 0:
                scored.append((score, art))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [art for _, art in scored[:top_k]]

    def list_active(self) -> List[SkillArtifact]:
        return [art for art in self._skills.values() if art.active]

    def deprecate(self, name: str) -> bool:
        art = self._skills.get(name)
        if art is None:
            return False
        art.active = False
        art.updated_at = datetime.now(timezone.utc).isoformat()
        return True
