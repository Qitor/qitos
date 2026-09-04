"""MCP server abstract base class and tool info dataclass."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class MCPToolInfo:
    """Descriptor for a single tool exposed by an MCP server.

    Mirrors the ``tools/list`` response item from the MCP specification:
    each tool has a name, a human-readable description, and a JSON Schema
    describing its input parameters.
    """

    name: str
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)


class MCPServer(ABC):
    """Abstract base for MCP server transports.

    Subclasses implement the transport-specific details (stdio, HTTP, etc.)
    while this contract defines the lifecycle that consumers rely on:

    1. ``connect()``  -- establish the transport and perform the MCP handshake.
    2. ``list_tools()`` -- discover available tools.
    3. ``call_tool()``  -- invoke a tool by name with JSON-serialisable arguments.
    4. ``cleanup()``    -- tear down the transport gracefully.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable identifier for this server connection."""

    @abstractmethod
    async def connect(self) -> None:
        """Open the transport and complete the MCP initialization handshake.

        After this method returns, the server is ready to accept
        ``list_tools`` and ``call_tool`` requests.
        """

    @abstractmethod
    async def cleanup(self) -> None:
        """Shut down the transport and release all resources."""

    @abstractmethod
    async def list_tools(self) -> List[MCPToolInfo]:
        """Return the list of tools exposed by the connected MCP server.

        Corresponds to the ``tools/list`` MCP method.
        """

    @abstractmethod
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Invoke a tool on the connected MCP server.

        Corresponds to the ``tools/call`` MCP method.

        :param tool_name: The exact tool name as returned by ``list_tools``.
        :param arguments: JSON-serialisable dict of argument values.
        :returns: The tool result payload (typically a dict or list).
        """
