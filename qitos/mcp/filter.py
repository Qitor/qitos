"""Tool name filtering for MCP server tool discovery.

When bridging MCP tools into QitOS, a ``ToolFilter`` controls which tools
are included and which are excluded.  This is useful when an MCP server
exposes many tools but only a subset is relevant for a given agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Set


@dataclass
class ToolFilter:
    """Decides whether a tool name should be included when bridging MCP tools.

    Evaluation order:

    1. If ``filter_func`` is set, its result is authoritative (``True`` = keep).
    2. If ``allowed_tool_names`` is set, only names in the set are kept.
    3. If ``blocked_tool_names`` is set, names in the set are excluded.
    4. Otherwise the name passes (no filtering).

    You can combine allowed and blocked lists: a name must be in the
    allowed list (if set) AND not in the blocked list.

    Example::

        # Only include "search" and "read"
        f = ToolFilter(allowed_tool_names={"search", "read"})

        # Include everything except "dangerous_tool"
        f = ToolFilter(blocked_tool_names={"dangerous_tool"})

        # Custom logic
        f = ToolFilter(filter_func=lambda name: name.startswith("fs_"))
    """

    allowed_tool_names: Optional[Set[str]] = None
    blocked_tool_names: Optional[Set[str]] = None
    filter_func: Optional[Callable[[str], bool]] = None

    def matches(self, tool_name: str) -> bool:
        """Return ``True`` if the tool name passes the filter.

        :param tool_name: The candidate tool name.
        """
        # 1. Custom filter function takes priority
        if self.filter_func is not None:
            return bool(self.filter_func(tool_name))

        # 2. Allowed list gate (if set, name must be present)
        if self.allowed_tool_names is not None:
            if tool_name not in self.allowed_tool_names:
                return False

        # 3. Blocked list gate (if set, name must be absent)
        if self.blocked_tool_names is not None:
            if tool_name in self.blocked_tool_names:
                return False

        return True
