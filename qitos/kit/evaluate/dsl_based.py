"""DSL-based trajectory evaluator with safe expression subset."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, Dict

from qitos.evaluate import EvaluationContext, EvaluationResult, TrajectoryEvaluator


_ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Subscript,
    ast.Index,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Eq,
    ast.NotEq,
    ast.Gt,
    ast.GtE,
    ast.Lt,
    ast.LtE,
    ast.In,
    ast.NotIn,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
)


@dataclass
class DSLEvaluator(TrajectoryEvaluator):
    name: str = "dsl_based"
    expression: str = "True"

    def evaluate(self, context: EvaluationContext) -> EvaluationResult:
        scope: Dict[str, Any] = {
            "task": context.task.to_dict() if hasattr(context.task, "to_dict") else {},
            "manifest": context.manifest,
            "events": context.events,
            "steps": context.steps,
            "extras": context.extras,
        }
        try:
            tree = ast.parse(self.expression, mode="eval")
            for node in ast.walk(tree):
                if not isinstance(node, _ALLOWED_NODES):
                    raise ValueError(f"disallowed_node:{node.__class__.__name__}")
            value = eval(compile(tree, filename="<dsl>", mode="eval"), {"__builtins__": {}}, scope)
            ok = bool(value)
            return EvaluationResult(
                name=self.name,
                success=ok,
                score=1.0 if ok else 0.0,
                reasons=[] if ok else ["dsl_expression_false"],
                evidence={"expression": self.expression, "value": value},
            )
        except Exception as exc:
            return EvaluationResult(
                name=self.name,
                success=False,
                score=0.0,
                reasons=[f"dsl_error:{exc}"],
                evidence={"expression": self.expression},
            )
