"""Parser protocol definitions for Engine integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, Optional, Protocol, TypeVar

from ..core.decision import Decision


ActionT = TypeVar("ActionT")


class Parser(Protocol, Generic[ActionT]):
    def parse(self, raw_output: Any, context: Optional[Dict[str, Any]] = None) -> Decision[ActionT]:
        """Parse raw output into a validated Decision."""


class BaseParser(ABC, Generic[ActionT]):
    @abstractmethod
    def parse(self, raw_output: Any, context: Optional[Dict[str, Any]] = None) -> Decision[ActionT]:
        """Parse raw output into Decision."""


__all__ = ["Parser", "BaseParser"]
