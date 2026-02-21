"""Compatibility shim for canonical memory adapter contracts."""

from __future__ import annotations

from ..adapter import MemoryAdapter as BaseMemoryV2
from ..adapter import MemoryRecord

__all__ = ["MemoryRecord", "BaseMemoryV2"]
