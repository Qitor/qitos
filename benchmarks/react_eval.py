"""Benchmark runner for ReAct v2 template."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import List

from qitos import FSMEngine
from templates.react.agent import ReActAgent


@dataclass
class Case:
    task: str
    expected: str


DATASET = [
    Case(task="compute 2 + 3", expected="5"),
    Case(task="compute 7 * 8", expected="56"),
    Case(task="compute 21 + 21", expected="42"),
]


def run_eval() -> dict:
    agent = ReActAgent()

    successes = 0
    step_counts: List[int] = []
    rows = []

    for case in DATASET:
        engine = FSMEngine(agent=agent)
        result = engine.run(case.task)
        pred = str(result.state.final_result)
        ok = pred == case.expected
        successes += int(ok)
        step_counts.append(len(result.records))
        rows.append((case.task, case.expected, pred, ok, len(result.records)))

    metrics = {
        "total": len(DATASET),
        "success": successes,
        "success_rate": successes / len(DATASET),
        "avg_steps": mean(step_counts) if step_counts else 0.0,
        "rows": rows,
    }
    return metrics


def write_report(metrics: dict, path: str = "reports/react_baseline.md") -> None:
    lines = [
        "# ReAct Baseline Report",
        "",
        f"- Total: {metrics['total']}",
        f"- Success: {metrics['success']}",
        f"- Success Rate: {metrics['success_rate']:.2%}",
        f"- Average Steps: {metrics['avg_steps']:.2f}",
        "",
        "## Cases",
        "",
        "| Task | Expected | Predicted | OK | Steps |",
        "|---|---:|---:|:---:|---:|",
    ]

    for task, expected, pred, ok, steps in metrics["rows"]:
        lines.append(f"| {task} | {expected} | {pred} | {'Y' if ok else 'N'} | {steps} |")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    m = run_eval()
    write_report(m)
    print(m)
