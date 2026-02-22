"""Benchmark adapter abstractions for converting external datasets into QitOS Tasks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

from qitos.core.task import Task


@dataclass
class BenchmarkSource:
    """Metadata describing one benchmark data source."""

    name: str
    split: str
    subset: Optional[str] = None
    version: Optional[str] = None


class BenchmarkAdapter(ABC):
    """Base adapter interface for converting benchmark samples to Task objects."""

    source: BenchmarkSource

    @abstractmethod
    def to_tasks(self, records: Iterable[Mapping[str, Any]], split: str, limit: Optional[int] = None) -> list[Task]:
        """Convert iterable records into validated QitOS Task objects."""

