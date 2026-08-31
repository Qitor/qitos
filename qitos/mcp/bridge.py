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

import asyncio
import inspect
from typing import Any, Dict, List, Optional

from ..core.tool import FunctionTool, ToolMeta, ToolSpec
from ..core.tool_runtime import ToolResourceKind
from .filter import ToolFilter
from .schema_convert import convert_mcp_schema_to_tool_spec
from .server import MCPServer, MCPToolInfo


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
    Since the actual MCP call is async but FunctionTool.execute is
    synchronous, we use ``asyncio.run`` or the running loop to bridge.
    """
    # Build a callable with the right parameter signature for FunctionTool.
    # FunctionTool inspects the function signature to build its own spec,
    # but we want to use *our* spec (from MCP schema conversion).  We
    # override by providing a ToolMeta that carries our custom spec fields.

    async def _mcp_caller(**kwargs: Any) -> Any:
        """Call the MCP tool via the server transport."""
        runtime_context = kwargs.pop("runtime_context", None)
        env = kwargs.pop("env", None)
        ops = kwargs.pop("ops", None)
        # Strip other QitOS-injected kwargs that MCP does not need.
        kwargs.pop("file_ops", None)
        kwargs.pop("process_ops", None)

        result = await server.call_tool(original_name, kwargs)
        return result

    def _sync_wrapper(**kwargs: Any) -> Any:
        """Synchronous wrapper that runs the async MCP call."""
        runtime_context = kwargs.get("runtime_context")
        env = kwargs.get("env")
        ops = kwargs.get("ops")
        # Remove QitOS-injected kwargs before passing to MCP
        call_kwargs = {
            k: v for k, v in kwargs.items()
            if k not in ("runtime_context", "env", "ops", "file_ops", "process_ops")
        }
        if runtime_context is not None:
            call_kwargs["runtime_context"] = runtime_context
        if env is not None:
            call_kwargs["env"] = env
        if ops is not None:
            call_kwargs["ops"] = ops

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            # We're inside an already-running event loop (e.g. Engine is async).
            # Create a Future and schedule the coroutine.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _mcp_caller(**call_kwargs))
                return future.result()
        else:
            return asyncio.run(_mcp_caller(**call_kwargs))

    # Attach metadata so FunctionTool uses our spec fields.
    meta = ToolMeta(
        name=spec.name,
        description=spec.description,
        input_schema=spec.input_schema,
        read_only=spec.read_only,
        concurrency_safe=spec.concurrency_safe,
        lifecycle=ToolResourceKind.MCP_REQUEST,
    )

    tool = FunctionTool(_sync_wrapper, meta=meta)
    # Override the spec with our MCP-derived spec (preserving all fields)
    spec.lifecycle = ToolResourceKind.MCP_REQUEST
    tool.spec = spec
    return tool
