"""Composition root for the current stable snapshot component owners."""

from __future__ import annotations

from .request_view import CONVERSATION_SNAPSHOT_COMPONENT_CODEC
from .session import (
    CORE_SNAPSHOT_COMPONENT_CODECS,
    SnapshotComponentRegistry,
)
from .tool_result import TOOL_EFFECTS_SNAPSHOT_COMPONENT_CODEC
from .work_graph import WORK_GRAPH_SNAPSHOT_COMPONENT_CODEC


STABLE_SNAPSHOT_COMPONENT_REGISTRY = SnapshotComponentRegistry(
    (
        *CORE_SNAPSHOT_COMPONENT_CODECS,
        CONVERSATION_SNAPSHOT_COMPONENT_CODEC,
        TOOL_EFFECTS_SNAPSHOT_COMPONENT_CODEC,
        WORK_GRAPH_SNAPSHOT_COMPONENT_CODEC,
    )
)


__all__ = ["STABLE_SNAPSHOT_COMPONENT_REGISTRY"]
