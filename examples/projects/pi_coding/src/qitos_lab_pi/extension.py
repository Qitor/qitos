"""Installable project extension. All generated-code execution stays in Env."""

import hashlib
import shlex
from typing import Optional, Dict, Any

from qitos.core.artifact import ArtifactRef
from qitos.core.function_tool_decorator import function_tool
from qitos.core.tool import ToolPermission
from qitos.core.tool_result import ToolResult


def verification_tools(task):
    @function_tool(
        required_ops=["file", "process"],
        permissions=ToolPermission(filesystem_read=True, command=True),
        concurrency_safe=False,
    )
    def verify_project(runtime_context: Optional[Dict[str, Any]] = None):
        """Run controller-owned checks, capture exact tested source artifacts."""
        context = runtime_context or {}
        fs, process = context["ops"]["file"], context["ops"]["process"]
        bodies = {path: fs.read_text(path).encode() for path in task["outputs"]}
        outcome = dict(
            process.run("python -c " + shlex.quote(task["checks"]), timeout=30)
        )
        unchanged = all(
            fs.read_text(path).encode() == body for path, body in bodies.items()
        )
        passed = (
            outcome.get("returncode") == 0
            and not outcome.get("outcome_unknown")
            and unchanged
        )
        refs = []
        for path, body in bodies.items():
            digest = hashlib.sha256(body).hexdigest()
            ref = ArtifactRef(
                artifact_id="sha256:" + digest,
                resolver_key="tool-result-output",
                sha256=digest,
                byte_length=len(body),
                media_type="text/x-python",
            )
            context["artifact_resolver"].put(ref, body)
            refs.append(ref)
        report = {
            "verified": passed,
            "source_digests": {
                path: hashlib.sha256(body).hexdigest() for path, body in bodies.items()
            },
            "checks_digest": hashlib.sha256(task["checks"].encode()).hexdigest(),
            "returncode": outcome.get("returncode"),
            "source_unchanged": unchanged,
            "feedback": str(outcome.get("stderr", ""))[-3000:],
        }
        return ToolResult(
            output=report,
            model_output=report,
            artifact_refs=tuple(refs),
            tool_name="verify_project",
        )

    return (verify_project,)


def statistics_tools():
    """Optional pure-data extension reused by the PlanAct composition lesson."""

    @function_tool(read_only=True, concurrency_safe=True)
    def weighted_summary(values: list[float], weights: list[int]):
        """Calculate a weighted mean with explicit dimension/weight validation."""
        if (
            not values
            or len(values) != len(weights)
            or any(weight < 0 for weight in weights)
        ):
            raise ValueError("invalid_weighted_series")
        total = sum(weights)
        if total <= 0:
            raise ValueError("empty_weighted_series")
        return {
            "mean": sum(value * weight for value, weight in zip(values, weights))
            / total,
            "total_weight": total,
        }

    return (weighted_summary,)
