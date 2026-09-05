"""Memdir-style file memory with a lightweight MEMORY.md index."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from qitos.core.memory import Memory, MemoryRecord, MemoryResourceError

_VALID_TYPES = {"user", "feedback", "project", "reference", "runtime"}


class MemdirMemory(Memory):
    """Persist text records with stable identity and fresh disk retrieval.

    Restore is the default and fails if a bound root is missing. Pass
    ``create=True`` only to explicitly initialize a namespace. ``reset`` and
    ``evict`` affect the append-time cache only; persistent deletion is external.
    Arbitrary Python/JSON content and metadata are not a durable round-trip API.
    """

    def __init__(
        self,
        memory_dir: str = ".qitos/memory",
        *,
        global_memory_dir: str | None = None,
        create: bool = False,
        max_index_entries: int = 200,
        max_index_chars: int = 25_000,
    ):
        self.memory_dir = Path(memory_dir).expanduser().resolve()
        self.global_memory_dir = (
            Path(global_memory_dir).expanduser().resolve()
            if global_memory_dir
            else None
        )
        self.max_index_entries = max(10, int(max_index_entries))
        self.max_index_chars = max(2000, int(max_index_chars))
        self._records: List[MemoryRecord] = []
        if create:
            self._ensure_layout()
        self._require_roots()

    def append(self, record: MemoryRecord) -> None:
        self._require_roots()
        if not isinstance(record.content, str):
            raise TypeError("MemdirMemory persists text records only")
        if not re.fullmatch(r"[a-zA-Z0-9_.:-]{1,128}", record.record_id):
            raise ValueError("memory record_id must be a logical identity")
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", record.role):
            raise ValueError("memory role must be a logical label")
        memory_type = self._memory_type_from_record(record)
        folder = self.memory_dir / memory_type
        folder.mkdir(parents=True, exist_ok=True)
        stem = hashlib.sha256(record.record_id.encode()).hexdigest()
        existing = sorted(self.memory_dir.glob(f"*/{stem}.md"))
        path = existing[0] if existing else folder / f"{stem}.md"
        created_at = datetime.now(timezone.utc).isoformat()
        body = record.content
        frontmatter = [
            "---",
            f"record_id: {record.record_id}",
            f"type: {memory_type}",
            f"role: {record.role}",
            f"step_id: {int(record.step_id)}",
            f"created_at: {created_at}",
            "---",
            body,
        ]
        path.write_text("\n".join(frontmatter), encoding="utf-8")
        self._records = [item for item in self._records if item.record_id != record.record_id]
        self._records.append(record)
        self._append_index_entry(path=path, record=record, memory_type=memory_type)

    def retrieve(
        self,
        query: Optional[Dict[str, Any]] = None,
        state: Any = None,
        observation: Any = None,
    ) -> List[MemoryRecord]:
        _ = state
        _ = observation
        self._require_roots()
        query = query or {}
        roles = (
            {str(item) for item in list(query.get("roles") or [])}
            if isinstance(query.get("roles"), list)
            else None
        )
        memory_type = str(query.get("type") or "").strip().lower() or None
        contains = str(query.get("contains") or "").strip().lower() or None
        max_items = max(1, int(query.get("max_items", 50) or 50))

        items: List[MemoryRecord] = []
        for path in self._iter_memory_files():
            parsed = self._read_memory_file(path)
            if parsed is None:
                continue
            if roles and parsed.role not in roles:
                continue
            meta_type = str(parsed.metadata.get("type") or "").strip().lower()
            if memory_type and meta_type != memory_type:
                continue
            if contains and contains not in str(parsed.content).lower():
                continue
            items.append(parsed)
        # Disk is authoritative: never merge stale append-time cache records.
        by_id = {item.record_id: item for item in items}
        items = sorted(by_id.values(), key=lambda item: (int(item.step_id), item.record_id))
        if max_items > 0:
            items = items[-max_items:]
        return items

    def summarize(self, max_items: int = 30) -> str:
        """Render current records, never stale index snippets after external edits."""
        records = self.retrieve({"max_items": max_items})
        lines = ["# MEMORY", ""]
        lines.extend(f"- role={item.role} step={item.step_id}: {item.content}"
                     for item in records)
        return "\n".join(lines)[:self.max_index_chars]

    def evict(self) -> int:
        if len(self._records) <= self.max_index_entries:
            return 0
        removed = len(self._records) - self.max_index_entries
        self._records = self._records[-self.max_index_entries :]
        return removed

    def reset(self, run_id: Optional[str] = None) -> None:
        _ = run_id
        self._records = []

    def _require_roots(self) -> None:
        roots = [self.memory_dir]
        if self.global_memory_dir is not None:
            roots.append(self.global_memory_dir)
        if any(not root.is_dir() for root in roots):
            raise MemoryResourceError("bound memory root is unavailable")

    def _ensure_layout(self) -> None:
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        for bucket in sorted(_VALID_TYPES):
            (self.memory_dir / bucket).mkdir(parents=True, exist_ok=True)
        index = self.memory_dir / "MEMORY.md"
        if not index.exists():
            index.write_text(
                "# MEMORY\n\n<!-- memdir index: newest entries appended below -->\n",
                encoding="utf-8",
            )

    def _append_index_entry(
        self, *, path: Path, record: MemoryRecord, memory_type: str
    ) -> None:
        index = self.memory_dir / "MEMORY.md"
        rel = str(path.relative_to(self.memory_dir))
        snippet = str(record.content or "").replace("\n", " ").strip()[:150]
        line = (
            f"- type={memory_type} role={record.role} step={record.step_id} "
            f"path={rel} note={snippet}"
        )
        existing = index.read_text(encoding="utf-8").splitlines()
        header = existing[:2] if len(existing) >= 2 else ["# MEMORY", ""]
        body = existing[2:] if len(existing) >= 2 else []
        body.append(line)
        if len(body) > self.max_index_entries:
            body = body[-self.max_index_entries :]
        merged = "\n".join(header + body).strip() + "\n"
        if len(merged) > self.max_index_chars:
            merged = merged[-self.max_index_chars :]
            if not merged.startswith("# MEMORY"):
                merged = "# MEMORY\n\n" + merged
        index.write_text(merged, encoding="utf-8")

    def _memory_type_from_record(self, record: MemoryRecord) -> str:
        raw = str((record.metadata or {}).get("type") or "").strip().lower()
        if raw in _VALID_TYPES:
            return raw
        role = str(record.role or "").strip().lower()
        if role in {"feedback", "user", "reference"}:
            return role
        return "project"

    def _iter_memory_files(self) -> List[Path]:
        roots = [self.memory_dir]
        if self.global_memory_dir is not None:
            roots.append(self.global_memory_dir)
        files: List[Path] = []
        for root in roots:
            if not root.exists():
                continue
            for path in sorted(root.rglob("*.md")):
                if path.name == "MEMORY.md":
                    continue
                files.append(path)
        return files

    def _read_memory_file(self, path: Path) -> MemoryRecord | None:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            raise MemoryResourceError("bound memory record is unavailable") from None
        metadata: Dict[str, Any] = {}
        body = text
        if text.startswith("---\n"):
            marker = "\n---\n"
            end = text.find(marker, 4)
            if end > 0:
                header = text[4:end]
                body = text[end + len(marker) :]
                for raw in header.splitlines():
                    line = raw.strip()
                    if ":" not in line:
                        continue
                    key, value = line.split(":", 1)
                    metadata[str(key).strip()] = str(value).strip()
        role = str(metadata.get("role") or "memory")
        step_id = 0
        step_raw = metadata.get("step_id")
        if str(step_raw or "").isdigit():
            step_id = int(str(step_raw))
        else:
            hit = re.search(r"step=(\d+)", text)
            if hit:
                step_id = int(hit.group(1))
        record_id = metadata.pop("record_id", None)
        if record_id is None:
            # Historical files have no persisted ID. Their namespace-relative
            # location is a stable fallback; absolute host paths never escape.
            root = self.memory_dir
            scope = "local"
            if not path.is_relative_to(root) and self.global_memory_dir is not None:
                root = self.global_memory_dir
                scope = "global"
            relative = scope + ":" + path.relative_to(root).as_posix()
            record_id = "legacy_" + hashlib.sha256(relative.encode()).hexdigest()
            body = body.strip()
        return MemoryRecord(
            role=role, content=body, step_id=step_id,
            metadata=metadata, record_id=record_id,
        )


__all__ = ["MemdirMemory"]
