"""A custom notes AgentModule through the public Engine/Session path."""
from dataclasses import dataclass, field

from qitos import Action, AgentModule, Decision, Engine, StateSchema, ToolRegistry
from qitos.engine.action_executor import ActionExecutionPolicy
from qitos.engine.runtime import RuntimeComposition
from notes import summarize_note


# docs:start agent
@dataclass
class NotesState(StateSchema):
    titles: list[str] = field(default_factory=list)


class NotesAgent(AgentModule):
    def __init__(self):
        registry = ToolRegistry()
        registry.register(summarize_note)
        super().__init__(tool_registry=registry)

    def init_state(self, task, **kwargs):
        return NotesState(task=task, max_steps=3)

    def decide(self, state, observation):
        if state.titles:
            return Decision.final(", ".join(state.titles))
        return Decision.act([
            Action(name="summarize_note", args={"index": index}) for index in (0, 1)
        ])

    def reduce(self, state, observation, decision):
        state.titles.extend(item["output"]["title"] for item in observation.get("action_results", []))
        return state
# docs:end agent


# docs:start run
def main():
    for mode in ("sequential", "parallel"):
        engine = Engine(NotesAgent(), runtime=RuntimeComposition(),
                        action_execution_policy=ActionExecutionPolicy(mode=mode, max_concurrency=2))
        result = engine.session("Index the two notes").run()
        assert result.state.titles == ["Session", "Artifact"]
        assert result.state.final_result == "Session, Artifact"
        print(f"{mode}: Session, Artifact; process_local=true")
# docs:end run


if __name__ == "__main__":
    main()
