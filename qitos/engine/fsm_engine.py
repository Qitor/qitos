"""FSM execution engine for QitOS v2 AgentModule lifecycle."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

from ..core.action import Action
from ..core.agent_module import AgentModule
from ..core.decision import Decision
from ..core.errors import StopReason
from ..core.state import StateSchema
from ..core.state_validators import StateValidationGate
from ..memory.v2 import BaseMemoryV2, MemoryRecord
from ..trace import TraceWriter, runtime_event_to_trace, runtime_step_to_trace
from .recovery import RecoveryPolicy, build_failure_report
from .states import RuntimeBudget, RuntimeEvent, RuntimePhase, StepRecord


StateT = TypeVar("StateT", bound=StateSchema)
ObservationT = TypeVar("ObservationT")
ActionT = TypeVar("ActionT")

ActionExecutor = Callable[[Any, List[ActionT]], List[Any]]
RecoveryHandler = Callable[[StateT, RuntimePhase, Exception], None]


@dataclass
class EngineResult(Generic[StateT]):
    state: StateT
    records: List[StepRecord]
    events: List[RuntimeEvent]


class FSMEngine(Generic[StateT, ObservationT, ActionT]):
    """Canonical FSM runner for v2 agents."""

    def __init__(
        self,
        agent: AgentModule[StateT, ObservationT, ActionT],
        action_executor: Optional[ActionExecutor] = None,
        budget: Optional[RuntimeBudget] = None,
        validation_gate: Optional[StateValidationGate] = None,
        recovery_handler: Optional[RecoveryHandler] = None,
        recovery_policy: Optional[RecoveryPolicy] = None,
        trace_writer: Optional[TraceWriter] = None,
        memory: Optional[BaseMemoryV2] = None,
    ):
        self.agent = agent
        self.action_executor = action_executor or self._default_action_executor
        self.budget = budget or RuntimeBudget()
        self.validation_gate = validation_gate or StateValidationGate()
        self.recovery_handler = recovery_handler
        self.recovery_policy = recovery_policy or RecoveryPolicy()
        self.trace_writer = trace_writer
        self.memory = memory
        self.events: List[RuntimeEvent] = []
        self.records: List[StepRecord] = []

    def run(self, task: str, **kwargs: Any) -> EngineResult[StateT]:
        state = self.agent.init_state(task, **kwargs)
        started_at = time.monotonic()

        self._emit(0, RuntimePhase.INIT, payload={"task": task})

        step_id = 0
        while True:
            if self._budget_exhausted(step_id, started_at, state):
                self._emit(step_id, RuntimePhase.END, ok=False, payload={"stop_reason": state.stop_reason})
                break

            self.validation_gate.before_phase(state, RuntimePhase.OBSERVE.value)

            record = StepRecord(step_id=step_id)
            self.records.append(record)

            env_view = self._build_env_view(state, step_id, started_at)
            try:
                observation = self._run_observe(state, env_view, record)
                decision = self._run_decide(state, observation, record)
                action_results = self._run_act(state, decision, record)
                self._run_reduce(state, observation, decision, action_results, record)
            except Exception as exc:
                failed_phase = self._infer_failed_phase(record)
                if not self._recover(state, failed_phase, exc):
                    self._write_trace_step(record)
                    self._emit(step_id, RuntimePhase.END, ok=False, payload={"stop_reason": state.stop_reason})
                    break
                # recoverable: continue to next step
                self._write_trace_step(record)
                state.advance_step()
                step_id += 1
                continue

            stop = self._run_check_stop(state, decision)

            self.validation_gate.after_phase(state, RuntimePhase.CHECK_STOP.value)
            self._write_trace_step(record)

            if stop:
                self._emit(step_id, RuntimePhase.END, payload={"stop_reason": state.stop_reason})
                break

            state.advance_step()
            step_id += 1

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

        return EngineResult(state=state, records=self.records, events=self.events)

    def _build_env_view(self, state: StateT, step_id: int, started_at: float) -> Dict[str, Any]:
        elapsed = time.monotonic() - started_at
        return {
            "step_id": step_id,
            "elapsed_seconds": elapsed,
            "budget": {
                "max_steps": self.budget.max_steps,
                "max_runtime_seconds": self.budget.max_runtime_seconds,
                "max_tokens": self.budget.max_tokens,
            },
            "metadata": state.metadata,
        }

    def _run_observe(self, state: StateT, env_view: Dict[str, Any], record: StepRecord) -> ObservationT:
        self._emit(record.step_id, RuntimePhase.OBSERVE)
        observation = self.agent.observe(state, env_view)
        record.observation = observation
        self._memory_append("observation", observation, record.step_id)
        return observation

    def _run_decide(self, state: StateT, observation: ObservationT, record: StepRecord) -> Decision[ActionT]:
        self._emit(record.step_id, RuntimePhase.DECIDE)
        decision = self.agent.decide(state, observation)

        if decision.mode not in {"act", "final", "wait"}:
            raise ValueError(f"Invalid decision mode: {decision.mode}")

        record.decision = decision
        record.actions = list(decision.actions)
        self._memory_append("decision", decision, record.step_id)
        return decision

    def _run_act(self, state: StateT, decision: Decision[ActionT], record: StepRecord) -> List[Any]:
        self._emit(record.step_id, RuntimePhase.ACT)

        if decision.mode != "act":
            return []

        results = self.action_executor(state, decision.actions)

        record.action_results = results
        for item in results:
            self._memory_append("action_result", item, record.step_id)
        return results

    def _run_reduce(
        self,
        state: StateT,
        observation: ObservationT,
        decision: Decision[ActionT],
        action_results: List[Any],
        record: StepRecord,
    ) -> None:
        self._emit(record.step_id, RuntimePhase.REDUCE)
        before = state.to_dict()
        new_state = self.agent.reduce(state, observation, decision, action_results)
        if new_state is not state:
            # explicit handoff in case reducer returns a copied state
            state.__dict__.update(new_state.__dict__)
        after = state.to_dict()
        record.state_diff = self._compute_state_diff(before, after)

    def _run_check_stop(self, state: StateT, decision: Decision[ActionT]) -> bool:
        self._emit(state.current_step, RuntimePhase.CHECK_STOP)

        if decision.mode == "final":
            state.set_stop(StopReason.FINAL.value, decision.final_answer)
            return True

        if state.current_step + 1 >= min(state.max_steps, self.budget.max_steps):
            state.set_stop(StopReason.MAX_STEPS.value)
            return True

        if self.agent.should_stop(state):
            if state.stop_reason is None:
                state.set_stop(StopReason.AGENT_CONDITION.value)
            return True

        return False

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

    def _default_action_executor(self, state: Any, actions: List[ActionT]) -> List[Any]:
        if not actions:
            return []

        if self.agent.toolkit is None:
            raise RuntimeError("No toolkit configured for action execution")

        results: List[Any] = []
        for action in actions:
            if isinstance(action, Action):
                results.append(self.agent.toolkit.call(action.name, **action.args))
            elif isinstance(action, dict):
                name = action.get("name")
                args = action.get("args", {})
                if not name:
                    raise ValueError(f"Action missing name: {action}")
                results.append(self.agent.toolkit.call(name, **args))
            else:
                raise TypeError(
                    "Default action executor expects dict actions shaped as {'name': ..., 'args': {...}}"
                )
        return results

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

    def _write_trace_event(self, event: RuntimeEvent) -> None:
        if self.trace_writer is None:
            return
        self.trace_writer.write_event(runtime_event_to_trace(self.trace_writer.run_id, event))

    def _write_trace_step(self, step: StepRecord) -> None:
        if self.trace_writer is None:
            return
        self.trace_writer.write_step(runtime_step_to_trace(step))

    def _memory_append(self, role: str, content: Any, step_id: int) -> None:
        if self.memory is None:
            return
        self.memory.append(MemoryRecord(role=role, content=content, step_id=step_id))

    def _infer_failed_phase(self, record: StepRecord) -> RuntimePhase:
        if not record.phase_events:
            return RuntimePhase.RECOVER
        latest = record.phase_events[-1].phase
        if latest == RuntimePhase.DECIDE:
            return RuntimePhase.DECIDE
        if latest == RuntimePhase.ACT:
            return RuntimePhase.ACT
        return RuntimePhase.RECOVER
