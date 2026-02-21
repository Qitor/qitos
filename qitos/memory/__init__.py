"""Memory module exports."""

from .adapter import MemoryAdapter, MemoryRecord
from .adapters import WindowMemory, SummaryMemory, VectorMemory

# Legacy conversational memories kept for backward utility.
from .base import BaseMemory, MemoryMixin, ConversationMemory
from .window import SlidingWindowMemory, FixedWindowMemory, UnlimitedMemory

# Compatibility exports for existing tests/integrations.
from .v2 import BaseMemoryV2, WindowMemoryV2, SummaryMemoryV2, VectorMemoryV2

__all__ = [
    "MemoryAdapter",
    "MemoryRecord",
    "WindowMemory",
    "SummaryMemory",
    "VectorMemory",
    "BaseMemory",
    "MemoryMixin",
    "ConversationMemory",
    "SlidingWindowMemory",
    "FixedWindowMemory",
    "UnlimitedMemory",
    "BaseMemoryV2",
    "WindowMemoryV2",
    "SummaryMemoryV2",
    "VectorMemoryV2",
]
