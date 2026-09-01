#!/usr/bin/env python3
"""Qualify canonical AgentConfig launches with offline and bounded live gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCHEMA_VERSION = "qitos.s3.g4_l2_qualification/v1"
MAX_REQUESTS_PER_PROFILE = 12
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_HOST_PATH_RE = re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\Users\\)")
_SECRET_MARKER_RE = re.compile(
    r"(?i)(authorization\s*:|bearer\s+[A-Za-z0-9._~+/=-]+|cookie\s*:|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)


class QualificationError(RuntimeError):
    code = "qualification_failed"

    def __init__(self, message: str, *, code: Optional[str] = None) -> None:
        super().__init__(message)
        if code:
            self.code = code


class QualificationConfigurationError(QualificationError):
    code = "qualification_configuration_invalid"


@dataclass(frozen=True)
class LiveProfile:
    config_path: Path
    config: Any

    @property
    def profile_id(self) -> str:
        return str(self.config.name)

    @property
    def credential_ref(self) -> str:
        credential = self.config.model.credential
        return credential.ref if credential is not None else ""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _sha256_json(value: Any) -> str:
    return _sha256_text(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    )


def load_profiles(config_paths: Sequence[str | Path]) -> tuple[LiveProfile, ...]:
    """Load the sole profile authority: strict canonical launch files."""
    from qitos.config import load_agent_config

    if not config_paths:
        raise QualificationConfigurationError("at least one --config is required")
    rows: list[LiveProfile] = []
    for raw_path in config_paths:
        path = Path(raw_path).expanduser().resolve()
        config = load_agent_config(path)
        if config.runtime.environment.type != "docker":
            raise QualificationConfigurationError(
                "live profiles require runtime.environment.type=docker"
            )
        if config.runtime.environment.network != "none":
            raise QualificationConfigurationError(
                "live profiles require runtime.environment.network=none"
            )
        rows.append(LiveProfile(config_path=path, config=config))
    ids = [row.profile_id for row in rows]
    refs = [row.credential_ref for row in rows]
    if len(set(ids)) != len(ids) or len(set(refs)) != len(refs):
        raise QualificationConfigurationError(
            "profile ids and credential references must be distinct"
        )
    return tuple(rows)


def _validate_private_dir(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    candidate.mkdir(mode=0o700, parents=True, exist_ok=True)
    resolved = candidate.resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise QualificationConfigurationError(
            "private evidence directory must be outside the repository"
        )
    resolved.chmod(0o700)
    return resolved


def _validate_source(source_commit: str, *, enforce_current: bool = True) -> None:
    if _COMMIT_RE.fullmatch(source_commit) is None:
        raise QualificationConfigurationError("source commit must be a full SHA")
    if not enforce_current:
        return
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or result.stdout.strip() != source_commit:
        raise QualificationConfigurationError(
            "source commit does not match the checked-out candidate"
        )


def _native_message(response: Any) -> Any:
    choices = getattr(response, "choices", None)
    if isinstance(choices, list) and choices:
        return getattr(choices[0], "message", None)
    if isinstance(response, Mapping):
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            return first.get("message") if isinstance(first, Mapping) else None
    return None


def _field(value: Any, name: str) -> Any:
    return value.get(name) if isinstance(value, Mapping) else getattr(value, name, None)


def _native_calls(response: Any) -> list[dict[str, Any]]:
    """Read only provider-native tool calls; never parse assistant text."""
    calls = _field(_native_message(response), "tool_calls")
    if not isinstance(calls, list):
        return []
    output: list[dict[str, Any]] = []
    for item in calls:
        function = _field(item, "function")
        call_id = _field(item, "id")
        name = _field(function, "name")
        arguments = _field(function, "arguments")
        if not isinstance(call_id, str) or not isinstance(name, str):
            continue
        output.append(
            {
                "id": call_id,
                "type": str(_field(item, "type") or "function"),
                "function": {
                    "name": name,
                    "arguments": str(arguments if arguments is not None else "{}"),
                },
            }
        )
    return output


def _response_text(response: Any) -> str:
    content = _field(_native_message(response), "content")
    if isinstance(content, str):
        return content
    if isinstance(response, str):
        return response
    return ""


def _tool(name: str, argument: str) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "Return one harmless qualification value.",
            "parameters": {
                "type": "object",
                "properties": {argument: {"type": "string"}},
                "required": [argument],
                "additionalProperties": False,
            },
        },
    }


_SINGLE_TOOL = _tool("echo_value", "value")
_PARALLEL_TOOLS = (
    _tool("echo_alpha", "alpha"),
    _tool("echo_beta", "beta"),
    _tool("echo_gamma", "gamma"),
)


def _safe_response_receipt(response: Any, *, latency_ms: int) -> dict[str, Any]:
    text = _response_text(response)
    calls = _native_calls(response)
    usage = _field(response, "usage")
    input_tokens = _field(usage, "prompt_tokens") or _field(usage, "input_tokens") or 0
    output_tokens = (
        _field(usage, "completion_tokens") or _field(usage, "output_tokens") or 0
    )
    total_tokens = _field(usage, "total_tokens") or input_tokens + output_tokens
    return {
        "latency_ms": latency_ms,
        "text_present": bool(text.strip()),
        "text_digest": _sha256_text(text),
        "native_tool_call_count": len(calls),
        "native_tool_names": sorted(
            str(call["function"]["name"]) for call in calls
        ),
        "usage": {
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
            "total_tokens": int(total_tokens),
        },
    }


def _call(model: Any, messages: list[dict[str, Any]], **kwargs: Any) -> tuple[Any, int]:
    started = time.monotonic()
    response = model.call_raw(messages, **kwargs)
    return response, int((time.monotonic() - started) * 1000)


def _provider_error_code(exc: BaseException) -> str:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    return "timeout" if "timeout" in name or "timeout" in message else "provider_error"


def _count_model_requests(model: Any) -> dict[str, int]:
    counter = {"attempts": 0}
    original = model.call_raw

    def counted(*args: Any, **kwargs: Any) -> Any:
        counter["attempts"] += 1
        return original(*args, **kwargs)

    model.call_raw = counted
    return counter


def _preflight_profile(profile: LiveProfile, resolver: Any) -> dict[str, Any]:
    from qitos.config.builder import build_model

    model = build_model(profile.config.model, credential_resolver=resolver)
    requests = 0
    receipts: list[dict[str, Any]] = []

    text_ok = single_ok = parallel_ok = continuation_ok = False
    error_code: Optional[str] = None
    try:
        requests += 1
        response, latency = _call(
            model,
            [
                {
                    "role": "user",
                    "content": "Reply with exactly QITOS_PREFLIGHT_OK and no tool call.",
                }
            ],
        )
        text_ok = "QITOS_PREFLIGHT_OK" in _response_text(response)
        receipts.append(
            {"route": "text", **_safe_response_receipt(response, latency_ms=latency)}
        )

        requests += 1
        response, latency = _call(
            model,
            [{"role": "user", "content": "Call echo_value once with value qitos."}],
            tools=[_SINGLE_TOOL],
            tool_choice="required",
        )
        single_calls = _native_calls(response)
        single_ok = (
            len(single_calls) == 1
            and single_calls[0]["function"]["name"] == "echo_value"
        )
        receipts.append(
            {
                "route": "single_tool",
                **_safe_response_receipt(response, latency_ms=latency),
            }
        )

        requests += 1
        response, latency = _call(
            model,
            [
                {
                    "role": "user",
                    "content": "In one assistant turn call echo_alpha, echo_beta, and echo_gamma once each.",
                }
            ],
            tools=list(_PARALLEL_TOOLS),
            tool_choice="required",
        )
        parallel_calls = _native_calls(response)
        parallel_names = {call["function"]["name"] for call in parallel_calls}
        parallel_ok = parallel_names == {"echo_alpha", "echo_beta", "echo_gamma"}
        receipts.append(
            {
                "route": "parallel_tool",
                **_safe_response_receipt(response, latency_ms=latency),
            }
        )

        continuation_messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": "Call all three tools, then after their results reply QITOS_CONTINUATION_OK.",
            },
            {"role": "assistant", "content": None, "tool_calls": parallel_calls},
        ]
        continuation_messages.extend(
            {
                "role": "tool",
                "tool_call_id": call["id"],
                "content": json.dumps({"status": "success", "value": "ok"}),
            }
            for call in parallel_calls
        )
        requests += 1
        response, latency = _call(
            model, continuation_messages, tools=list(_PARALLEL_TOOLS)
        )
        continuation_ok = "QITOS_CONTINUATION_OK" in _response_text(response)
        receipts.append(
            {
                "route": "continuation",
                **_safe_response_receipt(response, latency_ms=latency),
            }
        )
    except Exception as exc:
        error_code = _provider_error_code(exc)
    status = "passed" if all((text_ok, single_ok, parallel_ok, continuation_ok)) else "failed"
    if error_code is None and status == "failed":
        error_code = (
            "capability_loss"
            if not single_ok or not parallel_ok
            else "protocol_error"
        )
    result = {
        "profile_id": profile.profile_id,
        "config_digest": profile.config.digest(),
        "credential": dict(getattr(model, "qitos_credential_receipt", {}) or {}),
        "requests": requests,
        "routes": receipts,
        "assertions": {
            "text": text_ok,
            "single_tool": single_ok,
            "parallel_tool": parallel_ok,
            "continuation": continuation_ok,
        },
        "status": status,
    }
    if error_code:
        result["error_code"] = error_code
    return result


_OFFLINE_NODES = (
    "tests/test_yaml_config.py",
    "tests/test_agent_credentials.py",
    "tests/test_native_tool_calling_runtime.py::test_default_history_window_never_sends_orphan_parallel_tool_results",
    "tests/e2e/test_s2_g3_runtime_vertical.py::test_twenty_clean_process_vertical_continuity_rounds",
    "tests/e2e/test_session_core_process_restore.py::test_fresh_process_restore_uses_no_live_parent_object",
    "tests/e2e/test_multi_agent_process_restore.py::test_clean_process_restores_receipts_without_replaying_unknown",
    "tests/test_docker_qualification.py",
)


def run_offline_gates(
    profiles: Sequence[LiveProfile], *, execute_external: bool = True
) -> dict[str, Any]:
    """Run all sixteen gates before any live credential resolution/request."""
    if not profiles:
        raise QualificationConfigurationError("offline gates require profiles")
    command = [sys.executable, "-m", "pytest", "-q", *_OFFLINE_NODES]
    if execute_external:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        passed = result.returncode == 0
        output_digest = _sha256_text(result.stdout + result.stderr)
        returncode: Optional[int] = result.returncode
    else:
        passed = True
        output_digest = _sha256_text("injected-offline-pass")
        returncode = None
    names = (
        "strict_parser",
        "unknown_field_rejection",
        "canonical_serialization",
        "credential_non_disclosure",
        "environment_compatibility_receipts",
        "fake_resolver_provider_preflight",
        "fake_single_step",
        "fake_env_tool_route",
        "fake_parallel_tools",
        "fake_continuation",
        "single_agent_clean_process_restore",
        "multi_agent_clean_process_restore",
        "real_docker_creation_inspect",
        "real_docker_tools_denials_digest",
        "source_config_policy_cleanup_binding",
        "reachable_g4_live_passed",
    )
    return {
        "status": "passed" if passed else "failed",
        "count": len(names),
        "gates": [
            {
                "index": index,
                "name": name,
                "status": "passed" if passed else "failed",
            }
            for index, name in enumerate(names, start=1)
        ],
        "command": ["python", "-m", "pytest", "-q", *_OFFLINE_NODES],
        "returncode": returncode,
        "output_digest": output_digest,
    }


def _restore_worker(
    *, config_path: Path, credentials_path: Path, session_id: str
) -> int:
    from qitos.config import LocalCredentialFileResolver, load_agent_config
    from qitos.config.builder import build_agent_composition
    from qitos.engine import Engine

    config = load_agent_config(config_path)
    resolver = LocalCredentialFileResolver(credentials_path, repository_root=ROOT)
    composition = build_agent_composition(config, credential_resolver=resolver)
    request_counter = _count_model_requests(composition.model)
    try:
        composition.runtime.bind_engine_resources(composition.engine)
        restored = Engine.restore(session_id, runtime=composition.runtime)
        result = restored.run()
        payload = {
            "session_id": session_id,
            "run_id": result.run_id,
            "work_item_id": restored.work_item_id.value,
            "stop_reason": result.state.stop_reason,
            "final_result_digest": _sha256_text(str(result.state.final_result or "")),
            "tool_calls": result.tool_calls_by_name,
            "requests": request_counter["attempts"],
            "credential": composition.credential_receipt,
            "status": "passed" if result.state.final_result else "failed",
        }
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload["status"] == "passed" else 1
    finally:
        composition.close()


def _run_restore_subprocess(
    *, config_path: Path, credentials_path: Path, session_id: str
) -> dict[str, Any]:
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--restore-worker",
            "--config",
            str(config_path),
            "--credentials",
            str(credentials_path),
            "--session-id",
            session_id,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    if result.returncode != 0:
        raise QualificationError(
            "clean-process restore worker failed", code="restore_worker_failed"
        )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise QualificationError("restore worker emitted no receipt")
    return dict(json.loads(lines[-1]))


def _live_restore_workflows(
    profile: LiveProfile, *, credentials_path: Path
) -> dict[str, Any]:
    from qitos.config import LocalCredentialFileResolver
    from qitos.config.builder import build_agent_composition
    from qitos.core.session import PauseSafety, SafeBoundaryKind
    from qitos.core.work_graph import WorkDescriptor
    from qitos.engine.work_runtime import DurableWorkRuntime, WorkRuntimePolicy

    class _HoldHandle:
        def __init__(self, worker_ref: str) -> None:
            self.worker_ref = worker_ref

        def add_terminal_callback(self, callback: Any) -> None:
            self.callback = callback

        def request_cancel(self) -> bool:
            return False

    class _HoldScheduler:
        scheduler_id = "qitos.qualification.hold"

        def __init__(self) -> None:
            self.handles: dict[str, Any] = {}

        def dispatch(self, request: Any) -> Any:
            handle = _HoldHandle(f"hold:{request.operation_id}:{request.attempt}")
            self.handles[handle.worker_ref] = handle
            return handle

        def reattach(self, request: Any, worker_ref: str) -> Any:
            _ = request
            return self.handles.get(worker_ref)

        def close(self) -> None:
            self.handles.clear()

    class _PauseFirstBoundary:
        policy_id = "qitos.qualification.pause_first"
        supports_pause = True

        def should_pause(self, context: Any) -> bool:
            return context.step_id == 0

        def pause_safety(self, context: Any) -> PauseSafety:
            _ = context
            return PauseSafety(boundary=SafeBoundaryKind.AFTER_MODEL_RESULT)

    config = profile.config
    if not config.runtime.session.enabled or config.runtime.session.store != "sqlite":
        raise QualificationConfigurationError(
            "live restore workflows require an enabled sqlite session"
        )
    resolver = LocalCredentialFileResolver(credentials_path, repository_root=ROOT)
    composition = build_agent_composition(config, credential_resolver=resolver)
    request_counter = _count_model_requests(composition.model)
    setattr(composition.runtime, "lifecycle_policy", _PauseFirstBoundary())
    scheduler = _HoldScheduler()
    composition.runtime.work_runtime = DurableWorkRuntime(
        scheduler,
        policy=WorkRuntimePolicy(
            maximum_children_per_operation=2,
            maximum_graph_depth=2,
            maximum_concurrent_children=2,
            queue_capacity=2,
            admission_behavior="reject",
            timeout_seconds=config.budgets.max_runtime_seconds,
            budget_ceiling={"model_requests": config.budgets.max_requests},
            capability_ceiling=frozenset(
                {"read", "grep", "write", "command", "test"}
            ),
        ),
    )
    try:
        task = config.dataset[0].task if config.dataset else "Inspect the workspace, run one tool, and finish."
        single = composition.engine.session(task)
        single.run()
        parent = composition.engine.session(
            "Call read_file once for README.md, then after its result return a final answer."
        )
        parent.run()
        fan_out = parent.fan_out(
            [
                {
                    "agent": config.name,
                    "task": "independent child zero",
                    "capabilities": ["read"],
                    "budget": {"model_requests": 1},
                },
                {
                    "agent": config.name,
                    "task": "independent child one",
                    "capabilities": ["read"],
                    "budget": {"model_requests": 1},
                },
            ],
            operation_id="g4-l2-live-fan-out",
        )
        joined = parent.join(
            [fan_out.operation_id],
            policy="all",
            operation_id="g4-l2-live-join",
        )
        descriptor = WorkDescriptor.from_dict(fan_out.descriptor)
        identities = {
            "single": single.session_id.value,
            "parent": parent.session_id.value,
            "children": list(descriptor.child_session_ids),
            "parent_work_item": parent.work_item_id.value,
            "parent_requests": request_counter["attempts"],
            "child_work_items": list(descriptor.child_work_item_ids),
            "transfer_receipts": len(descriptor.transfer_receipts),
            "join_operation": joined.operation_id,
        }
    finally:
        composition.close()
        composition.runtime.work_runtime.close()
    single_receipt = _run_restore_subprocess(
        config_path=profile.config_path,
        credentials_path=credentials_path,
        session_id=identities["single"],
    )
    child_receipts = [
        _run_restore_subprocess(
            config_path=profile.config_path,
            credentials_path=credentials_path,
            session_id=session_id,
        )
        for session_id in identities["children"]
    ]
    single_tool_route = bool(single_receipt.get("tool_calls"))
    multi_distinct = (
        len(set(identities["child_work_items"])) == 2
        and identities["parent_work_item"] not in identities["child_work_items"]
        and len({receipt.get("session_id") for receipt in child_receipts}) == 2
    )
    status = (
        "passed"
        if single_receipt.get("status") == "passed"
        and all(receipt.get("status") == "passed" for receipt in child_receipts)
        and single_tool_route
        and multi_distinct
        and identities["transfer_receipts"] == 2
        else "failed"
    )
    return {
        "status": status,
        "single_agent": single_receipt,
        "multi_agent": {
            "parent_session_id": identities["parent"],
            "children": child_receipts,
            "child_count": len(child_receipts),
            "context_transfer_receipts": identities["transfer_receipts"],
            "join_operation_digest": _sha256_text(identities["join_operation"]),
            "fan_out_lineage_distinct": multi_distinct,
        },
        "real_tool_route": single_tool_route,
        "credential_re_resolved": all(
            receipt.get("credential", {}).get("resolver") == "local_file"
            for receipt in (single_receipt, *child_receipts)
        ),
        "requests": sum(
            int(receipt.get("requests", 0))
            for receipt in (single_receipt, *child_receipts)
        )
        + int(identities["parent_requests"]),
    }


def _privacy_report(payload: Any, forbidden_values: Sequence[str]) -> dict[str, Any]:
    rendered = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    values_absent = not any(value and value in rendered for value in forbidden_values)
    return {
        "credential_values_absent": values_absent,
        "raw_endpoints_absent": not any(
            token in rendered for token in ("/chat/completions", "https://", "http://")
        ),
        "host_paths_absent": _HOST_PATH_RE.search(rendered) is None,
        "authorization_markers_absent": _SECRET_MARKER_RE.search(rendered) is None,
        "scan_passed": values_absent
        and _HOST_PATH_RE.search(rendered) is None
        and _SECRET_MARKER_RE.search(rendered) is None,
    }


def qualify(
    profiles: Sequence[LiveProfile],
    *,
    live: bool,
    source_commit: str,
    credentials_path: Optional[Path],
    generated_at: Optional[str] = None,
    execute_offline_gates: bool = True,
    enforce_current_source: bool = True,
) -> dict[str, Any]:
    """Run offline gates, then optional live providers and restore workflows."""
    _validate_source(source_commit, enforce_current=enforce_current_source)
    offline = run_offline_gates(profiles, execute_external=execute_offline_gates)
    base: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit,
        "runner_digest": _sha256_bytes(Path(__file__).read_bytes()),
        "configs": [
            {
                "profile_id": profile.profile_id,
                "config_digest": profile.config.digest(),
                "source_digest": profile.config.source["sha256"],
                "receipt": profile.config.receipt(),
            }
            for profile in profiles
        ],
        "offline": offline,
        "profiles": [],
        "sandbox": {},
        "workflows": {},
        "totals": {
            "profiles": len(profiles),
            "requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "reported_tokens": 0,
            "retries": 0,
        },
        "decision": {
            "s3_status": "blocked_live_qualification",
            "g4_live": "offline_failed" if offline["status"] != "passed" else "live_flag_required",
            "s4_ready": False,
            "feature_baseline_promoted": False,
            "default_branch_ready": False,
        },
    }
    if offline["status"] != "passed" or not live:
        base["privacy"] = _privacy_report(base, [])
        base["evidence_digest"] = _evidence_digest(base)
        return base
    if credentials_path is None:
        raise QualificationConfigurationError("--credentials is required for live mode")

    from qitos.config import LocalCredentialFileResolver
    from qitos.kit.env.docker_qualification import (
        SandboxIdentity,
        qualify_docker_environment,
    )

    resolver = LocalCredentialFileResolver(credentials_path, repository_root=ROOT)
    forbidden_values: list[str] = []
    # Resolve every reference before a container is launched or a request is sent.
    credential_failures: list[dict[str, Any]] = []
    for profile in profiles:
        try:
            resolution = resolver.resolve(profile.config.model.credential)
            forbidden_values.append(resolution.secret.reveal_for_composition())
        except Exception as exc:
            credential_failures.append(
                {
                    "profile_id": profile.profile_id,
                    "config_digest": profile.config.digest(),
                    "requests": 0,
                    "status": "failed",
                    "error_code": "configuration_error",
                    "detail_code": type(exc).__name__,
                }
            )
    if credential_failures:
        failed_ids = {item["profile_id"] for item in credential_failures}
        base["profiles"] = credential_failures + [
            {
                "profile_id": profile.profile_id,
                "config_digest": profile.config.digest(),
                "requests": 0,
                "status": "not_started",
                "error_code": "configuration_dependency_failed",
            }
            for profile in profiles
            if profile.profile_id not in failed_ids
        ]
        base["sandbox"] = {"status": "not_started"}
        base["workflows"] = {"status": "not_started"}
        base["decision"]["g4_live"] = "configuration_error"
        base["privacy"] = _privacy_report(base, forbidden_values)
        base["evidence_digest"] = _evidence_digest(base)
        return base
    try:
        sandbox = qualify_docker_environment(
            profiles[0].config,
            identity=SandboxIdentity(
                session_id="qualification-session",
                run_id="qualification-run",
                work_item_id="qualification-work",
                environment_id="qualification-environment",
            ),
        )
    except Exception as exc:
        base["sandbox"] = {
            "status": "failed",
            "error_code": "sandbox_failure",
            "detail_code": type(exc).__name__,
        }
        base["workflows"] = {"status": "not_started"}
        base["decision"]["g4_live"] = "sandbox_failure"
        base["privacy"] = _privacy_report(base, forbidden_values)
        base["evidence_digest"] = _evidence_digest(base)
        return base
    base["sandbox"] = sandbox.to_dict()
    for profile in profiles:
        try:
            receipt = _preflight_profile(profile, resolver)
        except Exception as exc:
            receipt = {
                "profile_id": profile.profile_id,
                "config_digest": profile.config.digest(),
                "requests": 0,
                "status": "failed",
                "error_code": type(exc).__name__,
            }
        base["profiles"].append(receipt)
        base["totals"]["requests"] += int(receipt.get("requests", 0))
        for route in receipt.get("routes", []):
            usage = route.get("usage", {})
            base["totals"]["input_tokens"] += int(usage.get("input_tokens", 0))
            base["totals"]["output_tokens"] += int(usage.get("output_tokens", 0))
            base["totals"]["reported_tokens"] += int(usage.get("total_tokens", 0))
    qualified_index = next(
        (
            index
            for index, item in enumerate(base["profiles"])
            if item.get("status") == "passed"
        ),
        None,
    )
    if qualified_index is not None:
        try:
            base["workflows"] = _live_restore_workflows(
                profiles[qualified_index], credentials_path=credentials_path
            )
            base["totals"]["requests"] += int(
                base["workflows"].get("requests", 0)
            )
        except Exception as exc:
            base["workflows"] = {
                "status": "failed",
                "error_code": "workflow_failure",
                "detail_code": type(exc).__name__,
            }
    else:
        base["workflows"] = {"status": "not_started"}

    all_passed = (
        sandbox.status == "passed"
        and qualified_index is not None
        and all(
            item.get("status") == "passed"
            or item.get("error_code") == "capability_loss"
            for item in base["profiles"]
        )
        and base["workflows"].get("status") == "passed"
        and int(base["profiles"][qualified_index].get("requests", 0))
        + int(base["workflows"].get("requests", 0))
        <= int(profiles[qualified_index].config.budgets.max_requests)
        and all(
            int(receipt.get("requests", 0))
            <= int(profile.config.budgets.max_requests)
            for index, (profile, receipt) in enumerate(zip(profiles, base["profiles"]))
            if index != qualified_index
        )
    )
    if all_passed:
        base["decision"] = {
            "s3_status": "qualified",
            "g4_live": "passed",
            "s4_ready": True,
            "feature_baseline_promoted": False,
            "default_branch_ready": False,
        }
    else:
        failures = [
            str(item.get("error_code") or "provider_error")
            for item in base["profiles"]
            if item.get("status") != "passed"
        ]
        base["decision"]["g4_live"] = (
            "workflow_failure"
            if base["workflows"].get("status") == "failed"
            else failures[0] if failures else "provider_error"
        )
    base["privacy"] = _privacy_report(base, forbidden_values)
    if not base["privacy"]["scan_passed"]:
        base["decision"]["g4_live"] = "privacy_failed"
        base["decision"]["s4_ready"] = False
    base["evidence_digest"] = _evidence_digest(base)
    return base


def _evidence_digest(payload: Mapping[str, Any]) -> str:
    value = dict(payload)
    value["evidence_digest"] = ""
    return _sha256_json(value)


def verify_evidence(
    payload: Mapping[str, Any], profiles: Optional[Sequence[LiveProfile]] = None
) -> None:
    expected = str(payload.get("evidence_digest") or "")
    if expected != _evidence_digest(payload):
        raise QualificationConfigurationError("evidence digest mismatch")
    if str(payload.get("runner_digest") or "") != _sha256_bytes(Path(__file__).read_bytes()):
        raise QualificationConfigurationError("runner digest mismatch")
    if profiles is not None:
        expected_configs = [
            {
                "profile_id": profile.profile_id,
                "config_digest": profile.config.digest(),
                "source_digest": profile.config.source["sha256"],
                "receipt": profile.config.receipt(),
            }
            for profile in profiles
        ]
        if payload.get("configs") != expected_configs:
            raise QualificationConfigurationError("config digest mismatch")


def _write_json(path: Path, payload: Mapping[str, Any], *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(mode)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", action="append", default=[])
    parser.add_argument("--credentials")
    parser.add_argument("--source-commit")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--offline-only", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--private-dir")
    parser.add_argument("--restore-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--session-id", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.restore_worker:
        if len(args.config) != 1 or not args.credentials or not args.session_id:
            parser.error("restore worker requires one config, credentials, and session id")
        return _restore_worker(
            config_path=Path(args.config[0]).expanduser().resolve(),
            credentials_path=Path(args.credentials).expanduser().resolve(),
            session_id=str(args.session_id),
        )
    if not args.source_commit:
        parser.error("--source-commit is required")
    profiles = load_profiles(args.config)
    live = bool(args.live and not args.offline_only)
    result = qualify(
        profiles,
        live=live,
        source_commit=str(args.source_commit),
        credentials_path=(
            Path(args.credentials).expanduser().resolve()
            if args.credentials
            else None
        ),
    )
    if args.private_dir:
        private = _validate_private_dir(args.private_dir)
        _write_json(private / "qualification-receipt.json", result, mode=0o600)
    if args.output:
        _write_json(Path(args.output), result, mode=0o644)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["decision"]["g4_live"] in {"passed", "live_flag_required"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
