"""CyBench-specific utility tools."""

from __future__ import annotations

from typing import Any, Dict, Optional

from qitos.core.tool import BaseTool, ToolPermission, ToolSpec


class SubmitAnswer(BaseTool):
    """Record one answer candidate for CyBench evaluation."""

    def __init__(self):
        super().__init__(
            ToolSpec(
                name="submit_answer",
                description="Submit one answer candidate for current CyBench objective",
                parameters={
                    "answer": {"type": "string", "description": "candidate answer"},
                    "subtask_index": {"type": "integer", "description": "optional subtask index"},
                },
                required=["answer"],
                permissions=ToolPermission(),
                required_ops=[],
            )
        )

    def run(self, answer: str, subtask_index: Optional[int] = None, runtime_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "status": "success",
            "type": "answer_submission",
            "answer": str(answer),
            "subtask_index": int(subtask_index) if subtask_index is not None else None,
        }


__all__ = ["SubmitAnswer"]
