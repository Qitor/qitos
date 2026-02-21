"""Benchmark runner for Voyager template."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import List, Optional

from qitos import FSMEngine, TraceWriter
from qitos.skills.library import InMemorySkillLibrary
from templates.voyager.agent import VoyagerAgent


@dataclass
class Case:
    task: str
    expected: str


DATASET = [
    Case(task="compute 5 + 7", expected="12"),
    Case(task="compute 6 * 7", expected="42"),
    Case(task="compute 2 + 8", expected="10"),
    Case(task="compute 3 * 9", expected="27"),
]


def run_eval(trace_output_dir: Optional[str] = None) -> dict:
    lib = InMemorySkillLibrary()
    agent = VoyagerAgent(skill_library=lib)

    successes = 0
    step_counts: List[int] = []
    reuse_hits = 0

    for idx, case in enumerate(DATASET):
        writer = None
        if trace_output_dir is not None:
            writer = TraceWriter(
                output_dir=trace_output_dir,
                run_id=f"voyager-{idx}",
                metadata={
                    "model_id": "deterministic-template",
                    "prompt_hash": "template-voyager",
                    "tool_versions": {"math": "builtin"},
                    "seed": idx,
                    "run_config_hash": "voyager-baseline",
                },
            )

        engine = FSMEngine(agent=agent, trace_writer=writer)
        result = engine.run(case.task)
        pred = str(result.state.final_result)
        ok = pred == case.expected
        successes += int(ok)
        step_counts.append(len(result.records))
        if result.state.used_skills:
            reuse_hits += 1

    active_skills = lib.list_active()
    metrics = {
        "total": len(DATASET),
        "success": successes,
        "success_rate": successes / len(DATASET),
        "avg_steps": mean(step_counts) if step_counts else 0.0,
        "reuse_hits": reuse_hits,
        "reuse_rate": reuse_hits / len(DATASET),
        "active_skill_count": len(active_skills),
    }
    return metrics


def write_report(metrics: dict, path: str = "reports/voyager_baseline.md") -> None:
    lines = [
        "# Voyager Baseline Report",
        "",
        f"- Total: {metrics['total']}",
        f"- Success: {metrics['success']}",
        f"- Success Rate: {metrics['success_rate']:.2%}",
        f"- Average Steps: {metrics['avg_steps']:.2f}",
        f"- Skill Reuse Rate: {metrics['reuse_rate']:.2%}",
        f"- Active Skill Count: {metrics['active_skill_count']}",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    m = run_eval()
    write_report(m)
    print(m)
