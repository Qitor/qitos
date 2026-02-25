"""Canonical Engine for AgentModule execution."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar
from uuid import uuid4

from ..core.action import Action
from ..core.agent_module import AgentModule
from ..core.decision import Decision
from ..core.errors import ErrorCategory, ParseExecutionError, RuntimeErrorInfo, StopReason
from ..core.env import Env, EnvObservation, EnvStepResult
from ..core.memory import Memory, MemoryRecord
from ..core.state import StateSchema
from ..core.task import Task, TaskCriterionResult, TaskResult, TaskValidationIssue
from ..trace import TraceWriter, runtime_event_to_trace, runtime_step_to_trace
from .action_executor import ActionExecutor
from .branching import BranchSelector, FirstCandidateSelector
from .critic import Critic
from .hooks import EngineHook, HookContext
from .parser import Parser
from .recovery import RecoveryPolicy, build_failure_report
from .search import Search
from .states import RuntimeBudget, RuntimeEvent, RuntimePhase, StepRecord
from .stop_criteria import FinalResultCriteria, StopCriteria
from .validation import StateValidationGate


StateT = TypeVar("StateT", bound=StateSchema)
ObservationT = TypeVar("ObservationT")
ActionT = TypeVar("ActionT")

RecoveryHandler = Callable[[StateT, RuntimePhase, Exception], None]


@dataclass
class EngineResult(Generic[StateT]):
    state: StateT
    records: List[StepRecord]
    events: List[RuntimeEvent]
    step_count: int
    task_result: Optional[TaskResult] = None


class Engine(Generic[StateT, ObservationT, ActionT]):
    """Single execution kernel for all AgentModule workflows."""

    def __init__(
        self,
        agent: AgentModule[StateT, ObservationT, ActionT],
        budget: Optional[RuntimeBudget] = None,
        validation_gate: Optional[StateValidationGate] = None,
        recovery_handler: Optional[RecoveryHandler] = None,
        recovery_policy: Optional[RecoveryPolicy] = None,
        trace_writer: Optional[TraceWriter] = None,
        memory: Optional[Memory] = None,
        parser: Optional[Parser[ActionT]] = None,
        stop_criteria: Optional[List[StopCriteria]] = None,
        branch_selector: Optional[BranchSelector[StateT, ObservationT, ActionT]] = None,
        search: Optional[Search[StateT, ObservationT, ActionT]] = None,
        critics: Optional[List[Critic]] = None,
        env: Optional[Env] = None,
        hooks: Optional[List[EngineHook]] = None,
        render_hooks: Optional[List[Any]] = None,
    ):
        self.agent = agent
        self.tool_registry = agent.tool_registry
        self.budget = budget or RuntimeBudget(max_steps=10)
        self._base_budget = RuntimeBudget(
            max_steps=self.budget.max_steps,
            max_runtime_seconds=self.budget.max_runtime_seconds,
            max_tokens=self.budget.max_tokens,
        )
        self.validation_gate = validation_gate or StateValidationGate()
        self.recovery_handler = recovery_handler
        self.recovery_policy = recovery_policy or RecoveryPolicy()
        self.trace_writer = trace_writer
        if memory is not None:
            self.agent.memory = memory
        self.parser = parser
        self.branch_selector = branch_selector or FirstCandidateSelector()
        self.search = search
        self.critics = critics or []
        self.env = env
        self.hooks: List[Any] = list(hooks or [])
        if render_hooks:
            self.hooks.extend(render_hooks)
        if stop_criteria is None:
            self._uses_default_stop_criteria = True
            self.stop_criteria = [FinalResultCriteria()]
        else:
            self._uses_default_stop_criteria = False
            self.stop_criteria = stop_criteria

        self.executor = ActionExecutor(tool_registry=self.tool_registry) if self.tool_registry is not None else None
        self.events: List[RuntimeEvent] = []
        self.records: List[StepRecord] = []
        self._active_state: Optional[StateT] = None
        self._active_task: str = ""
        self._active_task_obj: Optional[Task] = None
        self._last_env_observation: Optional[EnvObservation] = None
        self._last_env_result: Optional[EnvStepResult] = None
        self._token_usage: int = 0
        self._active_run_id: str = ""

    def register_hook(self, hook: Any) -> None:
        """Register one runtime hook instance."""
        self.hooks.append(hook)

    def unregister_hook(self, hook: Any) -> None:
        """Unregister one runtime hook instance if present."""
        self.hooks = [h for h in self.hooks if h is not hook]

    def clear_hooks(self) -> None:
        """Remove all runtime hooks."""
        self.hooks = []

    def run(self, task: str | Task, **kwargs: Any) -> EngineResult[StateT]:
        self.events = []
        self.records = []
        self._last_env_observation = None
        self._last_env_result = None
        memory = self._memory()
        if memory is not None:
            try:
                memory.reset()
            except Exception:
                pass
        if hasattr(self.recovery_policy, "reset"):
            try:
                self.recovery_policy.reset()
            except Exception:
                pass
        self._active_run_id = (
            str(getattr(self.trace_writer, "run_id", "")).strip() if self.trace_writer is not None else ""
        ) or f"run_{uuid4().hex[:12]}"
        task_obj, task_text = self._normalize_task(task)
        self._apply_task_budget(task_obj)
        self._token_usage = 0
        state = self.agent.init_state(task_text, **kwargs)
        self._active_task = task_text
        self._active_task_obj = task_obj
        self._active_state = state
        started_at = time.monotonic()
        self._hydrate_trace_metadata(task_obj=task_obj, task_text=task_text)

        self._setup_toolsets({"state": state, "trace_writer": self.trace_writer, "task": task_obj or task_text})
        self._setup_env(task_obj=task_obj, state=state, kwargs=kwargs)
        self._emit(
            0,
            RuntimePhase.INIT,
            payload={
                "task": task_text,
                "task_id": task_obj.id if task_obj is not None else None,
                "task_meta": self._task_meta(task_obj),
                "run_meta": self._run_meta(),
                "env": self._env_identity(),
            },
        )
        self._notify_run_start(task_text, state)
        preflight_issues = self._preflight_validate(task_obj=task_obj, workspace=kwargs.get("workspace"))
        if preflight_issues:
            has_task_issue = any(not issue.code.startswith("ENV_") for issue in preflight_issues)
            stop_reason = StopReason.TASK_VALIDATION_FAILED if has_task_issue else StopReason.ENV_CAPABILITY_MISMATCH
            state.set_stop(stop_reason)
            state.final_result = "Preflight validation failed."
            self._emit(
                0,
                RuntimePhase.END,
                ok=False,
                payload={
                    "stop_reason": state.stop_reason,
                    "error_category": ErrorCategory.TASK.value if has_task_issue else ErrorCategory.ENV.value,
                    "issues": [self._task_issue_to_dict(x) for x in preflight_issues],
                },
            )
            result = EngineResult(
                state=state,
                records=self.records,
                events=self.events,
                step_count=0,
                task_result=self._build_task_result(state, task_obj=task_obj, started_at=started_at),
            )
            self._notify_run_end(result)
            self._active_state = None
            self._active_task = ""
            self._active_task_obj = None
            self._last_env_observation = None
            self._last_env_result = None
            self._teardown_env()
            self._teardown_toolsets({"state": state, "trace_writer": self.trace_writer, "task": task_obj or task_text})
            return result

        step_id = 0
        current_observation = self._build_initial_observation(state, step_id, started_at)
        try:
            while True:
                if self._budget_exhausted(step_id, started_at, state):
                    self._emit(step_id, RuntimePhase.END, ok=False, payload={"stop_reason": state.stop_reason})
                    break

                self.validation_gate.before_phase(state, RuntimePhase.DECIDE.value)

                record = StepRecord(step_id=step_id)
                self.records.append(record)

                self._dispatch_hook(
                    "on_before_step",
                    HookContext(
                        task=task_text,
                        step_id=step_id,
                        phase=RuntimePhase.DECIDE,
                        state=state,
                        observation=current_observation,
                        record=record,
                    ),
                )
                try:
                    decision = self._run_decide(state, current_observation, record)
                    action_results = self._run_act(state, decision, record)
                    observation = self._build_observation_after_action(
                        state=state,
                        step_id=step_id,
                        started_at=started_at,
                        decision=decision,
                        action_results=action_results,
                    )
                    record.observation = observation
                    self._memory_append("observation", observation, record.step_id)
                    self._run_reduce(state, observation, decision, record)
                except Exception as exc:
                    failed_phase = self._infer_failed_phase(record)
                    if not self._recover(state, failed_phase, exc):
                        self._finalize_step(record, state)
                        self._emit(step_id, RuntimePhase.END, ok=False, payload={"stop_reason": state.stop_reason})
                        break
                    self._finalize_step(record, state)
                    self._dispatch_hook(
                        "on_after_step",
                        HookContext(
                            task=task_text,
                            step_id=step_id,
                            phase=RuntimePhase.RECOVER,
                            state=state,
                            record=record,
                            stop_reason=state.stop_reason,
                        ),
                    )
                    current_observation = self._build_initial_observation(state, step_id + 1, started_at)
                    state.advance_step()
                    step_id += 1
                    continue

                critic_action = self._apply_critics(state, record)
                if critic_action == "stop":
                    state.set_stop(StopReason.CRITIC_STOP)
                    self._finalize_step(record, state)
                    self._dispatch_hook(
                        "on_after_step",
                        HookContext(
                            task=task_text,
                            step_id=step_id,
                            phase=RuntimePhase.CRITIC,
                            state=state,
                            record=record,
                            stop_reason=state.stop_reason,
                        ),
                    )
                    self._emit(step_id, RuntimePhase.END, payload={"stop_reason": state.stop_reason})
                    break
                if critic_action == "retry":
                    self._finalize_step(record, state)
                    self._dispatch_hook(
                        "on_after_step",
                        HookContext(
                            task=task_text,
                            step_id=step_id,
                            phase=RuntimePhase.CRITIC,
                            state=state,
                            record=record,
                        ),
                    )
                    current_observation = observation
                    state.advance_step()
                    step_id += 1
                    continue

                stop = self._run_check_stop(state, record.decision, step_id, started_at)

                self.validation_gate.after_phase(state, RuntimePhase.CHECK_STOP.value)
                self._finalize_step(record, state)
                self._dispatch_hook(
                    "on_after_step",
                    HookContext(
                        task=task_text,
                        step_id=step_id,
                        phase=RuntimePhase.CHECK_STOP,
                        state=state,
                        record=record,
                        stop_reason=state.stop_reason,
                    ),
                )

                if stop:
                    self._emit(step_id, RuntimePhase.END, payload={"stop_reason": state.stop_reason})
                    break

                current_observation = observation
                state.advance_step()
                step_id += 1
        finally:
            self._teardown_env()
            self._teardown_toolsets({"state": state, "trace_writer": self.trace_writer, "task": task_obj or task_text})

        if self.trace_writer is not None:
            status = "failed" if state.stop_reason == StopReason.UNRECOVERABLE_ERROR.value else "completed"
            self.trace_writer.finalize(
                status=status,
                summary={
                    "stop_reason": state.stop_reason,
                    "final_result": state.final_result,
                    "steps": len(self.records),
                    "token_usage": self._token_usage,
                    "task_meta": self._task_meta(task_obj),
                    "task_result": self._build_task_result(state, task_obj=task_obj, started_at=started_at).to_dict(),
                    "run_meta": self._run_meta(),
                    "failure_report": build_failure_report(self.recovery_policy, state.stop_reason),
                },
            )

        result = EngineResult(
            state=state,
            records=self.records,
            events=self.events,
            step_count=len(self.records),
            task_result=self._build_task_result(state, task_obj=task_obj, started_at=started_at),
        )
        self._notify_run_end(result)
        self._active_state = None
        self._active_task = ""
        self._active_task_obj = None
        self._last_env_observation = None
        self._last_env_result = None
        self._active_run_id = ""
        return result

    def _apply_task_budget(self, task_obj: Optional[Task]) -> None:
        self.budget.max_steps = self._base_budget.max_steps
        self.budget.max_runtime_seconds = self._base_budget.max_runtime_seconds
        self.budget.max_tokens = self._base_budget.max_tokens
        if task_obj is None:
            if self._uses_default_stop_criteria:
                self.stop_criteria = [FinalResultCriteria()]
            return
        budget = task_obj.budget
        if budget.max_steps is not None:
            self.budget.max_steps = int(budget.max_steps)
        if budget.max_runtime_seconds is not None:
            self.budget.max_runtime_seconds = float(budget.max_runtime_seconds)
        if budget.max_tokens is not None:
            self.budget.max_tokens = int(budget.max_tokens)
        if self._uses_default_stop_criteria:
            self.stop_criteria = [FinalResultCriteria()]

    def _build_env_view(self, state: StateT, step_id: int, started_at: float) -> Dict[str, Any]:
        elapsed = time.monotonic() - started_at
        env_payload = self._env_payload()
        return {
            "step_id": step_id,
            "elapsed_seconds": elapsed,
            "budget": {
                "max_steps": self.budget.max_steps,
                "max_runtime_seconds": self.budget.max_runtime_seconds,
                "max_tokens": self.budget.max_tokens,
                "consumed_tokens": self._token_usage,
            },
            "metadata": state.metadata,
            "env": env_payload,
            "task": self._active_task_obj.to_dict() if self._active_task_obj is not None else {"objective": self._active_task},
        }

    def _build_initial_observation(self, state: StateT, step_id: int, started_at: float) -> ObservationT:
        env_view = self._build_env_view(state, step_id, started_at)
        obs = {
            "task": self._active_task,
            "step": step_id,
            "state": state.to_dict(),
            "env": env_view.get("env", {}),
            "action_results": [],
        }
        return obs  # type: ignore[return-value]

    def _build_observation_after_action(
        self,
        state: StateT,
        step_id: int,
        started_at: float,
        decision: Decision[ActionT],
        action_results: List[Any],
    ) -> ObservationT:
        env_view = self._build_env_view(state, step_id, started_at)
        obs = {
            "task": self._active_task,
            "step": step_id,
            "state": state.to_dict(),
            "decision": decision.to_dict() if hasattr(decision, "to_dict") else decision,
            "action_results": list(action_results),
            "env": env_view.get("env", {}),
        }
        self._emit(
            step_id,
            RuntimePhase.ACT,
            payload={
                "stage": "observation_ready",
                "observation": obs,
            },
        )
        return obs  # type: ignore[return-value]

    def _run_decide(self, state: StateT, observation: ObservationT, record: StepRecord) -> Decision[ActionT]:
        self._dispatch_hook(
            "on_before_decide",
            HookContext(
                task=self._active_task,
                step_id=record.step_id,
                phase=RuntimePhase.DECIDE,
                state=state,
                observation=observation,
                record=record,
            ),
        )
        self._emit(
            record.step_id,
            RuntimePhase.DECIDE,
            payload={"stage": "state_ready", "observation": observation},
        )
        self._emit(record.step_id, RuntimePhase.DECIDE, payload={"stage": "start"})
        raw_decision = self.agent.decide(state, observation)
        if raw_decision is None:
            if self.agent.llm is None:
                raise ValueError("No llm configured and Agent.decide returned None")
            prepared = self.agent.prepare(state)
            system_prompt = self.agent.build_system_prompt(state)
            messages: List[Dict[str, str]] = []
            if isinstance(system_prompt, str) and system_prompt.strip():
                messages.append({"role": "system", "content": system_prompt})
            history: List[Dict[str, str]] = []
            memory = self._memory()
            if memory is not None:
                runtime_view = {
                    "step_id": record.step_id,
                    "elapsed_seconds": 0.0,
                    "metadata": state.metadata,
                    "env": self._env_payload(),
                    "task": self._active_task_obj.to_dict() if self._active_task_obj is not None else {"objective": self._active_task},
                }
                try:
                    query = self.agent.build_memory_query(state, runtime_view) or {}
                except Exception:
                    query = {}
                try:
                    retrieved = memory.retrieve_messages(
                        state=state,
                        observation=observation,
                        query=query if isinstance(query, dict) else {},
                    )
                    if isinstance(retrieved, list):
                        for item in retrieved:
                            if not isinstance(item, dict):
                                continue
                            role = str(item.get("role", "")).strip()
                            content = str(item.get("content", ""))
                            if role and content:
                                history.append({"role": role, "content": content})
                except Exception:
                    history = []
            current_user = {"role": "user", "content": str(prepared)}
            messages.extend(history)
            messages.append(current_user)
            self._emit(
                record.step_id,
                RuntimePhase.DECIDE,
                payload={
                    "stage": "model_input",
                    "prepared": str(prepared),
                    "history_message_count": len(history),
                    "messages": messages,
                },
            )
            self._memory_append("message", current_user, record.step_id, metadata={"source": "engine"})
            self._memory_append("model_input", {"messages": messages}, record.step_id)
            raw_decision = self.agent.llm(messages)
            self._token_usage += self._estimate_tokens(messages) + self._estimate_tokens(str(raw_decision))
            self._emit(
                record.step_id,
                RuntimePhase.DECIDE,
                payload={"stage": "model_output", "raw_output": str(raw_decision)},
            )
            self._memory_append(
                "message",
                {"role": "assistant", "content": str(raw_decision)},
                record.step_id,
                metadata={"source": "engine"},
            )
            self._memory_append("model_output", raw_decision, record.step_id)
        decision = self._normalize_decision(raw_decision, step=record.step_id)

        if decision.mode == "branch":
            decision = self._select_branch(state, observation, decision)

        if decision.mode not in {"act", "final", "wait"}:
            raise ValueError(f"Invalid decision mode: {decision.mode}")

        decision.validate()
        record.decision = decision
        record.actions = list(decision.actions)
        self._memory_append("decision", decision, record.step_id)
        self._emit(
            record.step_id,
            RuntimePhase.DECIDE,
            payload={
                "stage": "decision_ready",
                "mode": decision.mode,
                "rationale": decision.rationale,
                "actions": decision.actions,
                "final_answer": decision.final_answer,
                "candidate_count": len(decision.candidates),
            },
        )
        self._dispatch_hook(
            "on_after_decide",
            HookContext(
                task=self._active_task,
                step_id=record.step_id,
                phase=RuntimePhase.DECIDE,
                state=state,
                observation=observation,
                decision=decision,
                record=record,
            ),
        )
        return decision

    def _select_branch(
        self,
        state: StateT,
        observation: ObservationT,
        branch_decision: Decision[ActionT],
    ) -> Decision[ActionT]:
        if self.search is not None:
            candidates = self.search.expand(state, observation, branch_decision) or list(branch_decision.candidates)
            scores = self.search.score(state, observation, candidates)
            candidates = self.search.prune(candidates, scores)
            if not candidates:
                new_state = self.search.backtrack(state)
                if new_state is not state:
                    state.__dict__.update(new_state.__dict__)
                return Decision.wait(rationale="search backtrack")
            scores = self.search.score(state, observation, candidates)
            selected = self.search.select(candidates, scores)
            mark_selected = getattr(self.search, "mark_selected", None)
            if callable(mark_selected):
                mark_selected(state, selected)
        else:
            selected = self.branch_selector.select(branch_decision.candidates, state, observation)
        selected.validate()
        return selected

    def _run_act(self, state: StateT, decision: Decision[ActionT], record: StepRecord) -> List[Any]:
        self._dispatch_hook(
            "on_before_act",
            HookContext(
                task=self._active_task,
                step_id=record.step_id,
                phase=RuntimePhase.ACT,
                state=state,
                decision=decision,
                record=record,
            ),
        )
        self._emit(record.step_id, RuntimePhase.ACT, payload={"stage": "start"})

        if decision.mode != "act":
            self._emit(record.step_id, RuntimePhase.ACT, payload={"stage": "skipped", "reason": "decision_not_act"})
            return []
        if self.executor is None:
            raise RuntimeError("No tool registry configured for action execution")
        actions = [action if isinstance(action, Action) else Action.from_dict(action) for action in decision.actions]
        execution = self.executor.execute(actions, env=self.env, state=state)

        record.tool_invocations = [
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
        results = [r.output if r.status.value == "success" else {"error": r.error} for r in execution]
        if self.env is not None:
            env_result = self._run_env_step(decision=decision, action_results=results)
            if env_result is not None:
                results.append({"env": self._env_step_result_to_dict(env_result)})
        record.action_results = results
        for item in results:
            self._memory_append("action_result", item, record.step_id)
        self._emit(
            record.step_id,
            RuntimePhase.ACT,
            payload={
                "stage": "action_results",
                "tool_invocations": record.tool_invocations,
                "action_results": results,
            },
        )
        self._dispatch_hook(
            "on_after_act",
            HookContext(
                task=self._active_task,
                step_id=record.step_id,
                phase=RuntimePhase.ACT,
                state=state,
                decision=decision,
                action_results=results,
                record=record,
            ),
        )
        return results

    def _run_reduce(
        self,
        state: StateT,
        observation: ObservationT,
        decision: Decision[ActionT],
        record: StepRecord,
    ) -> None:
        self._dispatch_hook(
            "on_before_reduce",
            HookContext(
                task=self._active_task,
                step_id=record.step_id,
                phase=RuntimePhase.REDUCE,
                state=state,
                observation=observation,
                decision=decision,
                action_results=(record.action_results if record is not None else []),
                record=record,
            ),
        )
        self._emit(record.step_id, RuntimePhase.REDUCE, payload={"stage": "start"})
        before = state.to_dict()
        new_state = self.agent.reduce(state, observation, decision)
        if new_state is not state:
            state.__dict__.update(new_state.__dict__)
        after = state.to_dict()
        record.state_diff = self._compute_state_diff(before, after)
        self._emit(
            record.step_id,
            RuntimePhase.REDUCE,
            payload={"stage": "state_reduced", "state_diff": record.state_diff},
        )
        self._dispatch_hook(
            "on_after_reduce",
            HookContext(
                task=self._active_task,
                step_id=record.step_id,
                phase=RuntimePhase.REDUCE,
                state=state,
                observation=observation,
                decision=decision,
                action_results=(record.action_results if record is not None else []),
                record=record,
                payload={"state_diff": record.state_diff},
            ),
        )

    def _apply_critics(self, state: StateT, record: StepRecord) -> str:
        if not self.critics:
            return "continue"
        self._dispatch_hook(
            "on_before_critic",
            HookContext(
                task=self._active_task,
                step_id=record.step_id,
                phase=RuntimePhase.CRITIC,
                state=state,
                decision=record.decision,
                action_results=record.action_results,
                record=record,
            ),
        )
        self._emit(record.step_id, RuntimePhase.CRITIC, payload={"stage": "start", "critic_count": len(self.critics)})
        outputs: List[Dict[str, Any]] = []
        for critic in self.critics:
            out = critic.evaluate(state, record.decision, record.action_results)
            outputs.append(out if isinstance(out, dict) else {"action": "continue", "reason": "invalid_critic_output"})
        record.critic_outputs = outputs
        self._emit(record.step_id, RuntimePhase.CRITIC, payload={"stage": "outputs", "critic_outputs": outputs})
        for output in outputs:
            action = str(output.get("action", "continue"))
            if action == "stop":
                self._emit(record.step_id, RuntimePhase.CRITIC, payload={"stage": "stop", "reason": output.get("reason")})
                self._dispatch_hook(
                    "on_after_critic",
                    HookContext(
                        task=self._active_task,
                        step_id=record.step_id,
                        phase=RuntimePhase.CRITIC,
                        state=state,
                        decision=record.decision,
                        action_results=record.action_results,
                        record=record,
                        payload={"critic_outputs": outputs, "result": "stop"},
                    ),
                )
                return "stop"
            if action == "retry":
                self._emit(record.step_id, RuntimePhase.CRITIC, payload={"stage": "retry", "reason": output.get("reason")})
                self._dispatch_hook(
                    "on_after_critic",
                    HookContext(
                        task=self._active_task,
                        step_id=record.step_id,
                        phase=RuntimePhase.CRITIC,
                        state=state,
                        decision=record.decision,
                        action_results=record.action_results,
                        record=record,
                        payload={"critic_outputs": outputs, "result": "retry"},
                    ),
                )
                return "retry"
        self._emit(record.step_id, RuntimePhase.CRITIC, payload={"stage": "pass"})
        self._dispatch_hook(
            "on_after_critic",
            HookContext(
                task=self._active_task,
                step_id=record.step_id,
                phase=RuntimePhase.CRITIC,
                state=state,
                decision=record.decision,
                action_results=record.action_results,
                record=record,
                payload={"critic_outputs": outputs, "result": "continue"},
            ),
        )
        return "continue"

    def _run_check_stop(self, state: StateT, decision: Decision[ActionT], step_id: int, started_at: float) -> bool:
        self._dispatch_hook(
            "on_before_check_stop",
            HookContext(
                task=self._active_task,
                step_id=step_id,
                phase=RuntimePhase.CHECK_STOP,
                state=state,
                decision=decision,
            ),
        )
        self._emit(state.current_step, RuntimePhase.CHECK_STOP, payload={"stage": "start"})

        if decision.mode == "final":
            state.set_stop(StopReason.FINAL, decision.final_answer)
            self._emit(
                state.current_step,
                RuntimePhase.CHECK_STOP,
                payload={"stage": "stop", "stop_reason": state.stop_reason, "final_result": state.final_result},
            )
            self._dispatch_hook(
                "on_after_check_stop",
                HookContext(
                    task=self._active_task,
                    step_id=step_id,
                    phase=RuntimePhase.CHECK_STOP,
                    state=state,
                    decision=decision,
                    stop_reason=state.stop_reason,
                    payload={"result": "stop"},
                ),
            )
            return True

        if self.agent.should_stop(state):
            if state.stop_reason is None:
                state.set_stop(StopReason.AGENT_CONDITION)
            self._emit(
                state.current_step,
                RuntimePhase.CHECK_STOP,
                payload={"stage": "stop", "stop_reason": state.stop_reason, "final_result": state.final_result},
            )
            self._dispatch_hook(
                "on_after_check_stop",
                HookContext(
                    task=self._active_task,
                    step_id=step_id,
                    phase=RuntimePhase.CHECK_STOP,
                    state=state,
                    decision=decision,
                    stop_reason=state.stop_reason,
                    payload={"result": "stop"},
                ),
            )
            return True

        if self.env is not None and self.env.is_terminal(state=state, last_result=self._last_env_result):
            if state.stop_reason is None:
                state.set_stop(StopReason.ENV_TERMINAL)
            self._emit(
                state.current_step,
                RuntimePhase.CHECK_STOP,
                payload={
                    "stage": "stop",
                    "stop_reason": state.stop_reason,
                    "final_result": state.final_result,
                    "env_terminal": True,
                },
            )
            self._dispatch_hook(
                "on_after_check_stop",
                HookContext(
                    task=self._active_task,
                    step_id=step_id,
                    phase=RuntimePhase.CHECK_STOP,
                    state=state,
                    decision=decision,
                    stop_reason=state.stop_reason,
                    payload={"result": "stop"},
                ),
            )
            return True

        elapsed = time.monotonic() - started_at
        should_stop, reason, detail = self._should_stop_by_criteria(state, step_id, elapsed)
        if should_stop:
            if state.stop_reason is None:
                state.set_stop(reason or StopReason.UNRECOVERABLE_ERROR)
            self._emit(
                state.current_step,
                RuntimePhase.CHECK_STOP,
                payload={
                    "stage": "stop",
                    "stop_reason": state.stop_reason,
                    "final_result": state.final_result,
                    "stop_detail": detail,
                },
            )
            self._dispatch_hook(
                "on_after_check_stop",
                HookContext(
                    task=self._active_task,
                    step_id=step_id,
                    phase=RuntimePhase.CHECK_STOP,
                    state=state,
                    decision=decision,
                    stop_reason=state.stop_reason,
                    payload={"result": "stop"},
                ),
            )
            return True

        self._emit(state.current_step, RuntimePhase.CHECK_STOP, payload={"stage": "continue"})
        self._dispatch_hook(
            "on_after_check_stop",
            HookContext(
                task=self._active_task,
                step_id=step_id,
                phase=RuntimePhase.CHECK_STOP,
                state=state,
                decision=decision,
                payload={"result": "continue"},
            ),
        )
        return False

    def _should_stop_by_criteria(self, state: StateT, step_id: int, elapsed_seconds: float) -> tuple[bool, Optional[StopReason], Optional[str]]:
        for criteria in self.stop_criteria:
            hit, reason, detail = criteria.should_stop(
                state,
                step_id,
                runtime_info={
                    "elapsed_seconds": elapsed_seconds,
                    "budget_max_steps": self.budget.max_steps,
                    "budget_max_runtime_seconds": self.budget.max_runtime_seconds,
                    "budget_max_tokens": self.budget.max_tokens,
                },
            )
            if hit:
                return True, reason, detail
        return False, None, None

    def _budget_exhausted(self, step_id: int, started_at: float, state: StateT) -> bool:
        if step_id >= self.budget.max_steps:
            state.set_stop(StopReason.BUDGET_STEPS)
            return True

        if self.budget.max_runtime_seconds is not None:
            elapsed = time.monotonic() - started_at
            if elapsed > self.budget.max_runtime_seconds:
                state.set_stop(StopReason.BUDGET_TIME)
                return True

        if self.budget.max_tokens is not None and self._token_usage >= int(self.budget.max_tokens):
            state.set_stop(StopReason.BUDGET_TOKENS)
            return True

        return False

    def _normalize_decision(self, raw_decision: Any, step: int) -> Decision[ActionT]:
        if isinstance(raw_decision, Decision):
            return raw_decision

        parser = self.parser or getattr(self.agent, "model_parser", None)
        if parser is not None:
            try:
                return parser.parse(raw_decision, context={"step": step})
            except Exception as exc:
                info = RuntimeErrorInfo(
                    category=ErrorCategory.PARSE,
                    message=str(exc),
                    phase="decide",
                    step_id=step,
                    recoverable=True,
                )
                raise ParseExecutionError(info) from exc

        raise ValueError("Agent.decide must return Decision when no parser is configured")

    def _compute_state_diff(self, before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
        diff: Dict[str, Any] = {}
        all_keys = set(before.keys()) | set(after.keys())
        for key in all_keys:
            b = before.get(key)
            a = after.get(key)
            if b != a:
                diff[key] = {"before": b, "after": a}
        return diff

    def _recover(self, state: StateT, phase: RuntimePhase, exc: Exception) -> bool:
        step_id = state.current_step
        self._dispatch_hook(
            "on_recover",
            HookContext(
                task=self._active_task,
                step_id=step_id,
                phase=phase,
                state=state,
                error=exc,
                stop_reason=state.stop_reason,
            ),
        )
        if phase == RuntimePhase.DECIDE:
            self._emit(step_id, RuntimePhase.DECIDE_ERROR, ok=False, error=str(exc))
        elif phase == RuntimePhase.ACT:
            self._emit(step_id, RuntimePhase.ACT_ERROR, ok=False, error=str(exc))
        self._emit(step_id, RuntimePhase.RECOVER, ok=False, error=str(exc))

        if self.recovery_handler is not None:
            self.recovery_handler(state, phase, exc)

        decision = self.recovery_policy.handle(state, phase.value, step_id, exc)
        if decision.stop_reason:
            state.set_stop(decision.stop_reason)

        if not decision.continue_run and state.stop_reason is None:
            state.set_stop(StopReason.UNRECOVERABLE_ERROR)

        return decision.continue_run

    def _emit(
        self,
        step_id: int,
        phase: RuntimePhase,
        ok: bool = True,
        payload: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        event_ts = datetime.now(timezone.utc).isoformat()
        event_payload = dict(payload or {})
        event_payload.setdefault("run_id", self._active_run_id)
        event_payload.setdefault("step_id", step_id)
        event_payload.setdefault("phase", phase.value)
        event_payload.setdefault("ts", event_ts)
        event = RuntimeEvent(step_id=step_id, phase=phase, ok=ok, payload=event_payload, error=error, ts=event_ts)
        self.events.append(event)
        if self.records and self.records[-1].step_id == step_id:
            self.records[-1].phase_events.append(event)
        self._write_trace_event(event)
        state = self._active_state
        if state is not None:
            self._notify_event(event, state)

    def _write_trace_event(self, event: RuntimeEvent) -> None:
        if self.trace_writer is None:
            return
        self.trace_writer.write_event(runtime_event_to_trace(self.trace_writer.run_id, event))

    def _write_trace_step(self, step: StepRecord) -> None:
        if self.trace_writer is None:
            return
        self.trace_writer.write_step(runtime_step_to_trace(step))

    def _finalize_step(self, record: StepRecord, state: StateT) -> None:
        self._write_trace_step(record)
        for hook in self.hooks:
            on_step_end = getattr(hook, "on_step_end", None)
            if on_step_end is None:
                continue
            try:
                on_step_end(record=record, state=state, engine=self)
            except Exception:
                continue

    def _memory_append(
        self,
        role: str,
        content: Any,
        step_id: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        memory = self._memory()
        if memory is None:
            return
        memory.append(MemoryRecord(role=role, content=content, step_id=step_id, metadata=metadata or {}))

    def _memory(self) -> Optional[Memory]:
        mem = getattr(self.agent, "memory", None)
        return mem if isinstance(mem, Memory) else None

    def _infer_failed_phase(self, record: StepRecord) -> RuntimePhase:
        if not record.phase_events:
            return RuntimePhase.RECOVER
        latest = record.phase_events[-1].phase
        if latest == RuntimePhase.DECIDE:
            return RuntimePhase.DECIDE
        if latest == RuntimePhase.ACT:
            return RuntimePhase.ACT
        return RuntimePhase.RECOVER

    def _normalize_task(self, task: str | Task) -> tuple[Optional[Task], str]:
        if isinstance(task, Task):
            return task, task.objective
        return None, str(task)

    def _preflight_validate(self, task_obj: Optional[Task], workspace: Any = None) -> List[TaskValidationIssue]:
        issues: List[TaskValidationIssue] = []
        if task_obj is not None:
            try:
                issues.extend(task_obj.validate_structured(workspace=str(workspace) if workspace else None))
            except Exception as exc:
                issues.append(
                    TaskValidationIssue(
                        code="TASK_VALIDATION_EXCEPTION",
                        message=str(exc),
                        field="task",
                    )
                )

        for issue in self._validate_env_capabilities():
            issues.append(
                TaskValidationIssue(
                    code=str(issue.get("code", "ENV_CAPABILITY_ERROR")),
                    message=str(issue.get("message", "Environment capability mismatch")),
                    field=str(issue.get("field", "env")),
                    details=issue.get("details", {}) if isinstance(issue.get("details", {}), dict) else {},
                )
            )
        health = self._validate_env_health()
        if health is not None:
            issues.append(
                TaskValidationIssue(
                    code=str(health.get("code", "ENV_HEALTH_CHECK_FAILED")),
                    message=str(health.get("message", "Environment health check failed")),
                    field=str(health.get("field", "env")),
                    details=health.get("details", {}) if isinstance(health.get("details", {}), dict) else {},
                )
            )
        return issues

    def _validate_env_capabilities(self) -> List[Dict[str, Any]]:
        required = self._collect_required_ops()
        if not required:
            return []
        if self.env is None:
            return [
                {
                    "code": "ENV_REQUIRED_OPS_MISSING",
                    "message": "No env configured but tools require env ops",
                    "field": "env",
                    "details": {"required_ops": sorted(required)},
                }
            ]
        missing = [group for group in sorted(required) if not self.env.has_ops(group)]
        if not missing:
            return []
        return [
            {
                "code": "ENV_OPS_GROUP_MISSING",
                "message": "Env is missing required ops groups",
                "field": "env",
                "details": {
                    "env_name": getattr(self.env, "name", self.env.__class__.__name__),
                    "missing_ops": missing,
                    "required_ops": sorted(required),
                },
            }
        ]

    def _collect_required_ops(self) -> set[str]:
        required: set[str] = set()
        if self.tool_registry is None or not hasattr(self.tool_registry, "list_tools"):
            return required
        try:
            for tool_name in self.tool_registry.list_tools():
                tool = self.tool_registry.get(tool_name) if hasattr(self.tool_registry, "get") else None
                spec = getattr(tool, "spec", None)
                groups = getattr(spec, "required_ops", None)
                if isinstance(groups, list):
                    required.update(str(x) for x in groups if str(x))
        except Exception:
            return required
        return required

    def _validate_env_health(self) -> Optional[Dict[str, Any]]:
        if self.env is None:
            return None
        try:
            probe = self.env.health_check()
        except Exception as exc:
            return {
                "code": "ENV_HEALTH_CHECK_EXCEPTION",
                "message": f"Env health_check raised exception: {exc}",
                "field": "env",
                "details": {"env_name": getattr(self.env, "name", self.env.__class__.__name__)},
            }
        if not isinstance(probe, dict):
            return None
        if bool(probe.get("ok", True)):
            return None
        return {
            "code": "ENV_HEALTH_CHECK_FAILED",
            "message": str(probe.get("message", "Environment health probe failed")),
            "field": "env",
            "details": probe,
        }

    def _setup_env(self, task_obj: Optional[Task], state: StateT, kwargs: Dict[str, Any]) -> None:
        if self.env is None and task_obj is not None and task_obj.env_spec is not None:
            self.env = self._build_env_from_spec(task_obj.env_spec, fallback_workspace=kwargs.get("workspace"))
        if self.env is None:
            return
        workspace = kwargs.get("workspace")
        reset_task: Any = task_obj if task_obj is not None else self._active_task
        resources = task_obj.resolve_resources(workspace=str(workspace) if workspace else None) if task_obj is not None else []
        try:
            self.env.setup(task=reset_task, workspace=workspace, resources=resources)
            first = self.env.reset(task=reset_task, workspace=workspace, resources=resources)
            if not isinstance(first, EnvObservation):
                first = EnvObservation(data={"value": first})
            self._last_env_observation = first
            self._last_env_result = EnvStepResult(observation=first, done=False, info={"source": "reset"})
        except Exception as exc:
            self._last_env_observation = EnvObservation(data={"error": str(exc)})
            self._last_env_result = EnvStepResult(observation=self._last_env_observation, done=False, error=str(exc))

    def _build_env_from_spec(self, env_spec: Any, fallback_workspace: Any = None) -> Optional[Env]:
        env_type = str(getattr(env_spec, "type", "")).strip().lower()
        config = getattr(env_spec, "config", {})
        if not isinstance(config, dict):
            config = {}
        workspace_root = str(config.get("workspace_root") or fallback_workspace or ".")
        if env_type in {"repo", "repository"}:
            try:
                from ..kit.env import RepoEnv

                return RepoEnv(workspace_root=workspace_root)
            except Exception:
                return None
        if env_type in {"host", "local"}:
            try:
                from ..kit.env import HostEnv

                return HostEnv(workspace_root=workspace_root)
            except Exception:
                return None
        if env_type in {"docker", "container"}:
            try:
                from ..kit.env import DockerEnv

                container = str(config.get("container", "")).strip()
                if not container:
                    return None
                container_workspace = str(config.get("container_workspace") or workspace_root or "/workspace")
                return DockerEnv(container=container, workspace_root=container_workspace)
            except Exception:
                return None
        return None

    def _teardown_env(self) -> None:
        if self.env is None:
            return
        try:
            self.env.teardown()
        except Exception:
            return

    def _run_env_step(self, decision: Decision[ActionT], action_results: List[Any]) -> Optional[EnvStepResult]:
        if self.env is None:
            return None
        try:
            result = self.env.step(
                action={
                    "decision_mode": decision.mode,
                    "actions": decision.actions,
                    "final_answer": decision.final_answer,
                    "action_results": action_results,
                },
                state=self._active_state,
            )
            if not isinstance(result, EnvStepResult):
                result = EnvStepResult(observation=EnvObservation(data={"value": result}))
            self._last_env_result = result
            self._last_env_observation = result.observation
            self._emit(
                self._active_state.current_step if self._active_state is not None else 0,
                RuntimePhase.ACT,
                payload={"stage": "env_step", "env_result": self._env_step_result_to_dict(result)},
            )
            return result
        except Exception as exc:
            err = EnvStepResult(
                observation=EnvObservation(data={"error": str(exc)}),
                done=False,
                error=str(exc),
            )
            self._last_env_result = err
            self._last_env_observation = err.observation
            self._emit(
                self._active_state.current_step if self._active_state is not None else 0,
                RuntimePhase.ACT,
                ok=False,
                payload={"stage": "env_step_error"},
                error=str(exc),
            )
            return err

    def _env_payload(self) -> Dict[str, Any]:
        if self.env is None:
            return {"enabled": False}
        ident = self._env_identity()
        return {
            "enabled": True,
            "name": ident["name"],
            "version": ident["version"],
            "observation": self._env_observation_to_dict(self._last_env_observation),
            "last_result": self._env_step_result_to_dict(self._last_env_result) if self._last_env_result is not None else None,
        }

    def _env_identity(self) -> Dict[str, Any]:
        if self.env is None:
            return {"enabled": False, "name": None, "version": None}
        return {
            "enabled": True,
            "name": getattr(self.env, "name", self.env.__class__.__name__),
            "version": getattr(self.env, "version", "0"),
        }

    def _env_observation_to_dict(self, observation: Optional[EnvObservation]) -> Optional[Dict[str, Any]]:
        if observation is None:
            return None
        return {"data": observation.data, "metadata": observation.metadata}

    def _env_step_result_to_dict(self, result: Optional[EnvStepResult]) -> Optional[Dict[str, Any]]:
        if result is None:
            return None
        return {
            "observation": self._env_observation_to_dict(result.observation),
            "done": result.done,
            "reward": result.reward,
            "info": result.info,
            "error": result.error,
        }

    def _setup_toolsets(self, context: Dict[str, Any]) -> None:
        if not hasattr(self.tool_registry, "setup"):
            return
        self._write_lifecycle_event("toolset_setup_start", context)
        try:
            self.tool_registry.setup(context)
            self._write_lifecycle_event("toolset_setup_end", context)
        except Exception as exc:
            self._write_lifecycle_event("toolset_setup_error", context, ok=False, error=str(exc))

    def _teardown_toolsets(self, context: Dict[str, Any]) -> None:
        if not hasattr(self.tool_registry, "teardown"):
            return
        self._write_lifecycle_event("toolset_teardown_start", context)
        try:
            self.tool_registry.teardown(context)
            self._write_lifecycle_event("toolset_teardown_end", context)
        except Exception as exc:
            self._write_lifecycle_event("toolset_teardown_error", context, ok=False, error=str(exc))

    def _write_lifecycle_event(self, phase: str, payload: Dict[str, Any], ok: bool = True, error: Optional[str] = None) -> None:
        if self.trace_writer is None:
            return
        from ..trace.events import TraceEvent

        event = TraceEvent(
            run_id=self.trace_writer.run_id,
            step_id=0,
            phase=phase,
            payload=self._sanitize_payload(payload),
            ok=ok,
            error=error,
        )
        self.trace_writer.write_event(event)

    def _estimate_tokens(self, payload: Any) -> int:
        text = payload if isinstance(payload, str) else repr(payload)
        if not text:
            return 0
        return max(1, len(text) // 4)

    def _task_meta(self, task_obj: Optional[Task]) -> Optional[Dict[str, Any]]:
        if task_obj is None:
            return None
        payload = task_obj.to_dict()
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return {
            "task_id": task_obj.id,
            "env_spec": payload.get("env_spec"),
            "budget": payload.get("budget"),
            "success_criteria": payload.get("success_criteria", []),
            "input_hash": hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16],
        }

    def _task_issue_to_dict(self, issue: TaskValidationIssue) -> Dict[str, Any]:
        return {
            "code": issue.code,
            "message": issue.message,
            "field": issue.field,
            "details": issue.details,
        }

    def _hydrate_trace_metadata(self, task_obj: Optional[Task], task_text: str) -> None:
        if self.trace_writer is None:
            return
        run_meta = self._run_meta()
        task_meta = self._task_meta(task_obj) or {}
        prompt_seed = {
            "task": task_text,
            "agent": getattr(self.agent, "name", self.agent.__class__.__name__),
            "parser": run_meta.get("parser"),
            "model_name": run_meta.get("model_name"),
            "tool_count": run_meta.get("tool_count"),
        }
        prompt_hash = hashlib.sha256(json.dumps(prompt_seed, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        run_cfg_hash = hashlib.sha256(json.dumps({"task_meta": task_meta, "run_meta": run_meta}, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        self.trace_writer.metadata.update(
            {
                "model_id": run_meta.get("model_name") or "unknown",
                "prompt_hash": prompt_hash,
                "tool_versions": {item.get("name", ""): item.get("origin", {}) for item in run_meta.get("tools", []) if isinstance(item, dict)},
                "seed": getattr(self.agent, "config", {}).get("seed") if isinstance(getattr(self.agent, "config", {}), dict) else None,
                "run_config_hash": run_cfg_hash,
                "task_hash": task_meta.get("input_hash"),
                "env_fingerprint": run_meta.get("env"),
            }
        )

    def _run_meta(self) -> Dict[str, Any]:
        llm = getattr(self.agent, "llm", None)
        model_name = getattr(llm, "model", None) if llm is not None else None
        parser_name = self.parser.__class__.__name__ if self.parser is not None else (
            self.agent.model_parser.__class__.__name__ if getattr(self.agent, "model_parser", None) is not None else None
        )
        tools: List[Dict[str, Any]] = []
        if self.tool_registry is not None and hasattr(self.tool_registry, "list_tools"):
            try:
                for name in self.tool_registry.list_tools():
                    if hasattr(self.tool_registry, "describe_tool"):
                        tools.append(self.tool_registry.describe_tool(name))
                    else:
                        tools.append({"name": name})
            except Exception:
                pass
        env_info = self._env_identity()
        return {
            "model_name": model_name,
            "parser": parser_name,
            "tool_count": len(tools),
            "tools": tools,
            "env": env_info,
        }

    def _build_task_result(self, state: StateT, task_obj: Optional[Task], started_at: float) -> TaskResult:
        stop_reason = state.stop_reason
        success = stop_reason in {
            StopReason.SUCCESS.value,
            StopReason.FINAL.value,
            StopReason.ENV_TERMINAL.value,
            StopReason.AGENT_CONDITION.value,
        }
        criteria_results: List[TaskCriterionResult] = []
        criteria = task_obj.success_criteria if task_obj is not None else []
        for c in criteria:
            criteria_results.append(
                TaskCriterionResult(
                    criterion=str(c),
                    passed=success,
                    evidence=str(state.final_result or stop_reason or ""),
                )
            )
        workspace = getattr(self.env, "workspace_root", None) if self.env is not None else None
        artifacts = task_obj.resolve_resources(workspace=workspace) if task_obj is not None else []
        elapsed_seconds = max(0.0, time.monotonic() - started_at)
        return TaskResult(
            task_id=task_obj.id if task_obj is not None else "",
            success=success,
            stop_reason=stop_reason,
            final_result=state.final_result,
            criteria=criteria_results,
            artifacts=artifacts,
            metrics={
                "steps": len(self.records),
                "elapsed_seconds": elapsed_seconds,
                "token_usage": self._token_usage,
            },
            metadata={
                "task_meta": self._task_meta(task_obj),
                "run_meta": self._run_meta(),
            },
        )

    def _sanitize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        safe: Dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                safe[key] = value
            elif isinstance(value, dict):
                safe[key] = {str(k): (v if isinstance(v, (str, int, float, bool)) or v is None else repr(v)) for k, v in value.items()}
            else:
                safe[key] = repr(value)
        return safe

    def _notify_event(self, event: RuntimeEvent, state: StateT) -> None:
        record: Optional[StepRecord] = None
        if self.records and self.records[-1].step_id == event.step_id:
            record = self.records[-1]
        for hook in self.hooks:
            on_event = getattr(hook, "on_event", None)
            if on_event is None:
                continue
            try:
                on_event(event=event, state=state, record=record, engine=self)
            except Exception:
                continue

    def _notify_run_start(self, task: str, state: StateT) -> None:
        for hook in self.hooks:
            on_run_start = getattr(hook, "on_run_start", None)
            if on_run_start is None:
                continue
            try:
                on_run_start(task=task, state=state, engine=self)
            except Exception:
                continue

    def _notify_run_end(self, result: EngineResult[StateT]) -> None:
        for hook in self.hooks:
            on_run_end = getattr(hook, "on_run_end", None)
            if on_run_end is None:
                continue
            try:
                on_run_end(result=result, engine=self)
            except Exception:
                continue

    def _dispatch_hook(self, method_name: str, ctx: HookContext) -> None:
        self._inject_hook_payload(method_name, ctx)
        for hook in self.hooks:
            method = getattr(hook, method_name, None)
            if method is None:
                continue
            try:
                method(ctx=ctx, engine=self)
            except TypeError:
                # compatibility with hooks using positional signatures
                try:
                    method(ctx, self)
                except Exception:
                    continue
            except Exception:
                continue

    def _inject_hook_payload(self, method_name: str, ctx: HookContext) -> None:
        now = datetime.now(timezone.utc).isoformat()
        ctx.run_id = self._active_run_id
        if not ctx.ts:
            ctx.ts = now
        payload = dict(ctx.payload or {})
        payload.setdefault("run_id", self._active_run_id)
        payload.setdefault("step_id", ctx.step_id)
        payload.setdefault("phase", ctx.phase.value)
        payload.setdefault("hook", method_name)
        payload.setdefault("task", ctx.task)
        payload.setdefault("stop_reason", ctx.stop_reason or getattr(ctx.state, "stop_reason", None))
        payload.setdefault("ts", ctx.ts)
        payload.setdefault(
            "state_digest",
            {
                "current_step": getattr(ctx.state, "current_step", None),
                "has_final_result": bool(getattr(ctx.state, "final_result", None)),
                "stop_reason": getattr(ctx.state, "stop_reason", None),
            },
        )
        payload.setdefault(
            "decision_digest",
            {
                "mode": getattr(ctx.decision, "mode", None) if ctx.decision is not None else None,
                "has_actions": bool(getattr(ctx.decision, "actions", None)) if ctx.decision is not None else False,
                "has_final_answer": bool(getattr(ctx.decision, "final_answer", None)) if ctx.decision is not None else False,
            },
        )
        payload.setdefault(
            "action_digest",
            {
                "result_count": len(ctx.action_results or []),
                "tool_invocation_count": len(getattr(ctx.record, "tool_invocations", []) or []) if ctx.record is not None else 0,
            },
        )
        payload.setdefault("error", str(ctx.error) if ctx.error is not None else None)
        ctx.payload = payload


__all__ = ["Engine", "EngineResult"]
