"""Regression tests for observed DeepSeek 400 tool-call chain failures.

Observed on 2026-08-04/05 in the deepseek-v4-flash Fleet: 7 tasks died with
``openai.BadRequestError`` 400::

    "An assistant message with 'tool_calls' must be followed by tool messages
    responding to each 'tool_call_id'. (insufficient tool messages following
    tool_calls message)"

Root cause: ``_ModelRuntime._ensure_chain_consistency`` used to append
placeholder tool responses at the END of the message list, but the OpenAI
protocol requires tool responses to immediately follow the assistant message
that declared the ``tool_calls``.  When a dangling assistant ``tool_calls``
message was followed by later messages, the appended placeholders remained out
of order and the API still rejected the chain.  The repair now inserts
placeholders in place and drops later misplaced responses for the same call
ids.

The fixtures under ``qitos/tests/fixtures/tool_call_parity/`` are the exact
``model_input_bundle`` message lists sent to the API at each failing step.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from qitos.engine._model_runtime import _ModelRuntime


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "tool_call_parity"
FIXTURES = sorted(path.name for path in FIXTURE_DIR.glob("*.json"))


def _insufficient_tool_message_violations(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Mimic the OpenAI chain rule that produced the observed 400.

    An assistant message with ``tool_calls`` must be immediately followed by
    tool messages covering every ``tool_call_id`` before any other role
    appears.  A violation is exactly what the provider reported:
    "insufficient tool messages following tool_calls message".
    """
    violations: list[dict[str, Any]] = []
    index = 0
    total = len(messages)
    while index < total:
        message = messages[index]
        if message.get("role") == "assistant" and message.get("tool_calls"):
            call_ids = [
                str(call.get("id"))
                for call in message.get("tool_calls", [])
                if isinstance(call, dict) and call.get("id")
            ]
            if not call_ids:
                index += 1
                continue
            pending = set(call_ids)
            cursor = index + 1
            while pending and cursor < total:
                following = messages[cursor]
                if (
                    following.get("role") == "tool"
                    and str(following.get("tool_call_id")) in pending
                ):
                    pending.remove(str(following.get("tool_call_id")))
                    cursor += 1
                    continue
                break
            if pending:
                violations.append(
                    {
                        "assistant_index": index,
                        "missing_tool_call_ids": sorted(pending),
                        "next_non_tool_index": cursor,
                    }
                )
            index = cursor
            continue
        index += 1
    return violations


def _load_fixture(name: str) -> dict[str, Any]:
    with (FIXTURE_DIR / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def _repair(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _ModelRuntime._ensure_chain_consistency(
        object.__new__(_ModelRuntime), messages
    )


def test_observed_failure_fixtures_reproduce_insufficient_tool_messages() -> None:
    """Every captured 400 payload must still exhibit the same chain violation."""
    assert FIXTURES, "no parity fixtures found under %s" % FIXTURE_DIR
    for name in FIXTURES:
        fixture = _load_fixture(name)
        assert _insufficient_tool_message_violations(fixture["messages"]), name


@pytest.mark.parametrize("name", FIXTURES)
def test_ensure_chain_consistency_repairs_observed_payload(name: str) -> None:
    fixture = _load_fixture(name)
    repaired = _repair(fixture["messages"])
    assert not _insufficient_tool_message_violations(repaired)


def test_ensure_chain_consistency_repairs_middle_dangling_call() -> None:
    messages = [
        {"role": "user", "content": "go"},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_dangling",
                    "type": "function",
                    "function": {"name": "f", "arguments": "{}"},
                }
            ],
        },
        {"role": "assistant", "content": "later"},
        {"role": "user", "content": "next"},
    ]
    repaired = _repair(messages)
    assert not _insufficient_tool_message_violations(repaired)
