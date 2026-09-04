"""Generated configuration must execute through the real composition boundary."""
from dataclasses import replace
import runpy

from qitos.config import build_agent_composition, load_agent_config
from qitos.config.scaffold import create_agent_project
from test_s4_lane_a_public_authoring import _config


def test_generated_starter_failure_policy_is_executable(tmp_path):
    project = create_agent_project(tmp_path, agent_name="g5_starter", description="G5 fixture",
                                   author="G5", default_model="fake", max_steps=2)
    config = load_agent_config(project / "agent.yaml")
    config = replace(config, runtime=replace(config.runtime,
        data_root=str(tmp_path / "data"), environment=_config(tmp_path).runtime.environment,
        session=replace(config.runtime.session, path=str(tmp_path / "sessions.sqlite3")),
        trajectory=replace(config.runtime.trajectory, output=str(tmp_path / "trajectory.journal"))))
    model = runpy.run_path(str(project / "src/g5_starter/fake_provider.py"))["DeterministicFakeModel"]()
    with build_agent_composition(config, model_override=model) as composition:
        assert composition.engine.executor.policy.fail_fast is True
        assert composition.session("verify generated starter").run().state.final_result == "fake-ok"
