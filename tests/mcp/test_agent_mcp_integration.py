"""Tests for AgentModule MCP integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from qitos.core.agent_module import AgentModule
from qitos.core.state import StateSchema
from qitos.mcp.server import MCPServer, MCPToolInfo


class FakeMCPServer(MCPServer):
    """Fake MCP server for testing."""

    def __init__(self, name: str = "fake", tools: list | None = None):
        self._name = name
        self._tools = tools or [
            MCPToolInfo(name="read", description="Read a file", input_schema={"type": "object"}),
        ]
        self.connected = False
        self.cleaned_up = False

    @property
    def name(self) -> str:
        return self._name

    async def connect(self) -> None:
        self.connected = True

    async def cleanup(self) -> None:
        self.cleaned_up = True

    async def list_tools(self) -> list[MCPToolInfo]:
        return self._tools

    async def call_tool(self, name: str, arguments: dict) -> Any:
        return f"result of {name}"


@dataclass
class DummyState(StateSchema):
    task: str = ""


class DummyAgent(AgentModule[DummyState, Any, Any]):
    name = "dummy"

    def init_state(self, task: str, **kwargs: Any) -> DummyState:
        return DummyState(task=task)

    def reduce(self, state: DummyState, observation: Any, decision: Any) -> DummyState:
        return state


class TestAgentModuleMCPServers:
    def test_mcp_servers_default_empty(self):
        agent = DummyAgent()
        assert agent.mcp_servers == []

    def test_mcp_servers_passed_to_init(self):
        server = FakeMCPServer()
        agent = DummyAgent(mcp_servers=[server])
        assert len(agent.mcp_servers) == 1
        assert agent.mcp_servers[0] is server

    def test_engine_connects_mcp_servers_on_run(self):
        server = FakeMCPServer()
        agent = DummyAgent(mcp_servers=[server])
        # Patch the engine's run loop to avoid actual execution
        from qitos.engine.engine import Engine

        engine = Engine(agent)

        # Mock the main run loop to just test MCP lifecycle
        with patch.object(engine, "_normalize_task", return_value=(None, "test task")):
            with patch.object(engine.agent, "init_state", return_value=DummyState(task="test")):
                # Directly test connect/cleanup
                engine._connected_mcp_servers = []
                engine._connect_mcp_servers()
                assert server.connected
                assert len(engine._connected_mcp_servers) == 1

                engine._cleanup_mcp_servers()
                assert server.cleaned_up
                assert engine._connected_mcp_servers == []

    def test_engine_mcp_connect_failure_doesnt_crash(self):
        """If an MCP server fails to connect, the engine should continue."""
        bad_server = MagicMock()
        bad_server.connect.side_effect = RuntimeError("Connection failed")

        agent = DummyAgent(mcp_servers=[bad_server])
        from qitos.engine.engine import Engine

        engine = Engine(agent)
        engine._connected_mcp_servers = []
        engine._connect_mcp_servers()

        # Should not have crashed, and the bad server should not be in connected list
        assert len(engine._connected_mcp_servers) == 0

    def test_engine_mcp_cleanup_failure_doesnt_crash(self):
        """If cleanup fails, other servers should still be cleaned up."""
        server1 = MagicMock()
        server1.cleanup.side_effect = RuntimeError("Cleanup failed")
        server2 = MagicMock()

        agent = DummyAgent(mcp_servers=[server1, server2])
        from qitos.engine.engine import Engine

        engine = Engine(agent)
        engine._connected_mcp_servers = [server1, server2]
        engine._cleanup_mcp_servers()

        # Both should have been attempted
        server1.cleanup.assert_called_once()
        server2.cleanup.assert_called_once()
        assert engine._connected_mcp_servers == []
