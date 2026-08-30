"""Keep the S1-D exact-source census and architecture decision auditable."""

from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CENSUS = ROOT / "docs" / "internal" / "plans" / "s1_d_source_census.md"
ADR = ROOT / "docs" / "internal" / "plans" / "s1_d_trajectory_adr.md"

SOURCES: dict[str, tuple[tuple[str, str], ...]] = {
    "D01": (("qitos/engine/states.py", "RuntimeEvent"),),
    "D02": (("qitos/engine/states.py", "StepRecord"),),
    "D03": (("qitos/trace/writer.py", "TraceWriter"),),
    "D04": (
        ("qitos/trace/events.py", "TraceEvent"),
        ("qitos/trace/events.py", "TraceStep"),
        ("qitos/trace/writer.py", "runtime_event_to_trace"),
        ("qitos/trace/writer.py", "runtime_step_to_trace"),
    ),
    "D05": (
        ("qitos/tracing/models.py", "SpanData"),
        ("qitos/tracing/models.py", "Span"),
        ("qitos/tracing/models.py", "Trace"),
        ("qitos/tracing/provider.py", "TracingProvider"),
    ),
    "D06": (("qitos/tracing/legacy_processor.py", "LegacyTraceWriterProcessor"),),
    "D07": (
        ("qitos/render/events.py", "RenderEvent"),
        ("qitos/render/_hooks_impl.py", "RenderStreamHook._emit"),
        ("qitos/render/_hooks_impl.py", "ClaudeStyleHook"),
    ),
    "D08": (
        ("qitos/qita/_cli_app.py", "_discover_runs"),
        ("qitos/qita/_cli_app.py", "_load_run_payload"),
        ("qitos/qita/_cli_app.py", "_build_replay_records"),
        ("qitos/qita/_cli_app.py", "_cmd_export"),
    ),
    "D09": (("qitos/debug/replay.py", "ReplaySession"),),
    "D10": (
        ("qitos/checkpoint/checkpoint.py", "CheckpointData"),
        ("qitos/checkpoint/checkpoint.py", "CheckpointManager"),
        ("qitos/checkpoint/store.py", "Checkpoint"),
        ("qitos/checkpoint/store.py", "CheckpointStore"),
    ),
    "D11": (
        ("qitos/recipes/benchmarks/_shared.py", "build_example_specs"),
        ("qitos/benchmark/common.py", "write_benchmark_results"),
    ),
    "D12": (
        ("qitos/evaluate/base.py", "EvaluationContext"),
        ("qitos/evaluate/base.py", "load_run_artifacts"),
        ("qitos/metric/base.py", "MetricInput"),
    ),
    "D13": (
        ("qitos/leaderboard/store.py", "LeaderboardStore.submit_run_dir"),
        ("qitos/hf/hub.py", "push_run"),
        ("qitos/hf/hub.py", "pull_run"),
    ),
    "D14": (
        ("qitos/core/model_response.py", "ModelResponse.to_summary_dict"),
        ("qitos/engine/_model_runtime.py", "_ModelRuntime"),
    ),
    "D15": (
        ("qitos/core/tool_result.py", "ToolResult"),
        ("qitos/engine/_action_runtime.py", "_ActionRuntime"),
        ("qitos/engine/action_executor.py", "ActionExecutor._build_runtime_context"),
    ),
    "D16": (
        ("qitos/kit/history/compact_history.py", "CompactHistory"),
        ("qitos/engine/_context_runtime.py", "_ContextRuntime.normalize_history_events"),
    ),
    "D17": (
        ("qitos/core/conversation.py", "ExchangeLog"),
        ("qitos/core/conversation.py", "ExchangeLog.to_persistence_dict"),
        ("qitos/core/conversation.py", "ExchangeLog.to_model_dict"),
        ("qitos/core/conversation.py", "ExchangeLog.to_trace_safe_dict"),
    ),
    "D18": (
        ("qitos/core/conversation.py", "OpaqueContinuationAttachment"),
        ("qitos/models/_openai_responses.py", "_model_response_from_responses"),
    ),
    "D19": (
        ("qitos/core/tool_result.py", "ToolResult"),
        ("qitos/core/multimodal.py", "ContentBlock"),
        ("qitos/core/multimodal.py", "observation_visual_assets"),
        ("qitos/kit/tool/library/base.py", "ToolArtifact"),
    ),
    "D20": (
        ("qitos/kit/history/compact_history.py", "CompactionController"),
        ("qitos/kit/history/compact_history.py", "CompactHistory"),
    ),
    "D21": (
        ("qitos/engine/engine.py", "Engine.init_session"),
        ("qitos/engine/engine.py", "Engine.run"),
    ),
    "D22": (("qitos/engine/run_state.py", "RunState"),),
    "D23": (
        ("qitos/engine/engine.py", "Engine._save_checkpoint"),
        ("qitos/engine/engine.py", "Engine.resume_from_checkpoint"),
        ("qitos/engine/engine.py", "Engine.resume"),
    ),
    "D24": (
        ("qitos/checkpoint/fork.py", "fork_checkpoint"),
        ("qitos/checkpoint/fork.py", "list_fork_history"),
    ),
    "D25": (("qitos/qita/_cli_app.py", "_build_handler"),),
    "D26": (("qitos/engine/_handoff_runtime.py", "_HandoffRuntime.execute_handoff"),),
    "D27": (
        ("qitos/kit/tool/delegate.py", "DelegateTool.execute"),
        ("qitos/kit/tool/delegate.py", "DelegateTool._build_sub_engine"),
        ("qitos/kit/tool/delegate.py", "DelegateTool._build_sub_trace_writer"),
    ),
    "D28": (
        ("qitos/kit/tool/fanout.py", "FanOutTool.execute"),
        ("qitos/kit/tool/fanout.py", "FanOutTool._run_sub_agent"),
        ("qitos/kit/tool/fanout.py", "FanOutTool._build_sub_trace_writer"),
    ),
    "D29": (
        ("qitos/kit/tool/delegate.py", "DelegateTool._build_sub_trace_writer"),
        ("qitos/kit/tool/fanout.py", "FanOutTool._build_sub_trace_writer"),
        ("qitos/trace/writer.py", "TraceWriter"),
    ),
    "D30": (
        ("qitos/qita/_cli_app.py", "_cmd_export"),
        ("qitos/hf/hub.py", "push_run"),
        ("qitos/benchmark/common.py", "write_benchmark_results"),
    ),
    "D31": (
        ("scripts/benchmark_trajectory_store.py", "validate_contract_receipts"),
        ("scripts/benchmark_trajectory_store.py", "build_readiness_result"),
    ),
}


def _has_symbol(path: Path, dotted_symbol: str) -> bool:
    nodes: list[ast.AST] = list(ast.parse(path.read_text(encoding="utf-8")).body)
    for part in dotted_symbol.split("."):
        match = next(
            (
                node
                for node in nodes
                if isinstance(
                    node,
                    (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
                )
                and node.name == part
            ),
            None,
        )
        if match is None:
            return False
        nodes = list(getattr(match, "body", []))
    return True


def test_s1_d_census_has_all_rows_and_live_symbols() -> None:
    text = CENSUS.read_text(encoding="utf-8")
    rows = {
        match.group(1): match.group(0)
        for match in re.finditer(r"^\| (D(?:0[1-9]|[12][0-9]|3[01])) \|.*$", text, re.MULTILINE)
    }

    assert set(rows) == set(SOURCES)
    assert len(re.findall(r"^\| D(?:0[1-9]|[12][0-9]|3[01]) \|", text, re.MULTILINE)) == 31
    for evidence_id, references in SOURCES.items():
        for path, symbol in references:
            assert path in rows[evidence_id], (evidence_id, path)
            assert symbol.split(".")[-1] in rows[evidence_id], (evidence_id, symbol)
            source = ROOT / path
            assert source.is_file(), (evidence_id, path)
            assert _has_symbol(source, symbol), (evidence_id, path, symbol)


def test_adr_contains_required_dx_and_single_architecture_decisions() -> None:
    text = ADR.read_text(encoding="utf-8")
    for heading in (
        "## Beginner qita flow",
        "## Advanced lineage inspection",
        "## Resume and fork discoverability",
        "## Error and remediation language",
        "## Public surface budget",
        "## Current trace compatibility presentation",
        "## Rejected dual-trace architecture",
    ):
        assert heading in text
    for name in (
        "Trajectory",
        "TrajectoryRecord",
        "TrajectoryStore",
        "TrajectoryReader",
        "TrajectoryExporter",
        "Lineage",
    ):
        assert name in text
    assert "run-name suffixes are never" in text
    assert "Hashing proves byte identity; it does not sanitize" in text
    assert "S1-D adds zero root exports and zero qita commands" in text


def test_no_second_public_trajectory_generation_was_added() -> None:
    changed_sources = [
        ROOT / "scripts" / "benchmark_trajectory_store.py",
        ROOT / "docs" / "internal" / "plans" / "s1_d_trajectory_adr.md",
    ]
    forbidden = ("TrajectoryV2", "TraceV2", "QitaV2", "TrajectoryNext")
    for path in changed_sources:
        text = path.read_text(encoding="utf-8")
        assert not any(token in text for token in forbidden), path
