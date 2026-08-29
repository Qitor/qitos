"""Keep Lane D's D01-D16 source ledger linked to real Python symbols."""

from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs" / "internal" / "plans" / "lane_d_data_convergence.md"

SOURCES: dict[str, tuple[tuple[str, str], ...]] = {
    "D01": (
        ("qitos/engine/states.py", "RuntimeEvent"),
        ("qitos/engine/_trace_runtime.py", "_TraceRuntime.emit"),
    ),
    "D02": (
        ("qitos/engine/states.py", "StepRecord"),
        ("qitos/engine/_trace_runtime.py", "_TraceRuntime.finalize_step"),
    ),
    "D03": (
        ("qitos/trace/writer.py", "TraceWriter"),
        ("qitos/trace/schema.py", "TraceSchemaValidator"),
    ),
    "D04": (
        ("qitos/trace/events.py", "TraceEvent"),
        ("qitos/trace/events.py", "TraceStep"),
        ("qitos/trace/writer.py", "runtime_event_to_trace"),
        ("qitos/trace/writer.py", "runtime_step_to_trace"),
        ("qitos/trace/writer.py", "TraceWriter.write_event"),
        ("qitos/trace/writer.py", "TraceWriter.write_step"),
    ),
    "D05": (
        ("qitos/tracing/models.py", "SpanData"),
        ("qitos/tracing/models.py", "Span"),
        ("qitos/tracing/models.py", "Trace"),
        ("qitos/tracing/provider.py", "TracingProvider"),
        ("qitos/tracing/processor.py", "SynchronousMultiTraceProcessor"),
    ),
    "D06": (("qitos/tracing/legacy_processor.py", "LegacyTraceWriterProcessor"),),
    "D07": (
        ("qitos/render/events.py", "RenderEvent"),
        ("qitos/render/_hooks_impl.py", "RenderStreamHook._emit"),
        ("qitos/render/_hooks_impl.py", "ClaudeStyleHook"),
    ),
    "D08": tuple(
        ("qitos/qita/_cli_app.py", symbol)
        for symbol in (
            "_discover_runs",
            "_load_run_payload",
            "_build_replay_records",
            "_cmd_board",
            "_cmd_replay",
            "_cmd_export",
        )
    ),
    "D09": (("qitos/debug/replay.py", "ReplaySession"),),
    "D10": (
        ("qitos/checkpoint/checkpoint.py", "CheckpointData"),
        ("qitos/checkpoint/checkpoint.py", "CheckpointManager"),
        ("qitos/checkpoint/store.py", "Checkpoint"),
        ("qitos/checkpoint/store.py", "CheckpointStore"),
        ("qitos/checkpoint/memory_store.py", "InMemoryCheckpointStore"),
        ("qitos/checkpoint/sqlite_store.py", "SqliteCheckpointStore"),
        ("qitos/checkpoint/fork.py", "fork_checkpoint"),
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
        ("qitos/core/action.py", "ActionResult"),
        ("qitos/core/tool_result.py", "ToolResult"),
        ("qitos/engine/_action_runtime.py", "_ActionRuntime"),
        (
            "qitos/engine/action_executor.py",
            "ActionExecutor._build_runtime_context",
        ),
    ),
    "D16": (
        ("qitos/kit/history/compact_history.py", "CompactHistory"),
        (
            "qitos/engine/_context_runtime.py",
            "_ContextRuntime.normalize_history_events",
        ),
    ),
}


def _has_symbol(path: Path, dotted_symbol: str) -> bool:
    nodes: list[ast.AST] = list(ast.parse(path.read_text(encoding="utf-8")).body)
    for part in dotted_symbol.split("."):
        match = next(
            (
                node
                for node in nodes
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == part
            ),
            None,
        )
        if match is None:
            return False
        nodes = list(getattr(match, "body", []))
    return True


def _expand_reference(path: str, symbols: str) -> set[tuple[str, str]]:
    if symbols.startswith("{") and symbols.endswith("}"):
        return {(path, item) for item in symbols[1:-1].split(",")}
    return {(path, symbols)}


def test_exact_source_ledger_has_one_row_per_id_and_live_symbols() -> None:
    text = PLAN.read_text(encoding="utf-8")
    section = text.split("### Producers, storage, and consumers", 1)[1].split(
        "### Correlation and representation comparison", 1
    )[0]
    rows = {
        match.group(1): match.group(0)
        for match in re.finditer(r"^\| (D(?:0[1-9]|1[0-6])) \|.*$", section, re.MULTILINE)
    }

    assert set(rows) == set(SOURCES)
    assert len(re.findall(r"^\| D(?:0[1-9]|1[0-6]) \|", section, re.MULTILINE)) == 16
    for evidence_id, references in SOURCES.items():
        row_refs: set[tuple[str, str]] = set()
        for path, symbols in re.findall(r"`([^`]+\.py)::([^`]+)`", rows[evidence_id]):
            row_refs.update(_expand_reference(path, symbols))
        assert set(references) <= row_refs, evidence_id
        for path, symbol in references:
            source = ROOT / path
            assert source.is_file(), (evidence_id, path)
            assert _has_symbol(source, symbol), (evidence_id, path, symbol)


def test_d15_keeps_action_and_tool_results_in_their_actual_modules() -> None:
    row = next(
        line
        for line in PLAN.read_text(encoding="utf-8").splitlines()
        if line.startswith("| D15 |")
    )

    assert "qitos/core/action.py::ActionResult" in row
    assert "qitos/core/tool_result.py::ToolResult" in row
    assert "qitos/core/runtime_context.py" not in row
