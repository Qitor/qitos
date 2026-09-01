"""Executable public-surface budget for G2 convergence contracts."""

from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUDGET = ROOT / "tests" / "fixtures" / "public_surface" / "g2-interface-budget.json"
CATEGORIES = {
    "beginner-facing",
    "extension-facing",
    "persistence-internal",
    "internal-private",
}
DELIBERATE_CATEGORIES = CATEGORIES - {"internal-private"}
REVIEWED_POLICY = {
    "deliberate_module_exports": 159,
    "visible_internal_private_symbols": 3,
    "root_exports": 41,
    "root_export_growth": 0,
    "engine_init_parameters": 34,
    "engine_parameter_growth": 1,
    "growth_authority": "architecture-review-required",
}
REVIEWED_ROOT_EXPORTS = {
    "Action", "AgentModule", "AgentRegistry", "AgentSpec", "AsyncEngine",
    "BaseTool", "BenchmarkRunResult", "ContextConfig", "ContextStrategy",
    "Decision", "Engine", "EngineEvent", "EngineEventType", "EngineResult",
    "Env", "EnvSpec", "EventStream", "ExperimentSpec", "HandoffContext",
    "History", "HistoryPolicy", "Memory", "ModelResponse", "Observation",
    "QitosRuntimeError", "RunSpec", "StateAdapter", "StateSchema",
    "StepSummary", "StopReason", "Task", "TaskBudget", "TaskResource",
    "TaskResult", "ToolPermissionContext", "ToolPermissionDecision",
    "ToolPermissionRule", "ToolRegistry", "ToolResult",
    "ToolValidationResult", "tool",
}
REVIEWED_ENGINE_PARAMETERS = {
    "self", "agent", "agent_registry", "budget", "delegate_depth",
    "shared_memory", "validation_gate", "recovery_handler", "recovery_policy",
    "trace_writer", "parser", "protocol", "stop_criteria", "branch_selector",
    "search", "critics", "env", "history_policy", "hooks", "render_hooks",
    "context_config", "cache_backend", "checkpoint_manager",
    "checkpoint_store", "checkpoint_durability", "permission_pipeline",
    "read_before_write_enforcer", "permission_interaction_callback",
    "loop_detector", "tracing_provider", "interceptors", "auto_approve",
    "action_execution_policy", "runtime",
}


def test_every_g2_module_export_has_exactly_one_interface_classification() -> None:
    payload = json.loads(BUDGET.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "qitos.g2_interface_budget/v2"
    assert payload["reviewed_policy"] == REVIEWED_POLICY
    deliberate_count = 0
    private_count = 0
    for module_name, categories in payload["modules"].items():
        assert set(categories) == CATEGORIES
        flattened = [
            name
            for category in CATEGORIES
            for name in categories[category]
        ]
        assert len(flattened) == len(set(flattened)), module_name
        module = importlib.import_module(module_name)
        deliberate = {
            name
            for category in DELIBERATE_CATEGORIES
            for name in categories[category]
        }
        private = set(categories["internal-private"])
        assert deliberate == set(module.__all__), module_name
        assert private.isdisjoint(module.__all__), module_name
        assert all(hasattr(module, name) for name in private), module_name
        deliberate_count += len(deliberate)
        private_count += len(private)
    assert deliberate_count == REVIEWED_POLICY["deliberate_module_exports"]
    assert private_count == REVIEWED_POLICY["visible_internal_private_symbols"]


def test_g2_contracts_add_no_root_exports_and_no_engine_parameters() -> None:
    import qitos
    from qitos.engine.engine import Engine

    assert set(qitos.__all__) == REVIEWED_ROOT_EXPORTS
    assert len(qitos.__all__) == REVIEWED_POLICY["root_exports"]
    parameters = set(inspect.signature(Engine.__init__).parameters)
    assert parameters == REVIEWED_ENGINE_PARAMETERS
    assert len(parameters) == REVIEWED_POLICY["engine_init_parameters"]
