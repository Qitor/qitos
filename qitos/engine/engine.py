"""Canonical Engine for AgentModule execution."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

from ..core.action import Action
from ..core.agent_module import AgentModule
from ..core.decision import Decision
from ..core.errors import ErrorCategory, ParseExecutionError, RuntimeErrorInfo, StopReason
from ..core.env import Env, EnvObservation, EnvStepResult
from ..core.memory import Memory, MemoryRecord
from ..core.state import StateSchema
from ..core.task import Task
from ..trace import TraceWriter, runtime_event_to_trace, runtime_step_to_trace
from .action_executor import ActionExecutor
from .branching import BranchSelector, FirstCandidateSelector
from .critic import Critic
from .hooks import EngineHook, HookContext
from .parser import Parser
from .recovery import RecoveryPolicy, build_failure_report
from .search import Search
from .states import RuntimeBudget, RuntimeEvent, RuntimePhase, StepRecord
from .stop_criteria import FinalResultCriteria, MaxRuntimeCriteria, MaxStepsCriteria, StopCriteria
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
        self.memory = memory
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
            self.stop_criteria = [MaxStepsCriteria(self.budget.max_steps)]
            if self.budget.max_runtime_seconds is not None:
                self.stop_criteria.append(MaxRuntimeCriteria(self.budget.max_runtime_seconds))
            self.stop_criteria.append(FinalResultCriteria())
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
        task_obj, task_text = self._normalize_task(task)
        self._apply_task_budget(task_obj)
        state = self.agent.init_state(task_text, **kwargs)
        self._active_task = task_text
        self._active_task_obj = task_obj
        self._active_state = state
        started_at = time.monotonic()

        self._setup_toolsets({"state": state, "trace_writer": self.trace_writer, "task": task_obj or task_text})
        self._setup_env(task_obj=task_obj, state=state, kwargs=kwargs)
        self._emit(
            0,
            RuntimePhase.INIT,
            payload={
                "task": task_text,
                "task_id": task_obj.id if task_obj is not None else None,
                "env": self._env_identity(),
            },
        )
        self._notify_run_start(task_text, state)

        step_id = 0
        try:
            while True:
                if self._budget_exhausted(step_id, started_at, state):
                    self._emit(step_id, RuntimePhase.END, ok=False, payload={"stop_reason": state.stop_reason})
                    break

                self.validation_gate.before_phase(state, RuntimePhase.OBSERVE.value)

                record = StepRecord(step_id=step_id)
                self.records.append(record)

                env_view = self._build_env_view(state, step_id, started_at)
                self._dispatch_hook(
                    "on_before_step",
                    HookContext(
                        task=task_text,
                        step_id=step_id,
                        phase=RuntimePhase.OBSERVE,
                        state=state,
                        env_view=env_view,
                        record=record,
                    ),
                )
                try:
                    observation = self._run_observe(state, env_view, record)
                    decision = self._run_decide(state, observation, record)
                    action_results = self._run_act(state, decision, record)
                    self._run_reduce(state, observation, decision, action_results, record)
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
                    state.advance_step()
                    step_id += 1
                    continue

                critic_action = self._apply_critics(state, record)
                if critic_action == "stop":
                    state.set_stop("critic_stop")
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
                    "failure_report": build_failure_report(self.recovery_policy, state.stop_reason),
                },
            )

        result = EngineResult(state=state, records=self.records, events=self.events, step_count=len(self.records))
        self._notify_run_end(result)
        self._active_state = None
        self._active_task = ""
        self._active_task_obj = None
        self._last_env_observation = None
        self._last_env_result = None
        return result

    def _apply_task_budget(self, task_obj: Optional[Task]) -> None:
        self.budget.max_steps = self._base_budget.max_steps
        self.budget.max_runtime_seconds = self._base_budget.max_runtime_seconds
        self.budget.max_tokens = self._base_budget.max_tokens
        if task_obj is None:
            if self._uses_default_stop_criteria:
                self.stop_criteria = [MaxStepsCriteria(self.budget.max_steps)]
                if self.budget.max_runtime_seconds is not None:
                    self.stop_criteria.append(MaxRuntimeCriteria(self.budget.max_runtime_seconds))
                self.stop_criteria.append(FinalResultCriteria())
            return
        budget = task_obj.budget
        if budget.max_steps is not None:
            self.budget.max_steps = int(budget.max_steps)
        if budget.max_runtime_seconds is not None:
            self.budget.max_runtime_seconds = float(budget.max_runtime_seconds)
        if budget.max_tokens is not None:
            self.budget.max_tokens = int(budget.max_tokens)
        if self._uses_default_stop_criteria:
            self.stop_criteria = [MaxStepsCriteria(self.budget.max_steps)]
            if self.budget.max_runtime_seconds is not None:
                self.stop_criteria.append(MaxRuntimeCriteria(self.budget.max_runtime_seconds))
            self.stop_criteria.append(FinalResultCriteria())

    def _build_env_view(self, state: StateT, step_id: int, started_at: float) -> Dict[str, Any]:
        elapsed = time.monotonic() - started_at
        memory_context = self._build_memory_context(state, step_id, elapsed)
        env_payload = self._env_payload()
        return {
            "step_id": step_id,
            "elapsed_seconds": elapsed,
            "budget": {
                "max_steps": self.budget.max_steps,
                "max_runtime_seconds": self.budget.max_runtime_seconds,
                "max_tokens": self.budget.max_tokens,
            },
            "metadata": state.metadata,
            "memory": memory_context,
            "env": env_payload,
            "task": self._active_task_obj.to_dict() if self._active_task_obj is not None else {"objective": self._active_task},
        }

    def _run_observe(self, state: StateT, env_view: Dict[str, Any], record: StepRecord) -> ObservationT:
        self._dispatch_hook(
            "on_before_observe",
            HookContext(
                task=self._active_task,
                step_id=record.step_id,
                phase=RuntimePhase.OBSERVE,
                state=state,
                env_view=env_view,
                record=record,
            ),
        )
        self._emit(record.step_id, RuntimePhase.OBSERVE, payload={"stage": "start"})
        observation = self.agent.observe(state, env_view)
        record.observation = observation
        self._memory_append("observation", observation, record.step_id)
        self._emit(
            record.step_id,
            RuntimePhase.OBSERVE,
            payload={
                "stage": "observation_ready",
                "observation": observation,
                "memory": env_view.get("memory", {}),
                "env": env_view.get("env", {}),
            },
        )
        self._dispatch_hook(
            "on_after_observe",
            HookContext(
                task=self._active_task,
                step_id=record.step_id,
                phase=RuntimePhase.OBSERVE,
                state=state,
                env_view=env_view,
                observation=observation,
                record=record,
            ),
        )
        return observation

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
        self._emit(record.step_id, RuntimePhase.DECIDE, payload={"stage": "start"})
        raw_decision = self.agent.decide(state, observation)
        if raw_decision is None:
            if self.agent.llm is None:
                raise ValueError("No llm configured and Agent.decide returned None")
            prepared = self.agent.prepare(state, observation)
            system_prompt = self.agent.build_system_prompt(state)
            messages: List[Dict[str, str]] = []
            if isinstance(system_prompt, str) and system_prompt.strip():
                messages.append({"role": "system", "content": system_prompt})
            history: List[Dict[str, str]] = []
            if self.memory is not None:
                try:
                    retrieved = self.memory.retrieve_messages(
                        state=state,
                        observation=observation,
                        query={},
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
        action_results: List[Any],
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
                action_results=action_results,
                record=record,
            ),
        )
        self._emit(record.step_id, RuntimePhase.REDUCE, payload={"stage": "start"})
        before = state.to_dict()
        new_state = self.agent.reduce(state, observation, decision, action_results)
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
                action_results=action_results,
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
            state.set_stop(StopReason.FINAL.value, decision.final_answer)
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
                state.set_stop(StopReason.AGENT_CONDITION.value)
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
                state.set_stop(StopReason.ENV_TERMINAL.value)
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
        should_stop, reason = self._should_stop_by_criteria(state, step_id, elapsed)
        if should_stop:
            if state.stop_reason is None:
                state.set_stop(reason or StopReason.MAX_STEPS.value)
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

    def _should_stop_by_criteria(self, state: StateT, step_id: int, elapsed_seconds: float) -> tuple[bool, Optional[str]]:
        for criteria in self.stop_criteria:
            hit, reason = criteria.should_stop(
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
                return True, reason
        return False, None

    def _budget_exhausted(self, step_id: int, started_at: float, state: StateT) -> bool:
        if step_id >= self.budget.max_steps:
            state.set_stop(StopReason.BUDGET_STEPS.value)
            return True

        if self.budget.max_runtime_seconds is not None:
            elapsed = time.monotonic() - started_at
            if elapsed > self.budget.max_runtime_seconds:
                state.set_stop(StopReason.BUDGET_TIME.value)
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
            state.set_stop(StopReason.UNRECOVERABLE_ERROR.value)

        return decision.continue_run

    def _emit(
        self,
        step_id: int,
        phase: RuntimePhase,
        ok: bool = True,
        payload: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        event = RuntimeEvent(step_id=step_id, phase=phase, ok=ok, payload=payload or {}, error=error)
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
        if self.memory is None:
            return
        self.memory.append(MemoryRecord(role=role, content=content, step_id=step_id, metadata=metadata or {}))

    def _build_memory_context(self, state: StateT, step_id: int, elapsed_seconds: float) -> Dict[str, Any]:
        if self.memory is None:
            return {"enabled": False, "records": [], "summary": ""}

        env_view = {
            "step_id": step_id,
            "elapsed_seconds": elapsed_seconds,
            "metadata": state.metadata,
        }
        try:
            query = self.agent.build_memory_query(state, env_view)
        except Exception:
            query = {"format": "records", "max_items": 8}
        if query is None:
            query = {"format": "records", "max_items": 8}
        if isinstance(query, dict) and "format" not in query:
            query = dict(query)
            query["format"] = "records"

        try:
            records = self.memory.retrieve(query=query, state=state, observation=None)
        except Exception:
            records = []
        max_items = int(query.get("max_items", 8)) if isinstance(query, dict) else 8
        try:
            summary = self.memory.summarize(max_items=max(1, max_items))
        except Exception:
            summary = ""

        return {
            "enabled": True,
            "query": query,
            "records": [self._memory_record_to_dict(r) for r in records if isinstance(r, MemoryRecord)],
            "summary": summary,
        }

    def _memory_record_to_dict(self, record: MemoryRecord) -> Dict[str, Any]:
        return {
            "role": record.role,
            "content": record.content,
            "step_id": record.step_id,
            "metadata": record.metadata,
        }

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
            task.validate()
            return task, task.objective
        return None, str(task)

    def _setup_env(self, task_obj: Optional[Task], state: StateT, kwargs: Dict[str, Any]) -> None:
        if self.env is None and task_obj is not None and task_obj.env_spec is not None:
            self.env = self._build_env_from_spec(task_obj.env_spec, fallback_workspace=kwargs.get("workspace"))
        if self.env is None:
            return
        workspace = kwargs.get("workspace")
        reset_task: Any = task_obj if task_obj is not None else self._active_task
        try:
            first = self.env.reset(task=reset_task, workspace=workspace)
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
            self.env.close()
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


__all__ = ["Engine", "EngineResult"]
