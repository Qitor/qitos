"""Run a custom State/AgentModule through the existing Engine Session.

This advanced in-process example has no model or external-effect tools. Its
Memory checkpoint store is process-local, not a clean-process restore example.
"""
from dataclasses import dataclass

from qitos import Action, AgentModule, Decision, Engine, StateSchema, ToolRegistry
from qitos.core.function_tool_decorator import function_tool
from qitos.engine.runtime import RuntimeComposition
from qitos.engine.action_executor import ActionExecutionPolicy


@dataclass
class CountingState(StateSchema):
    completed: int = 0


@function_tool(read_only=True, concurrency_safe=True)
def square(value: int) -> int:
    """Pure arithmetic, safe to call concurrently."""
    return value * value


class CountingAgent(AgentModule):
    def __init__(self):
        registry = ToolRegistry()
        registry.register(square)
        super().__init__(tool_registry=registry)

    def init_state(self, task, **kwargs):
        return CountingState(task=task, max_steps=3)

    def decide(self, state, observation):
        if state.completed:
            return Decision.final("squares complete")
        return Decision.act([Action(name="square", args={"value": value}) for value in (3, 4)])

    def reduce(self, state, observation, decision):
        state.completed += len(observation.get("action_results", []))
        return state


def main():
    runtime = RuntimeComposition()
    engine = Engine(CountingAgent(), runtime=runtime,
                    action_execution_policy=ActionExecutionPolicy(mode="parallel", max_concurrency=2))
    result = engine.session("Square 3 and 4").run()
    assert result.state.final_result == "squares complete"
    assert result.state.completed == 2
    print("squares complete; completed=2; process_local=true")


if __name__ == "__main__":
    main()
