"""Interactive approval cannot be mistaken for provider recovery."""
from dataclasses import replace
import pytest

from qitos.config import build_agent_composition
from qitos.core.function_tool_decorator import function_tool
from qitos.core.session import SessionContractError
from test_s4_lane_a_public_authoring import _config, _FinalModel


def test_session_pending_approval_does_not_resend_model_request(tmp_path):
    calls, effects = [], []

    @function_tool(needs_approval=True)
    def guarded():
        effects.append(1)
        return "applied"

    class Model(_FinalModel):
        qitos_protocol = "json_decision_multi_v1"

        def call_raw(self, messages, **options):
            calls.append(messages)
            if len(calls) > 1:
                return {"choices": [{"message": {"content": "unexpected resend"}}]}
            return {"choices": [{"message": {"content": None, "tool_calls": [
                {"id": "guarded-call", "type": "function", "function": {"name": "guarded", "arguments": "{}"}}]}}]}

    config = replace(_config(tmp_path), protocol="json_decision_multi_v1", tool_options={"auto_approve": False})
    with build_agent_composition(config, model_override=Model()) as composition:
        composition.tool_registry.register(guarded)
        session = composition.session("apply after explicit approval")
        session.run()
        assert not effects
        assert len(calls) == 1
        assert session.lifecycle.value == "waiting_input"
        before = session.current_head
        child = session.fork(operation_id="fork_" + "1" * 32)
        assert session.current_head == before
        assert child.session_id != session.session_id
        restored = composition.restore(session.session_id)
        with pytest.raises(SessionContractError) as rejected:
            restored.run(steering="Steering is not an approval receipt.")
        assert rejected.value.metadata["capability"] == "session.approval.resume"
        assert len(calls) == 1 and not effects
