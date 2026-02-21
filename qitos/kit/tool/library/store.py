"""In-memory skill library with simple versioning and retrieval."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from .base import BaseToolLibrary, ToolArtifact


class InMemoryToolLibrary(BaseToolLibrary):
    def __init__(self):
        self._tools: Dict[str, ToolArtifact] = {}

    def add_or_update(self, artifact: ToolArtifact) -> ToolArtifact:
        existing = self._tools.get(artifact.name)
        if existing:
            artifact.version = existing.version + 1
            artifact.created_at = existing.created_at
        artifact.updated_at = datetime.now(timezone.utc).isoformat()
        self._tools[artifact.name] = artifact
        return artifact

    def get(self, name: str) -> Optional[ToolArtifact]:
        return self._tools.get(name)

    def search(self, query: str, top_k: int = 5) -> List[ToolArtifact]:
        q = query.lower().strip()
        if not q:
            return self.list_active()[:top_k]

        scored = []
        for art in self._tools.values():
            if not art.active:
                continue
            hay = " ".join([art.name, art.description, " ".join(art.tags)]).lower()
            score = hay.count(q)
            if score > 0:
                scored.append((score, art))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [art for _, art in scored[:top_k]]

    def list_active(self) -> List[ToolArtifact]:
        return [art for art in self._tools.values() if art.active]

    def deprecate(self, name: str) -> bool:
        art = self._tools.get(name)
        if art is None:
            return False
        art.active = False
        art.updated_at = datetime.now(timezone.utc).isoformat()
        return True
