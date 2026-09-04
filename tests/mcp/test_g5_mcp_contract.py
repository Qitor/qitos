"""MCP results traverse the canonical permission/effect/artifact boundaries."""
import asyncio
import json
from types import SimpleNamespace

from qitos.core.action import Action
from qitos.core.tool_registry import ToolRegistry
from qitos.engine.action_executor import ActionExecutor
from qitos.kit.artifact.store import FileArtifactStore
from qitos.kit.permission.pipeline import PermissionMode, PermissionPipeline
from qitos.mcp.bridge import mcp_server_to_function_tools
from qitos.mcp.server import MCPToolInfo


class Server:
    name = "g5-owned-mcp-fixture"

    def __init__(self, delay=0):
        self.calls = []
        self.delay = delay

    async def list_tools(self):
        return [MCPToolInfo(name="sample", description="sample", input_schema={"type": "object", "properties": {}})]

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        await asyncio.sleep(self.delay)
        return {"text": "mcp-result" * 3000}


def executor(server, resolver=None, pipeline=None):
    tool = asyncio.run(mcp_server_to_function_tools(server))[0]
    tool.spec.timeout_s = .02 if server.delay else 2
    engine = SimpleNamespace(agent=SimpleNamespace(config={"artifact_resolver": resolver}))
    return ActionExecutor(ToolRegistry().register(tool), engine=engine, auto_approve=True,
                          permission_pipeline=pipeline)


def test_mcp_large_result_is_retrievable_and_runtime_context_stays_local(tmp_path):
    server = Server()
    resolver = FileArtifactStore(tmp_path / "artifacts")
    result = executor(server, resolver).execute_one(Action("sample", {}))
    assert result.status == "success"
    assert result.effect_state == "committed"
    assert result.truncated and result.complete
    reference = result.artifact_refs[0]
    assert json.loads(resolver.resolve(reference).body) == result.output
    assert server.calls == [("sample", {})]
    assert len(json.dumps(result.to_model_dict())) < 5000


def test_mcp_missing_artifact_store_is_typed_and_does_not_invent_retrievability():
    result = executor(Server()).execute_one(Action("sample", {}))
    assert result.status == "error"
    assert result.error_code == "artifact_resolver_unavailable"
    assert result.outcome_unknown and result.reconciliation_required
    assert result.artifact_refs == ()


def test_mcp_permission_denial_precedes_dispatch():
    server = Server()
    result = executor(server, pipeline=PermissionPipeline(mode=PermissionMode.PLAN)).execute_one(Action("sample", {}))
    assert result.status in {"error", "skipped"}
    assert not server.calls
    assert result.effect_state == "rejected"


def test_mcp_timeout_preserves_remote_effect_uncertainty():
    server = Server(.1)
    result = executor(server).execute_one(Action("sample", {}))
    assert result.status == "timed_out"
    assert result.outcome_unknown and result.reconciliation_required
    assert result.retry_disposition == "requires_reconciliation"
    assert len(server.calls) == 1
