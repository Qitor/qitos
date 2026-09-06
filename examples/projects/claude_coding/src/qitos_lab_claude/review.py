"""Use the framework's durable scheduler, Session fork and join, not a nested loop."""

import json
import time

from qitos.config import build_agent_composition
from qitos.core.work_graph import WorkGraph
from qitos.engine.runtime import LifecyclePolicy
from qitos.engine.work_runtime import (
    DurableWorkRuntime,
    LocalWorkScheduler,
    WorkRuntimePolicy,
)
from .agent import build_factory


class ReviewBoundary(LifecyclePolicy):
    policy_id = "lab.review_after_verified_edit"

    def __init__(self):
        self.enabled = True

    def should_pause(self, context):
        return self.enabled and context.state.verified


def wait_terminal(session, operation, timeout=1800):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        graph = WorkGraph.from_canonical_dict(session.inspect().work_graph)
        receipt = next(
            item
            for item in graph.operation_receipts
            if item.operation_id == operation.operation_id
        )
        if receipt.state in {"completed", "failed", "outcome_unknown"}:
            if receipt.state != "completed":
                raise RuntimeError("review_operation_not_completed")
            return receipt
        time.sleep(
            0.1
        )  # Live polling, not a deterministic race-test ordering primitive.
    raise TimeoutError("review_operation_deadline")


def independent_review(composition, session, task, resolver, *, model_factory=None):
    failures = []

    class ReviewResolver:
        resolver_id = "lab.independent_reviewer"

        def resolve(self, descriptor):
            stage = "construct"

            def execute():
                try:
                    return execute_review()
                except Exception as exc:
                    # Only a type name is diagnostic; provider/host messages stay private.
                    failures.append(stage + ":" + type(exc).__name__)
                    raise

            def execute_review():
                nonlocal stage
                if descriptor.operation == "join":
                    return {"joined": list(descriptor.child_session_ids)}
                reviews = []
                for identity in descriptor.child_session_ids:
                    with build_agent_composition(
                        composition.config,
                        credential_resolver=resolver,
                        model_override=model_factory() if model_factory else None,
                        agent_factory=build_factory(task, reviewer=True),
                    ) as child_composition:
                        stage = "restore"
                        child = child_composition.restore(identity)
                        stage = "run"
                        result = child.run()
                        stage = "validate-state"
                        if result.state.review is None or not result.state.verified:
                            failures.append(
                                json.dumps(
                                    {
                                        "review_present": result.state.review
                                        is not None,
                                        "verified": bool(result.state.verified),
                                        "steps": len(result.records),
                                        "reads": result.tool_calls_by_name.get(
                                            "read_file", 0
                                        ),
                                        "checks": result.tool_calls_by_name.get(
                                            "verify_project", 0
                                        ),
                                        "reviews": result.tool_calls_by_name.get(
                                            "submit_review", 0
                                        ),
                                        "check_succeeded": any(
                                            outcome.tool_name == "verify_project"
                                            and outcome.status == "success"
                                            for record in result.records
                                            for outcome in record.action_results
                                        ),
                                        "check_returncodes": [
                                            outcome.output.get("returncode")
                                            for record in result.records
                                            for outcome in record.action_results
                                            if outcome.tool_name == "verify_project"
                                            and isinstance(outcome.output, dict)
                                        ],
                                    }
                                )
                            )
                            raise RuntimeError("review_state_not_verified")
                        stage = "validate-final"
                        try:
                            returned = json.loads(result.state.final_result)
                        except (TypeError, ValueError):
                            raise RuntimeError("review_final_not_structured") from None
                        if returned != {"review": result.state.review}:
                            raise RuntimeError("review_final_state_mismatch")
                        stage = "validate-reads"
                        if result.tool_calls_by_name.get("read_file", 0) < len(
                            task["outputs"]
                        ):
                            raise RuntimeError("review_did_not_inspect_changed_files")
                        for record in result.records:
                            for outcome in record.action_results:
                                if (
                                    outcome.tool_name == "submit_review"
                                    and outcome.status == "success"
                                ):
                                    reviews.append(outcome.output["review"])
                if descriptor.operation != "join" and not reviews:
                    raise RuntimeError("review_missing")
                return {
                    "reviews": reviews,
                    "child_sessions": list(descriptor.child_session_ids),
                }

            return execute

    runtime = DurableWorkRuntime(
        LocalWorkScheduler(ReviewResolver(), max_workers=1),
        policy=WorkRuntimePolicy(timeout_seconds=1800),
    )
    composition.runtime.work_runtime = runtime
    ceiling = composition.config.budgets.max_requests if composition.config.budgets else None
    # Application allocation policy: reserve room for the parent's final response.
    # The framework still intersects this declaration with the remaining budget.
    review_requests = max(1, min(30, (ceiling or 90) // 3))
    try:
        operation = session.submit_work(
            "spawn",
            {
                "agent": composition.config.name,
                "task": "Independently review the changed source and its limitations.",
                "budget": {"model_requests": review_requests},
            },
            operation_id="independent-review",
        )
        try:
            receipt = wait_terminal(session, operation)
        except RuntimeError:
            raise RuntimeError(
                "review_operation_failed:" + ",".join(failures)
            ) from None
        join = session.join(
            [operation.operation_id], operation_id="independent-review-join"
        )
        wait_terminal(session, join)
        graph = WorkGraph.from_canonical_dict(session.inspect().work_graph)
        outcomes = []
        for completion in graph.completions:
            output = completion.outcome.get("output")
            if isinstance(output, dict) and isinstance(output.get("final_result"), str):
                try:
                    final = json.loads(output["final_result"])
                except ValueError:
                    continue
                if isinstance(final, dict) and isinstance(final.get("review"), dict):
                    outcomes.append(final)
        return {
            "operation_id": receipt.operation_id,
            "state": receipt.state,
            "child_sessions": list(operation.descriptor["child_session_ids"]),
            "outcomes": outcomes,
        }
    finally:
        runtime.close()
