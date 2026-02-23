"""Model-based trajectory evaluator (LLM-as-judge)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from qitos.evaluate import EvaluationContext, EvaluationResult, TrajectoryEvaluator


@dataclass
class ModelBasedEvaluator(TrajectoryEvaluator):
    name: str = "model_based"
    llm: Any = None
    rubric: str = "Judge whether the agent solved the task. Return JSON: {\"success\": bool, \"score\": number, \"reason\": str}."

    def evaluate(self, context: EvaluationContext) -> EvaluationResult:
        if self.llm is None:
            return EvaluationResult(
                name=self.name,
                success=False,
                score=0.0,
                reasons=["llm_not_configured"],
                evidence={},
            )

        prompt = self._build_prompt(context)
        try:
            raw = self.llm([
                {"role": "system", "content": "You are a strict trajectory evaluator."},
                {"role": "user", "content": prompt},
            ])
            text = str(raw)
            parsed = self._parse_jsonish(text)
            success = bool(parsed.get("success", False))
            score = float(parsed.get("score", 1.0 if success else 0.0))
            reason = str(parsed.get("reason", ""))
            reasons: List[str] = [reason] if reason else []
            return EvaluationResult(
                name=self.name,
                success=success,
                score=score,
                reasons=reasons,
                evidence={"raw": text, "parsed": parsed},
            )
        except Exception as exc:
            return EvaluationResult(
                name=self.name,
                success=False,
                score=0.0,
                reasons=[f"model_eval_error:{exc}"],
                evidence={},
            )

    def _build_prompt(self, context: EvaluationContext) -> str:
        summary = context.manifest.get("summary", {}) if isinstance(context.manifest, dict) else {}
        return "\n".join(
            [
                self.rubric,
                f"Task objective: {context.task.objective}",
                f"Stop reason: {summary.get('stop_reason')}",
                f"Final result: {summary.get('final_result')}",
                f"Extras: {context.extras}",
            ]
        )

    def _parse_jsonish(self, text: str) -> Dict[str, Any]:
        import json

        s = text.strip()
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
        start = s.find("{")
        end = s.rfind("}")
        if start >= 0 and end > start:
            obj = json.loads(s[start : end + 1])
            if isinstance(obj, dict):
                return obj
        return {"success": "true" in s.lower(), "reason": s}
