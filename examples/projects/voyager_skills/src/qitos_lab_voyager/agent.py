"""Automatic curriculum state and verified executable skill accumulation."""

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import re
from typing import Any, Dict, Optional
import json

from qitos.core.agent_module import AgentModule
from qitos.core.function_tool_decorator import function_tool
from qitos.core.state import StateSchema
from qitos.core.tool_result import ToolResult
from qitos.core.tool import ToolPermission
from qitos.kit.tool.library.base import ToolArtifact
from qitos.kit.tool.library.sqlite_store import SqliteToolLibrary
from .extension import verification_tools


@dataclass
class CurriculumState(StateSchema):
    mastered: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)
    feedback: list[dict] = field(default_factory=list)


class SkillAgent(AgentModule):
    def init_state(self, task, **kwargs):
        return CurriculumState(task=task, max_steps=self.config.get("max_steps", 80))

    def base_persona_prompt(self, state):
        return (
            "Learn reusable Python skills through actual execution feedback. "
            "This is a Docker data-programming adaptation of Voyager, not Minecraft. "
            "Inspect requirements, search the skill catalog, load useful complete programs, "
            "compose them when appropriate, test, and only publish verified programs."
        )

    def task_policy_prompt(self, state):
        return (
            "Write the current solution to skill.py. catalog_skills returns only descriptions; "
            "load_skill retrieves one full version into the sandbox, using skill.py for the "
            "current objective and name.py for dependencies. Use verify_project for feedback, "
            "then publish_skill. Never claim a failed program has been mastered. "
            "The current objective is the next curriculum item; previous skills persist "
            "across processes but the environment is disposable."
        )

    # docs:start design
    def prepare(self, state):
        return json.dumps(
            {
                "objective": state.task,
                "mastered": state.mastered,
                "actually_loaded": state.reused,
                "feedback": state.feedback[-3:],
            }
        )

    def reduce(self, state, observation, decision):
        for item in observation.action_results:
            value = item.output
            if isinstance(value, dict):
                if value.get("published"):
                    state.mastered = sorted(set(state.mastered + [value["published"]]))
                if value.get("loaded"):
                    state.reused.append(value["loaded"])
            state.feedback.append(item.to_model_dict(max_chars=6000))
        state.feedback = state.feedback[-6:]
        return state

    # docs:end design


class SkillFactory:
    def __init__(self, task, *, root, shared_root=None, variant="default", **kwargs):
        self.task, self.variant = task, variant
        location = Path(shared_root or root / "library")
        location.mkdir(parents=True, exist_ok=True)
        self.library = SqliteToolLibrary(
            location / "skills.sqlite3", namespace="data-programming"
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.library.close()

    def __call__(self, *, config, model, tool_registry, protocol, parser):
        verify = verification_tools(self.task)[0]

        @function_tool(read_only=True)
        def catalog_skills(query: str):
            """Search descriptions without loading executable bodies."""
            return (
                []
                if self.variant == "no-skills"
                else self.library.catalog(query, limit=8)
            )

        @function_tool(
            required_ops=["file"],
            permissions=ToolPermission(filesystem_write=True),
            concurrency_safe=False,
        )
        def load_skill(name: str, runtime_context: Optional[Dict[str, Any]] = None):
            """Load an exact verified skill version into the configured sandbox."""
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,48}", name):
                raise ValueError("invalid_skill_name")
            item = None if self.variant == "no-skills" else self.library.get(name)
            if (
                item is None
                or not item.active
                or item.metadata.get("verified") is not True
            ):
                raise ValueError("verified_skill_unavailable")
            target = "skill.py" if name == self.task["skill"] else name + ".py"
            (runtime_context or {})["ops"]["file"].atomic_write_text(
                target, item.source
            )
            return {
                "loaded": name,
                "version": item.version,
                "path": target,
                "source": item.source,
                "sha256": hashlib.sha256(item.source.encode()).hexdigest(),
                "provenance": item.metadata,
            }

        @function_tool(
            required_ops=["file", "process"],
            permissions=ToolPermission(filesystem_read=True, command=True),
            concurrency_safe=False,
        )
        def publish_skill(
            description: str, runtime_context: Optional[Dict[str, Any]] = None
        ):
            """Re-test exact source; publish only on a controller-owned passing receipt."""
            context = runtime_context or {}
            tested = verify.execute({}, context)
            if not tested.output.get("verified"):
                return tested
            source = context["ops"]["file"].read_text("skill.py")
            if (
                hashlib.sha256(source.encode()).hexdigest()
                != tested.output["source_digests"]["skill.py"]
            ):
                raise ValueError("skill_changed_after_validation")
            name = self.task["skill"]
            if self.variant == "no-skills":
                return ToolResult(
                    output={
                        "verified": True,
                        "published": None,
                        "persistence": "disabled",
                    },
                    tool_name="publish_skill",
                )
            item = self.library.add_or_update(
                ToolArtifact(
                    name,
                    description,
                    source,
                    metadata={
                        "verified": True,
                        "objective": self.task["id"],
                        "checks_digest": tested.output["checks_digest"],
                        "artifacts": [ref.to_dict() for ref in tested.artifact_refs],
                    },
                )
            )
            return ToolResult(
                output={"published": name, "version": item.version, "verified": True},
                tool_name="publish_skill",
                artifact_refs=tested.artifact_refs,
            )

        for tool in (verify, catalog_skills, load_skill, publish_skill):
            tool_registry.register(tool)
        return SkillAgent(
            llm=model,
            tool_registry=tool_registry,
            model_protocol=protocol.id,
            max_steps=config.max_steps,
            model_parser=parser,
        )


def build_factory(task, **resources):
    return SkillFactory(task, **resources)
