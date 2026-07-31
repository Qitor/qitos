"""Template-neutral trajectory projections for training and audit workflows."""

from __future__ import annotations

import json
from itertools import chain
from pathlib import Path
from typing import Any, Dict

from .canonical import CanonicalTraceReader, safe_projection


def openai_record(path: str | Path) -> Dict[str, Any]:
    """Project one canonical run to native OpenAI message/tool-call shape."""
    reader = CanonicalTraceReader(path)
    turns = reader.iter_turns()
    first = next(turns, None)
    if first is None:
        return {"messages": [], "tools": [], "qitos_transaction_manifest": []}
    messages = list(first["provider_messages"])
    tools = list(first["tool_schema"])
    transactions = []
    for turn in chain((first,), turns):
        assistant = turn.get("assistant_message")
        response = dict(turn.get("model_response") or {})
        if isinstance(assistant, dict):
            assistant = dict(assistant)
            reasoning = str(response.get("reasoning_content") or "")
            if reasoning:
                assistant["reasoning_content"] = reasoning
            messages.append(assistant)
        result_ids = []
        for result in turn.get("tool_results") or []:
            message = result.get("message")
            if isinstance(message, dict):
                messages.append(dict(message))
                result_ids.append(str(result.get("tool_call_id") or ""))
        calls = list((assistant or {}).get("tool_calls") or []) if isinstance(assistant, dict) else []
        transactions.append(
            {
                "turn_id": turn.get("turn_id"),
                "step_id": turn.get("step_id"),
                "call_ids": [str(item.get("id") or "") for item in calls if isinstance(item, dict)],
                "response_call_ids": result_ids,
            }
        )
    return safe_projection(
        {"messages": messages, "tools": tools, "qitos_transaction_manifest": transactions}
    )


def swift_record(path: str | Path) -> Dict[str, Any]:
    """Render the canonical transaction stream into ms-swift structural roles."""
    native = openai_record(path)
    swift_messages: list[dict[str, Any]] = []
    for message in native["messages"]:
        role = str(message.get("role") or "")
        if role in {"system", "user"}:
            swift_messages.append({"role": role, "content": message.get("content", ""), "loss": False})
            continue
        if role == "assistant":
            content = str(message.get("content") or "")
            reasoning = str(message.get("reasoning_content") or "")
            if reasoning:
                content = f"<think>\n{reasoning}\n</think>\n\n{content}"
            if content:
                swift_messages.append({"role": "assistant", "content": content, "loss": True})
            for call in list(message.get("tool_calls") or []):
                if not isinstance(call, dict):
                    continue
                function = dict(call.get("function") or {})
                arguments = function.get("arguments", "{}")
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        pass
                swift_messages.append(
                    {
                        "role": "tool_call",
                        "content": json.dumps(
                            {"id": call.get("id"), "name": function.get("name"), "arguments": arguments},
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        "loss": True,
                    }
                )
            continue
        if role == "tool":
            swift_messages.append(
                {
                    "role": "tool_response",
                    "content": json.dumps(
                        {
                            "tool_call_id": message.get("tool_call_id"),
                            "name": message.get("name"),
                            "content": message.get("content"),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "loss": False,
                }
            )
    return {
        "messages": swift_messages,
        "tools": json.dumps(native["tools"], ensure_ascii=False, sort_keys=True),
        "qitos_transaction_manifest": native["qitos_transaction_manifest"],
    }


def audit_record(path: str | Path) -> Dict[str, Any]:
    """Return a compact human/audit projection without provider transport data."""
    reader = CanonicalTraceReader(path)
    return safe_projection(
        {
            "schema": "qitos.audit.v1",
            "turns": reader.turns(),
            "footer": reader.footer(),
        }
    )


__all__ = ["openai_record", "swift_record", "audit_record"]
