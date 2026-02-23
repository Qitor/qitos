"""Rule-based trajectory evaluator implementations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from qitos.evaluate import EvaluationContext, EvaluationResult, TrajectoryEvaluator


@dataclass
class RuleBasedEvaluator(TrajectoryEvaluator):
    name: str = "rule_based"
    require_stop_reason: Optional[Sequence[str]] = None
    min_reward: Optional[float] = None
    final_contains: Optional[Sequence[str]] = None
    require_artifact_keys: Sequence[str] = field(default_factory=tuple)

    def evaluate(self, context: EvaluationContext) -> EvaluationResult:
        reasons: List[str] = []
        evidence: Dict[str, Any] = {}

        summary = context.manifest.get("summary", {}) if isinstance(context.manifest, dict) else {}
        stop_reason = str(summary.get("stop_reason", ""))
        final_result = summary.get("final_result")

        payload = dict(context.extras or {})
        reward = payload.get("reward")

        ok = True

        if self.require_stop_reason:
            allowed = set(str(x) for x in self.require_stop_reason)
            if stop_reason not in allowed:
                ok = False
                reasons.append(f"stop_reason_not_allowed:{stop_reason}")

        if self.min_reward is not None:
            try:
                rv = float(reward)
            except Exception:
                rv = -1.0
            if rv < float(self.min_reward):
                ok = False
                reasons.append(f"reward_below_threshold:{rv}")
            evidence["reward"] = rv

        if self.final_contains:
            final_text = str(final_result or "")
            missing = [x for x in self.final_contains if str(x) not in final_text]
            if missing:
                ok = False
                reasons.append(f"final_missing:{missing}")

        for key in self.require_artifact_keys:
            if key not in payload:
                ok = False
                reasons.append(f"missing_key:{key}")

        score = 1.0 if ok else 0.0
        evidence.update(
            {
                "stop_reason": stop_reason,
                "final_result": final_result,
                "extras": payload,
            }
        )
        return EvaluationResult(name=self.name, success=ok, score=score, reasons=reasons, evidence=evidence)
