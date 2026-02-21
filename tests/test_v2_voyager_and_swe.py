from pathlib import Path

from benchmarks.swe_mini_eval import run_eval as run_swe_eval
from benchmarks.voyager_eval import run_eval as run_voyager_eval
from qitos import FSMEngine
from qitos.skills.library import InMemorySkillLibrary, SkillArtifact
from templates.swe_agent.agent import SWEAgentMini
from templates.voyager.agent import VoyagerAgent


def test_skill_library_versioning_and_retrieval():
    lib = InMemorySkillLibrary()
    v1 = lib.add_or_update(
        SkillArtifact(name="skill_add", description="v1", source="first", tags=["math"])
    )
    assert v1.version == 1

    v2 = lib.add_or_update(
        SkillArtifact(name="skill_add", description="v2", source="second", tags=["math"])
    )
    assert v2.version == 2

    hits = lib.search("add", top_k=3)
    assert len(hits) >= 1
    assert hits[0].name == "skill_add"


def test_voyager_template_reflection_and_skill_reuse():
    metrics = run_voyager_eval()
    assert metrics["success_rate"] == 1.0
    assert metrics["active_skill_count"] >= 2
    assert metrics["reuse_rate"] > 0.0


def test_swe_agent_mini_patch_loop(tmp_path: Path):
    buggy = tmp_path / "buggy_module.py"
    buggy.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    agent = SWEAgentMini(workspace_root=str(tmp_path))
    engine = FSMEngine(agent=agent)

    result = engine.run(
        "Fix buggy add function",
        file_path="buggy_module.py",
        expected_snippet="return a + b",
        test_command='python -c "import buggy_module; assert buggy_module.add(20, 22) == 42"',
    )

    assert result.state.final_result == "patch_valid:buggy_module.py"
    assert "return a + b" in buggy.read_text(encoding="utf-8")


def test_swe_benchmark_baseline():
    metrics = run_swe_eval()
    assert metrics["success_rate"] == 1.0
    assert metrics["avg_steps"] >= 3


def test_voyager_single_run_skill_written():
    lib = InMemorySkillLibrary()
    agent = VoyagerAgent(skill_library=lib)
    engine = FSMEngine(agent=agent)

    result = engine.run("compute 6 * 7")

    assert result.state.final_result == "42"
    assert lib.get("skill_multiply") is not None
