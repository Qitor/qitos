"""Read successful controller-owned verification, not the model's final claim."""


def evaluate(result, task, *, prior_records=()):
    verified_step = -1
    edited_step = -1
    source_digests = {}
    for record in [*prior_records, *result.records]:
        for item in record.action_results:
            if item.tool_name in {"write_file", "edit_file", "run_command"}:
                edited_step = record.step_id
            if item.tool_name == "verify_project" and item.status == "success":
                output = item.output
                if isinstance(output, dict) and output.get("verified") is True:
                    verified_step = record.step_id
                    source_digests = output.get("source_digests", {})
                else:
                    verified_step = -1
    checks = {
        "independent_checks": verified_step >= 0,
        "no_edits_after_verification": verified_step >= edited_step,
        "all_outputs_captured": set(task["outputs"]) == set(source_digests),
        "read_before_edit": result.tool_calls_by_name.get("read_file", 0) > 0,
        "final": str(result.state.stop_reason) == "final",
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "source_digests": source_digests,
    }
