"""Benchmark runner for SWE-Agent mini template."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import List, Optional

from qitos import FSMEngine, TraceWriter
from templates.swe_agent.agent import SWEAgentMini


@dataclass
class Case:
    buggy_code: str
    expected_snippet: str


DATASET = [
    Case(
        buggy_code="def add(a, b):\n    return a - b\n",
        expected_snippet="return a + b",
    ),
    Case(
        buggy_code="def add(a, b):\n    return a - b\n",
        expected_snippet="return a + b",
    ),
]


def run_eval(trace_output_dir: Optional[str] = None) -> dict:
    successes = 0
    step_counts: List[int] = []

    for idx, case in enumerate(DATASET):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "buggy_module.py").write_text(case.buggy_code, encoding="utf-8")

            writer = None
            if trace_output_dir is not None:
                writer = TraceWriter(
                    output_dir=trace_output_dir,
                    run_id=f"swe-mini-{idx}",
                    metadata={
                        "model_id": "deterministic-template",
                        "prompt_hash": "template-swe-mini",
                        "tool_versions": {"editor": "builtin", "shell": "builtin"},
                        "seed": idx,
                        "run_config_hash": "swe-mini-baseline",
                    },
                )

            agent = SWEAgentMini(workspace_root=str(root))
            engine = FSMEngine(agent=agent, trace_writer=writer)
            result = engine.run(
                "Fix buggy add function",
                file_path="buggy_module.py",
                expected_snippet=case.expected_snippet,
                test_command='python -c "import buggy_module; assert buggy_module.add(20, 22) == 42"',
            )

            final = str(result.state.final_result)
            ok = final == "patch_valid:buggy_module.py"
            successes += int(ok)
            step_counts.append(len(result.records))

    return {
        "total": len(DATASET),
        "success": successes,
        "success_rate": successes / len(DATASET),
        "avg_steps": mean(step_counts) if step_counts else 0.0,
    }


def write_report(metrics: dict, path: str = "reports/swe_agent_baseline.md") -> None:
    lines = [
        "# SWE-Agent Mini Baseline Report",
        "",
        f"- Total: {metrics['total']}",
        f"- Success: {metrics['success']}",
        f"- Success Rate: {metrics['success_rate']:.2%}",
        f"- Average Steps: {metrics['avg_steps']:.2f}",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    m = run_eval()
    write_report(m)
    print(m)
