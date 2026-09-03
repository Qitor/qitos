"""Bridge MCP server tools into QitOS FunctionTool instances.

The bridge is the key integration point: it discovers tools from an MCP
server, converts their JSON Schema into QitOS ``ToolSpec`` objects, and
wraps each one in a ``FunctionTool`` whose ``execute`` method calls the
MCP server remotely.

Usage::

    from qitos.mcp import MCPServerStdio, mcp_server_to_function_tools, ToolFilter

    server = MCPServerStdio(command="npx", args=["-y", "@mcp/server-fs", "/tmp"])
    await server.connect()

    tools = await mcp_server_to_function_tools(
        server,
        tool_filter=ToolFilter(blocked_tool_names={"dangerous_op"}),
        name_prefix="fs",
    )
    # tools is a list of FunctionTool instances ready to register
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, List, Optional

from ..core.artifact import ArtifactRef
from ..core.tool import FunctionTool, ToolMeta, ToolSpec
from ..core.tool_result import ToolResult
from ..core.tool_runtime import ToolResourceKind
from .filter import ToolFilter
from .schema_convert import convert_mcp_schema_to_tool_spec
from .server import MCPServer


async def mcp_server_to_function_tools(
    server: MCPServer,
    tool_filter: Optional[ToolFilter] = None,
    name_prefix: Optional[str] = None,
) -> List[FunctionTool]:
    """Convert all tools exposed by an MCP server into QitOS FunctionTools.

    :param server: A connected MCP server instance.
    :param tool_filter: Optional filter to include/exclude tools by name.
    :param name_prefix: Optional prefix to disambiguate tool names when
        multiple MCP servers are bridged into the same registry.  When
        provided, tool names become ``{prefix}__{original_name}``.
    :returns: A list of ``FunctionTool`` instances, one per MCP tool that
        passes the filter.
    """
    mcp_tools = await server.list_tools()
    tools: List[FunctionTool] = []

    for mcp_tool in mcp_tools:
        # Apply filter
        if tool_filter is not None and not tool_filter.matches(mcp_tool.name):
            continue

        # Convert schema
        spec = convert_mcp_schema_to_tool_spec(mcp_tool, name_prefix=name_prefix)

        # Create a closure that captures the server and original tool name
        tool_name = mcp_tool.name
        tool = _make_function_tool(server, tool_name, spec)
        tools.append(tool)

    return tools


def _make_function_tool(
    server: MCPServer,
    original_name: str,
    spec: ToolSpec,
) -> FunctionTool:
    """Create a FunctionTool that delegates to ``server.call_tool``.

    The function wrapped by FunctionTool must accept keyword arguments
    matching the spec parameters, plus optional ``runtime_context``.
    The wrapper remains async.  ActionExecutor owns awaiting, timeout,
    lifecycle, effect, and terminal publication for MCP exactly as for other
    tool resource kinds.
    """
    # Build a callable with the right parameter signature for FunctionTool.
    # FunctionTool inspects the function signature to build its own spec,
    # but we want to use *our* spec (from MCP schema conversion).  We
    # override by providing a ToolMeta that carries our custom spec fields.

    async def _mcp_caller(**kwargs: Any) -> Any:
        """Call the MCP tool via the server transport."""
        result = await server.call_tool(original_name, kwargs)
        encoded = json.dumps(
            result, sort_keys=True, ensure_ascii=False, default=str
        ).encode("utf-8")
        if len(encoded) <= 16_000:
            model_output: Any = result
            artifacts: tuple[ArtifactRef, ...] = ()
            truncated = False
            omitted: dict[str, int] = {}
        else:
            digest = hashlib.sha256(encoded).hexdigest()
            model_output = {
                "status": "success",
                "summary": "MCP result retained as a canonical artifact reference",
                "byte_length": len(encoded),
            }
            artifacts = (
                ArtifactRef(
                    artifact_id=f"sha256:{digest}",
                    resolver_key="tool-result-output",
                    sha256=digest,
                    media_type="application/json",
                    byte_length=len(encoded),
                    encoding="utf-8",
                    sensitivity="internal",
                    model_summary="Full MCP result retained outside the bounded model projection",
                ),
            )
            truncated = True
            omitted = {"model_output_characters": max(0, len(encoded) - 16_000)}
        return ToolResult(
            output=result,
            model_output=model_output,
            tool_name=spec.name,
            artifact_refs=artifacts,
            truncated=truncated,
            complete=True,
            omitted=omitted,
            provenance={"transport": "mcp", "server_digest": hashlib.sha256(server.name.encode()).hexdigest()},
        )

    # Attach metadata so FunctionTool uses our spec fields.
    meta = ToolMeta(
        name=spec.name,
        description=spec.description,
        input_schema=spec.input_schema,
        permissions=spec.permissions,
        read_only=spec.read_only,
        concurrency_safe=spec.concurrency_safe,
        needs_approval=spec.needs_approval,
        lifecycle=ToolResourceKind.MCP_REQUEST,
        effect=spec.effect,
    )

    tool = FunctionTool(_mcp_caller, meta=meta)
    # Override the spec with our MCP-derived spec (preserving all fields)
    spec.lifecycle = ToolResourceKind.MCP_REQUEST
    tool.spec = spec
    return tool
