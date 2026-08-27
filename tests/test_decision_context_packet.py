"""Decision-context packet invariant (Batch M, 05a1c82)."""

from __future__ import annotations

from qitos import Action, AgentModule, Decision, Engine, ToolRegistry, tool
from qitos.core.state import StateSchema
from qitos.engine import RuntimeBudget
from qitos.engine._model_runtime import DecisionContextConfigurationError
from qitos.engine._model_runtime import _ModelRuntime


def _runtime() -> _ModelRuntime:
    class _Agent(AgentModule[StateSchema, dict, Action]):
        def __init__(self) -> None:
            registry = ToolRegistry()

            @tool(name="noop")
            def noop() -> dict[str, str]:
                return {"ok": "1"}

            registry.register(noop)
            super().__init__(tool_registry=registry)

        def init_state(self, task: str, **kwargs) -> StateSchema:
            return StateSchema(task=task, max_steps=1)

        def decide(self, state, observation) -> Decision[Action]:
            return Decision.final("done")

        def reduce(self, state, observation, decision) -> StateSchema:
            return state

    engine = Engine(agent=_Agent(), budget=RuntimeBudget(max_steps=1))
    return engine._model_runtime


AUTHORITATIVE = "<DECISION_CONTEXT version=\"1\">current authoritative state</DECISION_CONTEXT>"


def test_valid_packet_passes_through_unchanged() -> None:
    runtime = _runtime()
    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": f"task text\n\n{AUTHORITATIVE}"},
    ]
    delivery: dict = {"requested": "user"}

    rebuilt, sidecar = runtime._normalize_decision_context_packet(
        messages=messages, authoritative_source=AUTHORITATIVE, delivery=delivery
    )

    assert rebuilt == messages
    assert sidecar["rebuild_required"] is False
    assert sidecar["authoritative_context"] == AUTHORITATIVE
    assert sidecar["before_count"] == 1 and sidecar["after_count"] == 1


def test_stale_blocks_are_stripped_and_current_block_rebuilt() -> None:
    runtime = _runtime()
    stale = "<DECISION_CONTEXT version=\"1\">stale from a previous turn</DECISION_CONTEXT>"
    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": f"earlier turn\n{stale}"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "next turn"},
    ]
    delivery: dict = {"requested": "user"}

    rebuilt, sidecar = runtime._normalize_decision_context_packet(
        messages=messages, authoritative_source=AUTHORITATIVE, delivery=delivery
    )

    blocks = runtime._decision_context_blocks(rebuilt)
    assert len(blocks) == 1
    assert blocks[0] == AUTHORITATIVE
    assert sidecar["rebuild_required"] is True
    assert sidecar["reason"] in {"duplicate", "mismatch"}
    assert sidecar["before_count"] == 1
    assert sidecar["after_count"] == 1
    assert delivery["effective"] == "user"
    assert rebuilt[-1] == {"role": "user", "content": AUTHORITATIVE}


def test_duplicate_blocks_collapse_to_one_current_block() -> None:
    runtime = _runtime()
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": f"a\n{AUTHORITATIVE}"},
        {"role": "user", "content": f"b\n{AUTHORITATIVE}"},
    ]
    delivery: dict = {"requested": "user"}

    rebuilt, sidecar = runtime._normalize_decision_context_packet(
        messages=messages, authoritative_source=AUTHORITATIVE, delivery=delivery
    )

    assert sidecar["reason"] == "duplicate"
    assert sidecar["before_count"] == 2
    assert len(runtime._decision_context_blocks(rebuilt)) == 1


def test_invalid_authoritative_source_reports_rebuild_without_touching_packet() -> None:
    runtime = _runtime()
    messages = [{"role": "user", "content": "packet"}]
    delivery: dict = {"requested": "user"}

    rebuilt, sidecar = runtime._normalize_decision_context_packet(
        messages=messages, authoritative_source="", delivery=delivery
    )

    assert rebuilt == messages
    assert sidecar["rebuild_required"] is True
    assert sidecar["reason"] == "authoritative_invalid"
    assert sidecar["authoritative_context"] == ""


def test_strip_decision_context_content_handles_block_lists() -> None:
    from qitos.engine._model_runtime import _strip_decision_context_content

    content = [
        {"type": "text", "text": f"keep\n{AUTHORITATIVE}"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}},
    ]
    stripped = _strip_decision_context_content(content)

    assert stripped[0]["text"] == "keep"
    assert "DECISION_CONTEXT" not in stripped[0]["text"]
    assert stripped[1] == content[1]


def test_configuration_error_is_a_runtime_error_subtype() -> None:
    assert issubclass(DecisionContextConfigurationError, RuntimeError)
