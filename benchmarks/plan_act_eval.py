"""Benchmark runner for Plan-and-Act v2 template."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import List

from qitos import FSMEngine
from templates.plan_act.agent import PlanActAgent


@dataclass
class Case:
    task: str
    expected: str


DATASET = [
    Case(task="compute 2 + 3 then * 4", expected="20"),
    Case(task="compute 10 + 5 then * 2", expected="30"),
    Case(task="compute 11 + 10 then * 2", expected="42"),
]


def run_eval() -> dict:
    agent = PlanActAgent()

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


def write_report(metrics: dict, path: str = "reports/plan_act_baseline.md") -> None:
    lines = [
        "# Plan-and-Act Baseline Report",
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
