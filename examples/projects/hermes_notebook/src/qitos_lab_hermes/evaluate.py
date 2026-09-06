"""Controller-side evaluator, never staged into the agent's workspace."""

import math


def evaluate(result, task):
    submitted = []
    read_sources = set()
    for record in result.records:
        for item in record.action_results:
            output = item.output
            if (
                item.tool_name == "read_file"
                and item.status == "success"
                and isinstance(output, dict)
            ):
                if isinstance(output.get("path"), str):
                    read_sources.add(output["path"])
            if (
                item.tool_name == "submit_report"
                and item.status == "success"
                and isinstance(output, dict)
            ):
                if "submitted_report" in output:
                    submitted.append(output["submitted_report"])
    report = submitted[-1] if submitted and isinstance(submitted[-1], dict) else {}
    citations = report.get("citations", [])
    valid_citations = isinstance(citations, list) and all(
        isinstance(item, str) for item in citations
    )
    limitations = report.get("limitations", [])
    checks = {
        "report_submitted": bool(submitted),
        "conclusion": isinstance(report.get("conclusion"), str)
        and bool(report.get("conclusion")),
        "limitations": isinstance(limitations, list)
        and bool(limitations)
        and all(isinstance(item, str) and item.strip() for item in limitations),
        "citations": valid_citations
        and set(task["required_sources"]) <= set(citations),
        "actual_reads": (set(task["required_sources"]) - {"protocol.md"})
        <= read_sources,
        "final": str(result.state.stop_reason) == "final",
    }
    metrics = report.get("metrics", {})
    for key, expected in task["expected_metrics"].items():
        value = metrics.get(key) if isinstance(metrics, dict) else None
        checks[key] = type(value) in (int, float) and math.isclose(
            value, expected, rel_tol=0.005, abs_tol=0.005
        )
    return {"passed": all(checks.values()), "checks": checks, "submitted": report}
