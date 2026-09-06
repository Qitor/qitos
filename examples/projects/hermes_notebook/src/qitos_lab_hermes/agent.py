"""Facts, episodic recall and selectively loaded procedures are distinct."""

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path

from qitos.core.agent_module import AgentModule
from qitos.core.function_tool_decorator import function_tool
from qitos.core.memory import MemoryRecord
from qitos.core.state import StateSchema
from qitos.kit.memory.memdir_memory import MemdirMemory
from qitos.kit.tool.library.base import ToolArtifact
from qitos.kit.tool.library.sqlite_store import SqliteToolLibrary


@dataclass
class ResearchState(StateSchema):
    recent: list[dict] = field(default_factory=list)
    selected_skills: dict[str, int] = field(default_factory=dict)


class ResearchAgent(AgentModule):
    def __init__(self, *, skills, **kwargs):
        super().__init__(**kwargs)
        self.skills = skills  # Borrowed resolver, never serialized into State.

    def init_state(self, task, **kwargs):
        return ResearchState(task=task, max_steps=self.config.get("max_steps", 80))

    def base_persona_prompt(self, state):
        return (
            "You maintain a research notebook across independent Sessions. "
            "Facts, past episode summaries and reusable procedures are different resources. "
            "Recall first, inspect fresh evidence, reconcile changes, and cite sources. "
            "Only remember explicit useful facts; do not store guesses as facts."
        )

    def task_policy_prompt(self, state):
        return (
            "Use search_memory for facts, search_history for past outcomes, catalog_skills "
            "for descriptions and load_skill only for a relevant complete procedure. "
            "Save a reusable verification procedure when justified. Forget superseded facts "
            "with forget_fact. Use submit_report with JSON conclusion, metrics, citations, "
            "limitations; finish afterwards. State missing evidence honestly."
        )

    # docs:start design
    def prepare(self, state):
        selected = []
        for name, version in state.selected_skills.items():
            item = self.skills.get_version(name, version)
            if item is None:
                raise ValueError("required_skill_version_missing")
            selected.append(
                {"name": name, "version": version, "instructions": item.source}
            )
        # Full selected documents are part of the current task input. A request
        # budget failure must be explicit; slicing instructions is not recall.
        return json.dumps(
            {
                "task": state.task,
                "selected_skills": selected,
                "recent_results": state.recent[-4:],
            }
        )

    def reduce(self, state, observation, decision):
        for item in observation.action_results:
            output = item.output
            if (
                isinstance(output, dict)
                and "instructions" in output
                and "sha256" in output
            ):
                state.selected_skills[output["name"]] = output["version"]
        state.recent.extend(
            item.to_model_dict(max_chars=6000) for item in observation.action_results
        )
        state.recent = state.recent[-8:]
        return state

    # docs:end design


class NotebookFactory:
    """The application owns its bound resources; composition borrows them."""

    def __init__(self, task, *, root, shared_root=None, variant="default", **kwargs):
        self.task, self.variant = task, variant
        location = Path(shared_root or root / "notebook")
        location.mkdir(parents=True, exist_ok=True)
        self.memory = MemdirMemory(str(location / "facts"), create=True)
        self.history = MemdirMemory(str(location / "episodes"), create=True)
        self.skills = SqliteToolLibrary(
            location / "skills.sqlite3", namespace="research"
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.skills.close()

    def __call__(self, *, config, model, tool_registry, protocol, parser):
        @function_tool(read_only=True)
        def search_memory(query: str):
            """Search durable factual memory, not the current conversation."""
            return (
                []
                if self.variant == "no-memory"
                else [
                    asdict(row)
                    for row in self.memory.retrieve(
                        {"contains": query, "max_items": 12}
                    )
                ]
            )

        @function_tool(read_only=True)
        def search_history(query: str):
            """Recall source-labelled prior episode summaries."""
            return (
                []
                if self.variant == "no-memory"
                else [
                    asdict(row)
                    for row in self.history.retrieve(
                        {"contains": query, "max_items": 8}
                    )
                ]
            )

        @function_tool(concurrency_safe=False)
        def remember_fact(identity: str, content: str, source: str):
            """Create/update an explicitly sourced fact; identity stays stable."""
            if self.variant == "no-memory":
                return {"status": "disabled"}
            self.memory.append(
                MemoryRecord(
                    "reference", content + "\nSource: " + source, 0, record_id=identity
                )
            )
            return {"stored": identity}

        @function_tool(concurrency_safe=False)
        def forget_fact(identity: str):
            """Delete a fact only from this notebook namespace."""
            return {"removed": self.memory.delete(identity)}

        @function_tool(read_only=True)
        def catalog_skills(query: str):
            """List matching procedure names/descriptions, without loading bodies."""
            return self.skills.catalog(query, limit=8)

        @function_tool(read_only=True)
        def load_skill(name: str):
            """Load one complete procedure with exact version and source digest."""
            item = self.skills.get(name)
            if item is None or not item.active:
                raise ValueError("skill_unavailable")
            return {
                "name": name,
                "version": item.version,
                "instructions": item.source,
                "sha256": hashlib.sha256(item.source.encode()).hexdigest(),
                "provenance": item.metadata,
            }

        @function_tool(concurrency_safe=False)
        def save_procedure(name: str, description: str, instructions: str, source: str):
            """Store a procedural document, not verified executable code."""
            item = self.skills.add_or_update(
                ToolArtifact(
                    name,
                    description,
                    instructions,
                    metadata={"source": source, "validation": "document_only"},
                )
            )
            return {"name": item.name, "version": item.version}

        @function_tool(concurrency_safe=False)
        def submit_report(report_json: str):
            """Submit structured findings and persist a labelled episode summary."""
            report = json.loads(report_json)
            if not isinstance(report, dict):
                raise ValueError("report_must_be_object")
            if self.variant != "no-memory":
                self.history.append(
                    MemoryRecord(
                        "runtime",
                        json.dumps(
                            {
                                "task": self.task.get("id", self.task["task"]),
                                "report": report,
                                "verification": "not_yet_independently_checked",
                            }
                        ),
                        0,
                    )
                )
            return {"submitted_report": report}

        for tool in (
            search_memory,
            search_history,
            remember_fact,
            forget_fact,
            catalog_skills,
            load_skill,
            save_procedure,
            submit_report,
        ):
            tool_registry.register(tool)
        return ResearchAgent(
            llm=model,
            tool_registry=tool_registry,
            skills=self.skills,
            model_protocol=protocol.id,
            max_steps=config.max_steps,
            model_parser=parser,
        )


def build_factory(task, **resources):
    return NotebookFactory(task, **resources)
