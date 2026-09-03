"""MCP server transport over stdio (subprocess with JSON-RPC)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

from .server import MCPServer, MCPToolInfo

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# JSON-RPC helpers
# --------------------------------------------------------------------------- #

_JSONRPC_VERSION = "2.0"


def _make_request(method: str, params: Optional[Dict[str, Any]] = None, request_id: int = 1) -> str:
    """Build a JSON-RPC request string."""
    payload: Dict[str, Any] = {
        "jsonrpc": _JSONRPC_VERSION,
        "method": method,
        "id": request_id,
    }
    if params is not None:
        payload["params"] = params
    return json.dumps(payload)


def _make_notification(method: str, params: Optional[Dict[str, Any]] = None) -> str:
    """Build a JSON-RPC notification (no id, server must not reply)."""
    payload: Dict[str, Any] = {
        "jsonrpc": _JSONRPC_VERSION,
        "method": method,
    }
    if params is not None:
        payload["params"] = params
    return json.dumps(payload)


def _parse_response(raw: str) -> Dict[str, Any]:
    """Parse a JSON-RPC response, raising on error objects."""
    data = json.loads(raw)
    if "error" in data:
        err = data["error"]
        raise RuntimeError(
            f"MCP JSON-RPC error (code={err.get('code')}): {err.get('message')}"
        )
    return data


# --------------------------------------------------------------------------- #
# MCPServerStdio
# --------------------------------------------------------------------------- #


class MCPServerStdio(MCPServer):
    """Connect to an MCP server launched as a local subprocess.

    The subprocess speaks the MCP protocol over its stdin/stdout using
    newline-delimited JSON-RPC.  This transport is the most common way to
    integrate with MCP servers that ship as command-line tools (e.g. language
    servers, database connectors, etc.).

    Usage::

        server = MCPServerStdio(command="npx", args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"])
        await server.connect()
        tools = await server.list_tools()
        result = await server.call_tool("read_file", {"path": "/tmp/hello.txt"})
        await server.cleanup()
    """

    def __init__(
        self,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        name: Optional[str] = None,
    ) -> None:
        self._command = command
        self._args: List[str] = list(args or [])
        self._env = env
        self._cwd = cwd
        self._name = name or f"stdio:{command}"
        self._process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0

    @property
    def name(self) -> str:
        return self._name

    # -- lifecycle ----------------------------------------------------------- #

    async def connect(self) -> None:
        """Launch the subprocess and complete the MCP initialization handshake."""
        # Do not leak the controller's complete environment to an MCP child.
        env = {
            key: os.environ[key]
            for key in ("PATH", "LANG", "LC_ALL", "SYSTEMROOT", "TMPDIR")
            if key in os.environ
        }
        if self._env:
            env.update(self._env)

        self._process = await asyncio.create_subprocess_exec(
            self._command,
            *self._args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._cwd,
            env=env,
        )
        logger.info("MCP stdio process started (pid=%s)", self._process.pid)

        # MCP initialization handshake: initialize request -> initialized notification
        init_result = await self._send_request(
            "initialize",
            params={
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "qitos-mcp-client", "version": "0.1.0"},
            },
        )
        logger.debug("MCP initialize response: %s", init_result)

        # Send the initialized notification (no id, no response expected)
        await self._send_notification("notifications/initialized")
        logger.info("MCP stdio handshake complete for %s", self._name)

    async def cleanup(self) -> None:
        """Terminate the subprocess and clean up."""
        if self._process is None:
            return
        proc = self._process
        self._process = None
        try:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        except ProcessLookupError:
            pass
        logger.info("MCP stdio process terminated for %s", self._name)

    # -- MCP operations ------------------------------------------------------ #

    async def list_tools(self) -> List[MCPToolInfo]:
        """Request the list of tools from the MCP server."""
        result = await self._send_request("tools/list", params={})
        tools_data = result.get("tools", [])
        return [
            MCPToolInfo(
                name=t.get("name", ""),
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
            )
            for t in tools_data
        ]

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Invoke a tool on the MCP server."""
        result = await self._send_request(
            "tools/call",
            params={"name": tool_name, "arguments": arguments},
        )
        # The MCP spec returns content arrays; extract text or return raw.
        content = result.get("content", [])
        if isinstance(content, list) and len(content) == 1:
            item = content[0]
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                # Try to parse as JSON; fall back to raw string.
                try:
                    return json.loads(text)
                except (json.JSONDecodeError, TypeError):
                    return text
        return result

    # -- internal JSON-RPC transport ----------------------------------------- #

    async def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _send_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send a JSON-RPC request and read the response."""
        if self._process is None or self._process.stdin is None or self._process.stdout is None:
            raise RuntimeError("MCP server is not connected")

        request_id = await self._next_id()
        request_str = _make_request(method, params=params, request_id=request_id)
        logger.debug("MCP -> %s", request_str)

        self._process.stdin.write((request_str + "\n").encode("utf-8"))
        await self._process.stdin.drain()

        # Read one line from stdout
        raw_line = await self._process.stdout.readline()
        if not raw_line:
            raise RuntimeError("MCP server closed stdout unexpectedly")
        raw = raw_line.decode("utf-8").strip()
        if not raw:
            raise RuntimeError("MCP server returned empty line")

        logger.debug("MCP <- %s", raw)
        response = _parse_response(raw)

        # Validate id matches
        if response.get("id") != request_id:
            logger.warning(
                "MCP response id mismatch: expected %s, got %s",
                request_id,
                response.get("id"),
            )

        return response.get("result", {})

    async def _send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("MCP server is not connected")

        notification_str = _make_notification(method, params=params)
        logger.debug("MCP -> (notification) %s", notification_str)

        self._process.stdin.write((notification_str + "\n").encode("utf-8"))
        await self._process.stdin.drain()
