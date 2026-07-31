from __future__ import annotations

import json

from qitos.evaluate import load_run_artifacts
from qitos.trace import CanonicalTraceReader, TraceWriter, swift_record


TOOLS = [{"type": "function", "function": {"name": "READ", "parameters": {"type": "object"}}}]


def test_default_trace_is_compact_canonical_and_round_trips(tmp_path):
    writer = TraceWriter(str(tmp_path), "run", strict_validate=True)
    request = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "task"},
    ]
    writer.record_model_request(step_id=0, messages=request, tools=TOOLS, protocol="native")
    writer.record_model_response(
        step_id=0,
        assistant_message={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "a", "type": "function", "function": {"name": "READ", "arguments": "{\"path\":\"a.c\"}"}},
                {"id": "b", "type": "function", "function": {"name": "READ", "arguments": "{\"path\":\"b.c\"}"}},
            ],
        },
        finish_reason="tool_calls",
        usage={"total_tokens": 12},
        reasoning_content="inspect both files",
        reasoning_fields={"reasoning": "inspect both files"},
        reasoning_source="reasoning",
    )
    writer.record_tool_result(step_id=0, tool_call_id="a", tool_name="READ", content="A", status="success")
    writer.record_tool_result(step_id=0, tool_call_id="b", tool_name="READ", content="B", status="success")
    writer.finalize("completed", {"stop_reason": "success"})

    run = tmp_path / "run"
    assert (run / "trajectory.jsonl").is_file()
    assert not (run / "events.jsonl").exists()
    assert not (run / "steps.jsonl").exists()
    rows = [json.loads(line) for line in (run / "trajectory.jsonl").read_text().splitlines()]
    assert sum(row["record_type"] == "tool_schema" for row in rows) == 1
    assert sum(row["record_type"] == "message" for row in rows) == 5
    turn = CanonicalTraceReader(run / "trajectory.jsonl").turns()[0]
    assert turn["provider_messages"] == request
    assert [item["tool_call_id"] for item in turn["tool_results"]] == ["a", "b"]
    assert turn["model_response"]["reasoning_content"] == "inspect both files"


def test_canonical_reader_streams_turns_without_eager_record_cache(tmp_path):
    writer = TraceWriter(str(tmp_path), "run")
    for step_id in range(3):
        writer.record_model_request(
            step_id=step_id,
            messages=[{"role": "user", "content": f"turn {step_id}"}],
            tools=TOOLS,
        )
        writer.record_model_response(
            step_id=step_id,
            assistant_message={"role": "assistant", "content": "continue"},
        )
    writer.finalize("completed")

    reader = CanonicalTraceReader(tmp_path / "run" / "trajectory.jsonl")
    assert not hasattr(reader, "records")
    assert [turn["step_id"] for turn in reader.iter_turns()] == [0, 1, 2]


def test_canonical_swift_projection_preserves_parallel_calls(tmp_path):
    writer = TraceWriter(str(tmp_path), "run")
    writer.record_model_request(
        step_id=0,
        messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
        tools=TOOLS,
    )
    writer.record_model_response(
        step_id=0,
        assistant_message={
            "role": "assistant",
            "content": "", "tool_calls": [
                {"id": "one", "function": {"name": "READ", "arguments": "{}"}},
                {"id": "two", "function": {"name": "READ", "arguments": "{}"}},
            ],
        },
    )
    writer.record_tool_result(step_id=0, tool_call_id="one", tool_name="READ", content="1", status="success")
    writer.record_tool_result(step_id=0, tool_call_id="two", tool_name="READ", content="2", status="success")
    writer.finalize("completed")

    row = swift_record(tmp_path / "run" / "trajectory.jsonl")
    roles = [item["role"] for item in row["messages"]]
    assert roles == ["system", "user", "tool_call", "tool_call", "tool_response", "tool_response"]
    assert row["qitos_transaction_manifest"][0]["call_ids"] == ["one", "two"]
    assert row["qitos_transaction_manifest"][0]["response_call_ids"] == ["one", "two"]


def test_parsed_calls_amend_the_same_canonical_assistant_turn(tmp_path):
    writer = TraceWriter(str(tmp_path), "run")
    writer.record_model_request(
        step_id=3,
        messages=[{"role": "user", "content": "u"}],
        tools=TOOLS,
    )
    writer.record_model_response(
        step_id=3,
        assistant_message={"role": "assistant", "content": "legacy parser output"},
    )
    writer.record_model_tool_calls(
        step_id=3,
        tool_calls=[{"id": "parsed-1", "function": {"name": "READ", "arguments": "{}"}}],
    )
    writer.record_tool_result(
        step_id=3, tool_call_id="parsed-1", tool_name="READ", content="ok", status="success"
    )
    writer.finalize("completed")

    turn = CanonicalTraceReader(tmp_path / "run" / "trajectory.jsonl").turns()[0]
    assert turn["assistant_message"]["tool_calls"][0]["id"] == "parsed-1"
    assert turn["tool_results"][0]["tool_call_id"] == "parsed-1"


def test_canonical_reader_is_evaluation_compatible_and_redacts(tmp_path):
    writer = TraceWriter(str(tmp_path), "run", metadata={"model_id": "model", "endpoint": "https://private"})
    writer.record_model_request(
        step_id=0,
        messages=[{"role": "system", "content": "Bearer token /home/private/run hf_1234567890abcdefghijkl"}],
        tools=TOOLS,
    )
    writer.record_model_response(step_id=0, assistant_message={"role": "assistant", "content": "ok"})
    writer.finalize("completed")
    text = (tmp_path / "run" / "trajectory.jsonl").read_text()
    assert "private" not in text
    assert "Bearer token" not in text
    assert "hf_1234567890abcdefghijkl" not in text
    artifacts = load_run_artifacts(tmp_path / "run")
    assert len(artifacts["events"]) == 2
    assert len(artifacts["steps"]) == 1
