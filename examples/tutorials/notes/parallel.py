"""Force reverse completion while retaining declaration order in reduce."""
from threading import Event

from qitos import Action, Decision, Engine, ToolRegistry
from qitos.core.function_tool_decorator import function_tool
from qitos.engine.action_executor import ActionExecutionPolicy
from qitos.engine.runtime import RuntimeComposition
from custom_agent import NotesAgent
from notes import NOTES

# Explicit test instrumentation for one local invocation, not persistent state.
second_finished = Event()
completion_order = []


@function_tool(read_only=True, concurrency_safe=True)
def analyze_note(index: int) -> dict:
    """An in-memory fixture that controls completion order without file/network I/O."""
    if index == 0:
        if not second_finished.wait(5):
            raise RuntimeError("This fixture requires two parallel workers")
    completion_order.append(index)
    if index == 1:
        second_finished.set()
    return {"title": NOTES[index].split(":", 1)[0]}


class ParallelNotesAgent(NotesAgent):
    def __init__(self):
        super().__init__()
        self.tool_registry = ToolRegistry()
        self.tool_registry.register(analyze_note)

    def decide(self, state, observation):
        if state.titles:
            return Decision.final(", ".join(state.titles))
        return Decision.act([Action(name="analyze_note", args={"index": i}) for i in (0, 1)])


def run():
    second_finished.clear()
    completion_order.clear()
    engine = Engine(ParallelNotesAgent(), runtime=RuntimeComposition(),
                    action_execution_policy=ActionExecutionPolicy(mode="parallel", max_concurrency=2))
    result = engine.session("Compare completion with declaration order").run()
    assert completion_order == [1, 0]
    assert result.state.titles == ["Session", "Artifact"]
    print("completion=[1, 0]; declaration=[0, 1]; titles=Session, Artifact")


if __name__ == "__main__":
    run()
