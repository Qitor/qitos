"""ToolSet protocol for grouped capabilities with lifecycle."""

from __future__ import annotations

from typing import Any, Protocol


class ToolSet(Protocol):
    name: str
    version: str

    def setup(self, context: dict[str, Any]) -> None:
        """Prepare resources before runtime starts."""

    def teardown(self, context: dict[str, Any]) -> None:
        """Release resources after runtime ends."""

    def tools(self) -> list[Any]:
        """Return tool callables or BaseTool objects."""


__all__ = ["ToolSet"]
