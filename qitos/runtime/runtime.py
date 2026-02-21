"""Canonical runtime orchestrator (policy + executor + criteria + trace)."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Dict, Generic, List, Optional, TypeVar

from qitos.core.action import Action
from qitos.core.critic import Critic
from qitos.core.decision import Decision
from qitos.core.errors import ErrorCategory, ParseExecutionError, RuntimeErrorInfo
from qitos.core.parser import Parser
from qitos.core.policy import BranchSelector, FirstCandidateSelector, Policy
from qitos.core.search import SearchAdapter
from qitos.engine.action_executor import ActionExecutor
from qitos.engine.recovery import RecoveryPolicy, build_failure_report
from qitos.engine.states import RuntimeBudget
from qitos.trace import TraceWriter
from qitos.trace.events import TraceEvent, TraceStep
from qitos.runtime.stop_criteria import FinalResultCriteria, MaxRuntimeCriteria, MaxStepsCriteria, StopCriteria


StateT = TypeVar("StateT")
ObsT = TypeVar("ObsT")
ActionT = TypeVar("ActionT")


@dataclass
class RuntimeResult(Generic[StateT]):
    state: StateT
    step_count: int
    events: List[TraceEvent]


class Runtime(Generic[StateT, ObsT, ActionT]):
    def __init__(
        self,
        policy: Policy[StateT, ObsT, ActionT],
        toolkit: Any,
        parser: Optional[Parser[ActionT]] = None,
        budget: Optional[RuntimeBudget] = None,
        stop_criteria: Optional[List[StopCriteria]] = None,
        recovery_policy: Optional[RecoveryPolicy] = None,
        branch_selector: Optional[BranchSelector[StateT, ObsT, ActionT]] = None,
        search_adapter: Optional[SearchAdapter[StateT, ObsT, ActionT]] = None,
        critics: Optional[List[Critic]] = None,
        trace_writer: Optional[TraceWriter] = None,
    ):
        self.policy = policy
        self.toolkit = toolkit
        self.parser = parser
        self.budget = budget or RuntimeBudget(max_steps=10)
        if stop_criteria is None:
            self.stop_criteria = [MaxStepsCriteria(self.budget.max_steps)]
            if self.budget.max_runtime_seconds is not None:
                self.stop_criteria.append(MaxRuntimeCriteria(self.budget.max_runtime_seconds))
            self.stop_criteria.append(FinalResultCriteria())
        else:
            self.stop_criteria = stop_criteria
        self.recovery_policy = recovery_policy or RecoveryPolicy()
        self.branch_selector = branch_selector or FirstCandidateSelector()
        self.search_adapter = search_adapter
        self.critics = critics or []
        self.trace_writer = trace_writer
        self.executor = ActionExecutor(tool_registry=toolkit)
        self.events: List[TraceEvent] = []

    def run(self, state: StateT) -> RuntimeResult[StateT]:
        step = 0
        started_at = time.monotonic()
        self.policy.prepare(state, context={"budget": self.budget})
        lifecycle_context = self._build_tool_context(state)
        self._setup_toolsets(lifecycle_context)

        try:
            while True:
                obs = self._build_observation(state, step)
                try:
                    raw_decision = self.policy.propose(state, obs)
                    decision = self._normalize_decision(raw_decision, step=step)
                    decision.validate()
                except Exception as exc:
                    recovery = self.recovery_policy.handle(state, "propose", step, exc)
                    if not recovery.continue_run:
                        if hasattr(state, "stop_reason"):
                            state.stop_reason = recovery.stop_reason
                        break
                    if hasattr(state, "current_step"):
                        state.current_step = step + 1
                    step += 1
                    continue

                if decision.mode == "branch":
                    if self.search_adapter is not None:
                        candidates = self.search_adapter.expand(state, obs, decision) or list(decision.candidates)
                        scores = self.search_adapter.score(state, obs, candidates)
                        candidates = self.search_adapter.prune(candidates, scores)
                        if not candidates:
                            state = self.search_adapter.backtrack(state)
                            if hasattr(state, "current_step"):
                                state.current_step = step + 1
                            step += 1
                            continue
                        # Re-score after prune so scores and candidates are aligned.
                        pruned_scores = self.search_adapter.score(state, obs, candidates)
                        decision = self.search_adapter.select(candidates, pruned_scores)
                    else:
                        decision = self.branch_selector.select(decision.candidates, state, obs)
                    decision.validate()

                action_results: List[Any] = []
                tool_invocations: List[Dict[str, Any]] = []
                if decision.mode == "act":
                    try:
                        actions = [
                            action if isinstance(action, Action) else Action.from_dict(action)  # type: ignore[arg-type]
                            for action in decision.actions
                        ]
                        execution = self.executor.execute(actions)
                        tool_invocations = [
                            {
                                "tool_name": item.name,
                                "toolset_name": item.metadata.get("toolset_name"),
                                "toolset_version": item.metadata.get("toolset_version"),
                                "source": item.metadata.get("source"),
                                "attempts": item.attempts,
                                "latency_ms": item.latency_ms,
                                "status": item.status.value,
                                "error_category": item.metadata.get("error_category"),
                                "error": item.error,
                            }
                            for item in execution
                        ]
                        action_results = [r.output if r.status.value == "success" else {"error": r.error} for r in execution]
                    except Exception as exc:
                        recovery = self.recovery_policy.handle(state, "act", step, exc)
                        if not recovery.continue_run:
                            if hasattr(state, "stop_reason"):
                                state.stop_reason = recovery.stop_reason
                            break
                        if hasattr(state, "current_step"):
                            state.current_step = step + 1
                        step += 1
                        continue

                if decision.mode == "final" and hasattr(state, "final_result"):
                    state.final_result = decision.final_answer

                try:
                    state = self.policy.update(state, obs, decision, action_results)
                except Exception as exc:
                    recovery = self.recovery_policy.handle(state, "update", step, exc)
                    if not recovery.continue_run:
                        if hasattr(state, "stop_reason"):
                            state.stop_reason = recovery.stop_reason
                        break

                critic_outputs = self._evaluate_critics(state, decision, action_results)
                critic_action = self._critic_action(critic_outputs)
                if critic_action == "stop":
                    if hasattr(state, "stop_reason"):
                        state.stop_reason = "critic_stop"
                    self._write_step_trace(
                        step,
                        obs,
                        decision,
                        action_results,
                        tool_invocations=tool_invocations,
                        critic_outputs=critic_outputs,
                    )
                    break
                if critic_action == "retry":
                    self._write_step_trace(
                        step,
                        obs,
                        decision,
                        action_results,
                        tool_invocations=tool_invocations,
                        critic_outputs=critic_outputs,
                    )
                    if hasattr(state, "current_step"):
                        state.current_step = step + 1
                    step += 1
                    continue

                self._write_step_trace(
                    step,
                    obs,
                    decision,
                    action_results,
                    tool_invocations=tool_invocations,
                    critic_outputs=critic_outputs,
                )

                elapsed = time.monotonic() - started_at
                should_stop, reason = self._should_stop(state, step, elapsed_seconds=elapsed)
                if should_stop:
                    if hasattr(state, "stop_reason") and getattr(state, "stop_reason", None) is None:
                        state.stop_reason = reason
                    break

                if hasattr(state, "current_step"):
                    state.current_step = step + 1
                step += 1
        finally:
            self.policy.finalize(state)
            teardown_context = self._build_tool_context(state)
            self._teardown_toolsets(teardown_context)

        if self.trace_writer is not None:
            stop_reason = getattr(state, "stop_reason", None)
            status = "failed" if stop_reason == "unrecoverable_error" else "completed"
            self.trace_writer.finalize(
                status=status,
                summary={
                    "stop_reason": stop_reason,
                    "final_result": getattr(state, "final_result", None),
                    "steps": step + 1,
                    "failure_report": build_failure_report(self.recovery_policy, stop_reason),
                },
            )

        return RuntimeResult(state=state, step_count=step + 1, events=self.events)

    def _build_observation(self, state: StateT, step: int) -> ObsT:
        runtime_view: Dict[str, Any] = {"step": step, "budget_max_steps": self.budget.max_steps}
        if hasattr(self.policy, "build_observation"):
            return self.policy.build_observation(state, runtime_view)  # type: ignore[return-value]
        return runtime_view  # type: ignore[return-value]

    def _normalize_decision(self, raw_decision: Any, step: int) -> Decision[ActionT]:
        if isinstance(raw_decision, Decision):
            return raw_decision

        if self.parser is not None:
            try:
                return self.parser.parse(raw_decision, context={"step": step})
            except Exception as exc:
                info = RuntimeErrorInfo(
                    category=ErrorCategory.PARSE,
                    message=str(exc),
                    phase="propose",
                    step_id=step,
                    recoverable=True,
                )
                raise ParseExecutionError(info) from exc

        raise ValueError("Policy.propose must return Decision when no parser is configured")

    def _should_stop(self, state: StateT, step: int, elapsed_seconds: float = 0.0) -> tuple[bool, Optional[str]]:
        return self._should_stop_with_runtime(state, step, elapsed_seconds=elapsed_seconds)

    def _should_stop_with_runtime(self, state: StateT, step: int, elapsed_seconds: float) -> tuple[bool, Optional[str]]:
        for criteria in self.stop_criteria:
            hit, reason = criteria.should_stop(
                state,
                step,
                runtime_info={
                    "elapsed_seconds": elapsed_seconds,
                    "budget_max_steps": self.budget.max_steps,
                    "budget_max_runtime_seconds": self.budget.max_runtime_seconds,
                    "budget_max_tokens": self.budget.max_tokens,
                },
            )
            if hit:
                return True, reason
        return False, None

    def _write_step_trace(
        self,
        step: int,
        obs: ObsT,
        decision: Decision[ActionT],
        action_results: List[Any],
        tool_invocations: Optional[List[Dict[str, Any]]] = None,
        critic_outputs: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        if self.trace_writer is None:
            return

        event = TraceEvent(run_id=self.trace_writer.run_id, step_id=step, phase="STEP", payload={"mode": decision.mode})
        self.events.append(event)
        self.trace_writer.write_event(event)

        step_payload = TraceStep(
            step_id=step,
            observation=obs,
            decision={
                "mode": decision.mode,
                "rationale": decision.rationale,
                "final_answer": decision.final_answer,
                "meta": decision.meta,
            },
            actions=decision.actions,
            action_results=action_results,
            tool_invocations=tool_invocations or [],
            critic_outputs=critic_outputs or [],
            state_diff={},
        )
        self.trace_writer.write_step(step_payload)

    def _evaluate_critics(
        self,
        state: StateT,
        decision: Decision[ActionT],
        action_results: List[Any],
    ) -> List[Dict[str, Any]]:
        outputs: List[Dict[str, Any]] = []
        for critic in self.critics:
            out = critic.evaluate(state, decision, action_results)
            outputs.append(out if isinstance(out, dict) else {"action": "continue", "reason": "invalid_critic_output"})
        return outputs

    def _critic_action(self, critic_outputs: List[Dict[str, Any]]) -> str:
        for output in critic_outputs:
            action = str(output.get("action", "continue"))
            if action == "stop":
                return "stop"
            if action == "retry":
                return "retry"
        return "continue"

    def _build_tool_context(self, state: StateT) -> Dict[str, Any]:
        return {
            "state": state,
            "trace_writer": self.trace_writer,
        }

    def _setup_toolsets(self, context: Dict[str, Any]) -> None:
        if not hasattr(self.toolkit, "setup"):
            return
        self._write_lifecycle_event("toolset_setup_start", context)
        try:
            self.toolkit.setup(context)
            self._write_lifecycle_event("toolset_setup_end", context)
        except Exception as exc:
            self._write_lifecycle_event("toolset_setup_error", context, ok=False, error=str(exc))

    def _teardown_toolsets(self, context: Dict[str, Any]) -> None:
        if not hasattr(self.toolkit, "teardown"):
            return
        self._write_lifecycle_event("toolset_teardown_start", context)
        try:
            self.toolkit.teardown(context)
            self._write_lifecycle_event("toolset_teardown_end", context)
        except Exception as exc:
            self._write_lifecycle_event("toolset_teardown_error", context, ok=False, error=str(exc))

    def _write_lifecycle_event(self, phase: str, context: Dict[str, Any], ok: bool = True, error: Optional[str] = None) -> None:
        if self.trace_writer is None:
            return
        event = TraceEvent(
            run_id=self.trace_writer.run_id,
            step_id=int(getattr(context.get("state"), "current_step", 0)),
            phase=phase,
            ok=ok,
            payload={
                "toolsets": getattr(self.toolkit, "list_toolsets", lambda: [])(),
                "error_category": "teardown_error" if "teardown_error" in phase else ("setup_error" if "setup_error" in phase else None),
            },
            error=error,
        )
        self.events.append(event)
        self.trace_writer.write_event(event)
