"""Run from an independent environment with all six project wheels installed."""

from contextlib import ExitStack
from dataclasses import replace
from importlib import import_module
from importlib.resources import files
import json
from copy import deepcopy
from pathlib import Path
import tempfile
from uuid import uuid4

from qitos.config import (
    EnvironmentConfig,
    SessionConfig,
    TrajectoryConfig,
    build_agent_composition,
    load_agent_config,
)


class Model:
    model = "deterministic-design-mechanism"
    qitos_protocol = "json_decision_multi_v1"

    def __init__(self, actions):
        self.actions = list(actions)
        self.requests = 0
        self.call_scope = uuid4().hex
        self.seen = []

    def call_raw(self, messages, **kwargs):
        self.requests += 1
        self.seen.append(deepcopy(messages))
        if not self.actions:
            return {
                "choices": [
                    {"message": {"content": "Final Answer: verified mechanism"}}
                ]
            }
        name, arguments = self.actions.pop(0)
        return {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": self.call_scope + "-" + str(self.requests),
                                "type": "function",
                                "function": {
                                    "name": name,
                                    "arguments": json.dumps(arguments),
                                },
                            }
                        ],
                    }
                }
            ]
        }


def check_project(package, config_path, root):
    module = import_module(package + ".agent")
    task = json.loads(files(package).joinpath("tasks.json").read_text())[0]
    config = load_agent_config(config_path)
    # No generated code or host commands are executed by this offline factory test.
    env = EnvironmentConfig(
        type="unsafe_host",
        image="",
        workspace=str(root),
        container_workspace="",
        network="host",
        read_only_root=False,
        cap_drop=False,
        no_new_privileges=False,
        pids_limit=None,
        memory_mb=None,
        cpus=None,
        cleanup_required=False,
    )
    config = replace(
        config,
        runtime=replace(
            config.runtime,
            environment=env,
            session=SessionConfig(store="sqlite", path=str(root / "sessions.sqlite3")),
            trajectory=TrajectoryConfig(output=str(root / "trajectory.journal")),
        ),
    )
    actions = []
    if package.endswith("planact"):
        actions = [
            ("revise_plan", {"steps": ["inspect", "verify"], "evidence": "initial"}),
            ("submit_report", {"report_json": "{}"}),
            (
                "revise_plan",
                {
                    "steps": ["recheck contradictory evidence"],
                    "evidence": "new observation",
                },
            ),
        ]
    if package.endswith("hermes"):
        actions = [
            (
                "remember_fact",
                {"identity": "protocol", "content": "weight=0.8", "source": "approved"},
            ),
            (
                "save_procedure",
                {
                    "name": "audit",
                    "description": "audit evidence",
                    "instructions": "complete body\n" * 150 + "LAST_CHECK",
                    "source": "approved",
                },
            ),
            ("catalog_skills", {"query": "audit"}),
            ("load_skill", {"name": "audit"}),
        ]
    model = Model(actions)
    with ExitStack() as stack:
        factory = module.build_factory(task, root=root)
        if hasattr(factory, "__enter__"):
            factory = stack.enter_context(factory)
        composition = stack.enter_context(
            build_agent_composition(config, model_override=model, agent_factory=factory)
        )
        result = composition.session("deterministic policy mechanism").run()
        assert result.state.final_result in {
            "verified mechanism",
            "Final Answer: verified mechanism",
        }, (package, result.state.stop_reason)
        assert composition.agent.llm is model
        assert composition.agent.tool_registry is composition.tool_registry
        assert model.requests == len(actions) + 1
        for record in result.records:
            assert all(item.status == "success" for item in record.action_results)
        if package.endswith("planact"):
            assert result.state.plan_version == 2
            assert result.state.plan == ["recheck contradictory evidence"]
        if package.endswith("hermes"):
            outputs = [
                item.output
                for record in result.records
                for item in record.action_results
                if item.tool_name
                in {"remember_fact", "save_procedure", "catalog_skills", "load_skill"}
            ]
            assert "LAST_CHECK" not in json.dumps(outputs[2])
            assert "instructions" in outputs[3], [
                (
                    type(item).__name__,
                    list(item) if isinstance(item, dict) else len(item),
                )
                for item in outputs
            ]
            assert outputs[3]["instructions"].endswith("LAST_CHECK")
        if package.endswith("pi"):
            assert set(composition.tool_registry.list_tools()) == {
                "read_file",
                "write_file",
                "edit_file",
                "run_command",
                "verify_project",
            }
    if package.endswith("hermes"):
        with module.build_factory(task, root=root) as reopened:
            assert reopened.memory.retrieve()[0].content.startswith("weight=0.8")
            assert reopened.skills.get("audit").source.endswith("LAST_CHECK")
    if package.endswith("planact"):
        static = Model(
            [
                ("revise_plan", {"steps": ["first"], "evidence": "initial"}),
                (
                    "revise_plan",
                    {"steps": ["second"], "evidence": "not allowed in static control"},
                ),
            ]
        )
        with build_agent_composition(
            config,
            model_override=static,
            agent_factory=module.build_factory(task, variant="static"),
        ) as current:
            control = current.session("retain the first plan").run()
            assert control.state.plan == ["first"] and control.state.plan_version == 1
            assert any(
                item.error_code == "static_plan_locked"
                for record in control.records
                for item in record.action_results
            )
    return {
        "package": package,
        "requests": model.requests,
        "status": "mechanism_passed",
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("configs", type=Path)
    args = parser.parse_args()
    results = []
    for directory, suffix in [
        ("react_research", "react"),
        ("planact_research", "planact"),
        ("pi_coding", "pi"),
        ("claude_coding", "claude"),
        ("hermes_notebook", "hermes"),
        ("voyager_skills", "voyager"),
    ]:
        with tempfile.TemporaryDirectory(prefix="qitos-lab-consumer-") as temporary:
            results.append(
                check_project(
                    "qitos_lab_" + suffix,
                    args.configs / directory / "agent.yaml",
                    Path(temporary),
                )
            )
    print(json.dumps(results))
