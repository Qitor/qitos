#!/usr/bin/env python3
"""Qualify canonical AgentConfig launches with offline and bounded live gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCHEMA_VERSION = "qitos.s3.g4_l3_qualification/v1"
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


class _PauseFirstSuccessfulBoundary:
    """Pause once per Session after its first completed model/tool boundary."""

    policy_id = "qitos.qualification.pause_first_successful"
    supports_pause = True

    def __init__(self) -> None:
        self._paused_sessions: set[str] = set()

    @staticmethod
    def _session_key(context: Any) -> str:
        handle = getattr(context.engine, "_session_handle", None)
        identity = getattr(handle, "session_id", None)
        value = getattr(identity, "value", None)
        return str(value) if value else f"engine:{id(context.engine)}"

    def should_pause(self, context: Any) -> bool:
        return self._session_key(context) not in self._paused_sessions

    def pause_safety(self, context: Any) -> Any:
        from qitos.core.session import PauseSafety, SafeBoundaryKind

        self._paused_sessions.add(self._session_key(context))
        return PauseSafety(boundary=SafeBoundaryKind.AFTER_MODEL_RESULT)


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


def _count_model_requests(
    model: Any, *, max_attempts: Optional[int] = None
) -> dict[str, int]:
    counter = {"attempts": 0}
    original = model.call_raw

    def counted(*args: Any, **kwargs: Any) -> Any:
        if max_attempts is not None and counter["attempts"] >= max_attempts:
            raise QualificationError(
                "model request budget exhausted",
                code="request_budget_exhausted",
            )
        counter["attempts"] += 1
        return original(*args, **kwargs)

    model.call_raw = counted
    return counter


def _engine_result_error_code(result: Any) -> Optional[str]:
    """Project a safe typed cause from an unsuccessful Engine result."""
    if result.error_code:
        return str(result.error_code)
    stop_reason = str(result.state.stop_reason or "")
    return {
        "budget_steps": "engine_step_budget_exhausted",
        "budget_time": "engine_time_budget_exhausted",
        "budget_cost": "engine_cost_budget_exhausted",
    }.get(stop_reason)


def _exception_error_code(error: BaseException, fallback: str) -> str:
    """Project one non-echoing typed code from framework or runner errors."""
    for attribute in ("error_code", "code"):
        candidate = getattr(error, attribute, None)
        candidate = getattr(candidate, "value", candidate)
        if isinstance(candidate, str) and candidate:
            return candidate
    return fallback


_INFORMATIONAL_EXTERNAL_CODES = frozenset(
    {
        "provider_connection_failed",
        "provider_timeout",
        "provider_authentication_failed",
        "provider_rate_limited",
        "provider_request_rejected",
        "provider_server_error",
        "provider_request_cancelled",
    }
)
_INFORMATIONAL_FRAMEWORK_CODES = frozenset(
    {
        "codec_encode_failed",
        "codec_transport_options_invalid",
        "request_projection_failed",
        "provider_response_decode_failed",
        "provider_response_malformed",
    }
)


def _informational_outcome(
    root_code: Optional[str], *, framework_invariant_failure: bool
) -> str:
    """Keep a typed root cause while separating capability from conformance."""
    if framework_invariant_failure:
        return "framework_invariant_failure"
    if root_code == "model_request_budget_exhausted":
        return "model_budget_exhausted"
    if root_code in _INFORMATIONAL_EXTERNAL_CODES:
        return "provider_unavailable"
    if root_code:
        return "typed_failure"
    return "passed"


def _preflight_profile(profile: LiveProfile, resolver: Any) -> dict[str, Any]:
    """Run the provider probe through the canonical composition and Engine."""
    from qitos.config.builder import build_agent_composition

    composition = build_agent_composition(
        profile.config, credential_resolver=resolver
    )
    counter = _count_model_requests(
        composition.model,
        max_attempts=int(profile.config.budgets.max_requests),
    )
    try:
        task = (
            profile.config.dataset[0].task
            if profile.config.dataset
            else "Use one declared tool, then return a verified final answer."
        )
        result = composition.engine.run(task)
        tool_route = bool(result.tool_calls_by_name)
        capability_loss = any(
            event.payload.get("code") == "provider_capability_loss"
            for event in result.events
        )
        provider_categories = {
            str(event.payload.get("provider_failure", {}).get("category") or "")
            for event in result.events
            if event.payload.get("stage") == "provider_failure"
        }
        status = "passed" if result.state.final_result and tool_route else "failed"
        error_code = None
        if status == "failed":
            error_code = (
                _engine_result_error_code(result)
                or "provider_capability_loss"
                if capability_loss
                else "timeout"
                if "timeout" in provider_categories
                else _engine_result_error_code(result) or "engine_workflow_failed"
            )
        receipt = {
            "profile_id": profile.profile_id,
            "config_digest": profile.config.digest(),
            "credential": composition.credential_receipt,
            "requests": counter["attempts"],
            "engine": {
                "run_id": result.run_id,
                "stop_reason": str(result.state.stop_reason or ""),
                "final_present": bool(result.state.final_result),
                "tool_calls": result.tool_calls_by_name,
                "native_tool_route": tool_route,
            },
            "status": status,
            "root_error_code": result.error_code,
            "lifecycle_consequence": (
                "failed" if result.state.stop_reason == "unrecoverable_error" else "completed"
            ),
            "provider_request_sent": counter["attempts"] > 0,
        }
        if error_code:
            receipt["error_code"] = error_code
        return receipt
    except Exception as exc:
        return {
            "profile_id": profile.profile_id,
            "config_digest": profile.config.digest(),
            "credential": composition.credential_receipt,
            "requests": counter["attempts"],
            "status": "failed",
            "error_code": _exception_error_code(exc, type(exc).__name__),
        }
    finally:
        composition.close()


def _informational_smoke_profile(
    profile: LiveProfile,
    resolver: Any,
) -> dict[str, Any]:
    """Run one bounded Session as capability evidence, not a release oracle."""

    from qitos.config.builder import build_agent_composition
    from qitos.qita.reader import candidate_file_reader, load_session_payload
    from qitos.tracing.trajectory import PrivacyView

    maximum = int(profile.config.budgets.max_requests)
    if maximum < 1 or maximum > 3:
        raise QualificationConfigurationError(
            "informational smoke requires a one-to-three request config budget"
        )
    composition = build_agent_composition(
        profile.config,
        credential_resolver=resolver,
    )
    counter = _count_model_requests(composition.model, max_attempts=maximum)
    task = (
        profile.config.dataset[0].task
        if profile.config.dataset
        else "Inspect the declared workspace with a native tool and report one fact."
    )
    sentinel_text = "qitos-session-isolation-sentinel"
    session = None
    result = None
    run_error: Optional[BaseException] = None
    inspection = None
    cleanup_passed = False
    try:
        composition.engine.session(sentinel_text)
        session = composition.engine.session(task)
        try:
            result = session.run()
        except Exception as exc:
            # A typed provider failure can escape after the Session has already
            # committed its terminal snapshot.  Preserve that exact code and
            # continue the durable accounting/trajectory/privacy audit.
            run_error = exc
        inspection = session.inspect()
    finally:
        try:
            composition.close()
        finally:
            cleanup_passed = (
                composition.sandbox_receipt.get("cleanup") == "passed"
            )

    assert session is not None and inspection is not None
    request_view = inspection.last_request_view
    request_view_json = (
        json.dumps(
            request_view.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
        )
        if request_view is not None
        else ""
    )
    session_isolated = bool(request_view_json) and sentinel_text not in request_view_json
    native_request_expressed = bool(
        request_view is not None and request_view.tool_schemas
    )
    durable_requests = int(
        inspection.budget.get("model_requests_consumed", 0)
    )
    request_accounting_exact = durable_requests == counter["attempts"]
    trajectory_readable = False
    qita_readable = False
    try:
        reader = candidate_file_reader(_trajectory_path(profile.config))
        trajectory = reader.read_session(
            session.session_id.value,
            view=PrivacyView.RAW_PRIVATE,
        )
        qita = load_session_payload(reader, session.session_id.value)
        trajectory_readable = bool(trajectory.records)
        qita_readable = (
            qita.get("trajectory_meta", {}).get("session_id")
            == session.session_id.value
        )
    except (FileNotFoundError, ValueError, KeyError):
        pass

    root_code = (
        _engine_result_error_code(result)
        if result is not None
        else _exception_error_code(run_error, "informational_smoke_runtime_failed")
    )
    framework_invariant_failure = (
        not session_isolated
        or not request_accounting_exact
        or durable_requests > maximum
        or not trajectory_readable
        or not qita_readable
        or not cleanup_passed
        or root_code in _INFORMATIONAL_FRAMEWORK_CODES
        or (
            result is None
            and root_code not in _INFORMATIONAL_EXTERNAL_CODES
            and root_code != "model_request_budget_exhausted"
        )
    )
    outcome = _informational_outcome(
        root_code,
        framework_invariant_failure=framework_invariant_failure,
    )
    if outcome == "passed" and not (
        counter["attempts"] and native_request_expressed
    ):
        outcome = "typed_failure"
    return {
        "profile_id": profile.profile_id,
        "role": "informational_smoke",
        "config_digest": profile.config.digest(),
        "status": outcome,
        "requests": counter["attempts"],
        "durable_requests": durable_requests,
        "request_limit": maximum,
        "request_accounting_exact": request_accounting_exact,
        "provider_request_sent": counter["attempts"] > 0,
        "root_error_code": root_code,
        "lifecycle_consequence": session.lifecycle.value,
        "session_isolated": session_isolated,
        "request_view_digest": (
            _sha256_text(request_view_json) if request_view_json else None
        ),
        "native_tool_request_expressed": native_request_expressed,
        "native_tool_calls": (
            dict(result.tool_calls_by_name) if result is not None else {}
        ),
        "trajectory_readable": trajectory_readable,
        "qita_session_readable": qita_readable,
        "sandbox_cleanup": cleanup_passed,
        "framework_invariant_failure": framework_invariant_failure,
        "credential": composition.credential_receipt,
    }


_OFFLINE_NODES = (
    "tests/test_yaml_config.py",
    "tests/test_agent_credentials.py",
    "tests/test_config_security.py",
    "tests/test_native_tool_calling_runtime.py",
    "tests/test_config_trajectory_integration.py",
    "tests/test_sandbox_backend_contract.py",
    "tests/engine/test_session_runtime.py",
    "tests/engine/test_work_runtime.py",
    "tests/checkpoint",
    "tests/tracing",
    "tests/test_qita_cli.py",
    "tests/test_no_local_paths.py",
    "tests/e2e/test_session_core_process_restore.py::test_fresh_process_restore_uses_no_live_parent_object",
    "tests/e2e/test_s3_g4_configured_process_recovery.py",
    "tests/e2e/test_s3_g4_multi_agent_process_loss.py",
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
        "canonical_config_and_unknown_field_rejection",
        "compatibility_reader_canonical_writer",
        "deep_immutability_and_digest",
        "credential_permissions_and_non_disclosure",
        "protocol_parser_codec_convergence",
        "native_tool_and_malformed_response_diagnostics",
        "tool_use_policy_enforcement",
        "configured_single_agent_trajectory",
        "configured_multi_agent_trajectory",
        "sandbox_structural_conformance",
        "docker_inspect_attestation",
        "single_agent_clean_process_restore",
        "multi_agent_clean_process_restore",
        "stale_owner_corrupt_snapshot_and_partial_batch",
        "qita_graph_timeline_and_replay",
        "privacy_path_and_cleanup_failures",
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
    *,
    config_path: Path,
    credentials_path: Path,
    session_id: str,
    max_requests: int,
) -> int:
    from qitos.config import LocalCredentialFileResolver, load_agent_config
    from qitos.config.builder import build_agent_composition
    from qitos.engine import Engine

    config = load_agent_config(config_path)
    resolver = LocalCredentialFileResolver(credentials_path, repository_root=ROOT)
    composition = build_agent_composition(config, credential_resolver=resolver)
    request_counter = _count_model_requests(
        composition.model, max_attempts=max_requests
    )
    payload: dict[str, Any]
    try:
        composition.runtime.bind_engine_resources(composition.engine)
        try:
            restored = Engine.restore(session_id, runtime=composition.runtime)
            result = restored.run()
            lifecycle = restored.lifecycle.value
            passed = bool(result.state.final_result) and lifecycle == "completed"
            payload = {
                "session_id": session_id,
                "run_id": result.run_id,
                "work_item_id": restored.work_item_id.value,
                "stop_reason": result.state.stop_reason,
                "final_result_digest": _sha256_text(
                    str(result.state.final_result or "")
                ),
                "tool_calls": result.tool_calls_by_name,
                "requests": request_counter["attempts"],
                "credential": composition.credential_receipt,
                "status": "passed" if passed else "failed",
                "root_error_code": _engine_result_error_code(result),
                "error_code": (
                    None
                    if passed
                    else _engine_result_error_code(result)
                    or "restore_workflow_failed"
                ),
                "lifecycle_consequence": lifecycle,
                "pause_reached": lifecycle == "paused",
                "provider_request_sent": request_counter["attempts"] > 0,
            }
        except Exception as exc:
            payload = {
                "session_id": session_id,
                "requests": request_counter["attempts"],
                "credential": composition.credential_receipt,
                "status": "failed",
                "error_code": _exception_error_code(exc, type(exc).__name__),
                "root_error_code": _exception_error_code(
                    exc, type(exc).__name__
                ),
                "lifecycle_consequence": "failed",
                "pause_reached": False,
                "provider_request_sent": request_counter["attempts"] > 0,
            }
    finally:
        try:
            composition.close()
        except Exception as exc:
            payload = {
                **payload,
                "status": "failed",
                "error_code": _exception_error_code(
                    exc, "sandbox_cleanup_failed"
                ),
            }
    payload["sandbox"] = dict(composition.sandbox_receipt)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["status"] == "passed" else 1


def _run_restore_subprocess(
    *,
    config_path: Path,
    credentials_path: Path,
    session_id: str,
    max_requests: int,
) -> dict[str, Any]:
    try:
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
                "--max-requests",
                str(max_requests),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "session_id": session_id,
            "status": "failed",
            "error_code": "restore_worker_timeout",
            "requests": max_requests,
            "request_count_exact": False,
            "request_attempt_upper_bound": max_requests,
        }
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return {
            "session_id": session_id,
            "status": "failed",
            "error_code": "restore_worker_no_receipt",
            "requests": max_requests,
            "request_count_exact": False,
            "request_attempt_upper_bound": max_requests,
        }
    try:
        receipt = dict(json.loads(lines[-1]))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {
            "session_id": session_id,
            "status": "failed",
            "error_code": "restore_worker_invalid_receipt",
            "requests": max_requests,
            "request_count_exact": False,
            "request_attempt_upper_bound": max_requests,
        }
    if result.returncode != 0 and receipt.get("status") != "failed":
        return {
            "session_id": session_id,
            "status": "failed",
            "error_code": "restore_worker_failed",
            "requests": max_requests,
            "request_count_exact": False,
            "request_attempt_upper_bound": max_requests,
        }
    receipt["request_count_exact"] = True
    return receipt


def _live_restore_workflows(
    profile: LiveProfile,
    *,
    credentials_path: Path,
    request_limit: Optional[int] = None,
) -> dict[str, Any]:
    from qitos.config import LocalCredentialFileResolver
    from qitos.config.builder import build_agent_composition
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

    config = profile.config
    if not config.runtime.session.enabled or config.runtime.session.store != "sqlite":
        raise QualificationConfigurationError(
            "live restore workflows require an enabled sqlite session"
        )
    resolver = LocalCredentialFileResolver(credentials_path, repository_root=ROOT)
    composition = build_agent_composition(config, credential_resolver=resolver)
    request_limit = (
        int(request_limit)
        if request_limit is not None
        else int(config.budgets.max_requests)
    )
    if request_limit < 1:
        raise QualificationError(
            "no model request budget remains", code="request_budget_exhausted"
        )
    request_counter = _count_model_requests(
        composition.model, max_attempts=request_limit
    )
    setattr(
        composition.runtime,
        "lifecycle_policy",
        _PauseFirstSuccessfulBoundary(),
    )
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
    identities: dict[str, Any] = {}
    setup_error: Optional[Exception] = None
    root_error_code: Optional[str] = None
    lifecycle_consequence = "created"
    pause_reached = False
    try:
        task = config.dataset[0].task if config.dataset else "Inspect the workspace, run one tool, and finish."
        single = composition.engine.session(task)
        single_first = single.run()
        lifecycle_consequence = single.lifecycle.value
        root_error_code = single_first.error_code
        pause_reached = single.lifecycle.value == "paused"
        if single.lifecycle.value != "paused":
            raise QualificationError(
                "single-agent session did not reach a restorable pause",
                code=single_first.error_code or "workflow_single_not_paused",
            )
        parent = composition.engine.session(
            "Call read_file once for README.md, then after its result return a final answer."
        )
        parent_first = parent.run()
        if parent.lifecycle.value != "paused":
            root_error_code = parent_first.error_code
            lifecycle_consequence = parent.lifecycle.value
            raise QualificationError(
                "parent session did not reach a dispatch-safe pause",
                code=parent_first.error_code or "workflow_parent_not_paused",
            )
        operation_scope = parent.session_id.value
        fan_out = parent.fan_out(
            [
                {
                    "agent": config.name,
                    "task": "Call read_file once for README.md, then return a concise final answer.",
                    "capabilities": ["read"],
                    "budget": {"model_requests": 2},
                },
                {
                    "agent": config.name,
                    "task": "Call read_file once for README.md, then return a concise final answer.",
                    "capabilities": ["read"],
                    "budget": {"model_requests": 2},
                },
            ],
            operation_id=f"g4-l3-live-fan-out:{operation_scope}",
        )
        joined = parent.join(
            [fan_out.operation_id],
            policy="all",
            operation_id=f"g4-l3-live-join:{operation_scope}",
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
            "initial_single_tool_calls": single_first.tool_calls_by_name,
            "initial_parent_tool_calls": parent_first.tool_calls_by_name,
            "sandbox": dict(composition.sandbox_receipt),
        }
    except Exception as exc:
        setup_error = exc
    finally:
        try:
            composition.close()
        except Exception as exc:
            setup_error = setup_error or exc
        if identities:
            identities["sandbox"] = dict(composition.sandbox_receipt)
        try:
            composition.runtime.work_runtime.close()
        except Exception as exc:
            setup_error = setup_error or exc
    if setup_error is not None:
        setup_code = _exception_error_code(
            setup_error, type(setup_error).__name__
        )
        return {
            "status": "failed",
            "error_code": setup_code,
            "root_error_code": root_error_code or setup_code,
            "lifecycle_consequence": lifecycle_consequence,
            "pause_reached": pause_reached,
            "provider_request_sent": request_counter["attempts"] > 0,
            "requests": request_counter["attempts"],
            "sandbox_cleanup": (
                composition.sandbox_receipt.get("cleanup") == "passed"
            ),
        }
    remaining = request_limit - int(identities["parent_requests"])
    if remaining < 1:
        single_receipt = {
            "session_id": identities["single"],
            "status": "failed",
            "error_code": "request_budget_exhausted",
            "requests": 0,
        }
    else:
        single_receipt = _run_restore_subprocess(
            config_path=profile.config_path,
            credentials_path=credentials_path,
            session_id=identities["single"],
            max_requests=remaining,
        )
    consumed = int(identities["parent_requests"]) + int(
        single_receipt.get("requests", 0)
    )
    child_receipts: list[dict[str, Any]] = []
    if single_receipt.get("status") == "passed":
        for session_id in identities["children"]:
            remaining = request_limit - consumed
            if remaining < 1:
                break
            receipt = _run_restore_subprocess(
                config_path=profile.config_path,
                credentials_path=credentials_path,
                session_id=session_id,
                max_requests=remaining,
            )
            child_receipts.append(receipt)
            consumed += int(receipt.get("requests", 0))
            if receipt.get("status") != "passed":
                break
    join_receipt = (
        _close_live_parent_join(
            profile,
            credentials_path=credentials_path,
            parent_session_id=str(identities["parent"]),
            child_receipts=child_receipts,
        )
        if len(child_receipts) == 2
        and all(receipt.get("status") == "passed" for receipt in child_receipts)
        else {"status": "not_started", "sandbox_cleanup": False}
    )
    single_tool_route = bool(
        identities["initial_single_tool_calls"]
        or single_receipt.get("tool_calls")
    )
    multi_distinct = (
        len(child_receipts) == 2
        and len(set(identities["child_work_items"])) == 2
        and identities["parent_work_item"] not in identities["child_work_items"]
        and len({receipt.get("session_id") for receipt in child_receipts}) == 2
    )
    try:
        artifact_receipt = _verify_live_artifacts(
            profile,
            session_id=str(identities["single"]),
            parent_session_id=str(identities["parent"]),
        )
    except Exception as exc:
        artifact_receipt = {
            "status": "failed",
            "error_code": _exception_error_code(exc, type(exc).__name__),
        }
    cleanup_passed = (
        identities["sandbox"].get("cleanup") in {"passed", "not_applicable"}
        and all(
            receipt.get("sandbox", {}).get("cleanup") == "passed"
            for receipt in (single_receipt, *child_receipts)
        )
    )
    status = (
        "passed"
        if single_receipt.get("status") == "passed"
        and all(receipt.get("status") == "passed" for receipt in child_receipts)
        and single_tool_route
        and multi_distinct
        and identities["transfer_receipts"] == 2
        and join_receipt["status"] == "passed"
        and artifact_receipt["status"] == "passed"
        and cleanup_passed
        else "failed"
    )
    failure_codes = [
        single_receipt.get("root_error_code")
        or single_receipt.get("error_code"),
        *(receipt.get("root_error_code") or receipt.get("error_code")
          for receipt in child_receipts),
        join_receipt.get("error_code"),
        artifact_receipt.get("error_code"),
    ]
    root_error_code = next((str(code) for code in failure_codes if code), None)
    return {
        "status": status,
        "error_code": None if status == "passed" else root_error_code or "workflow_failed",
        "single_agent": single_receipt,
        "multi_agent": {
            "parent_session_id": identities["parent"],
            "children": child_receipts,
            "child_count": len(child_receipts),
            "context_transfer_receipts": identities["transfer_receipts"],
            "join_operation_digest": _sha256_text(identities["join_operation"]),
            "fan_out_lineage_distinct": multi_distinct,
            "join": join_receipt,
        },
        "artifacts": artifact_receipt,
        "sandbox_cleanup": cleanup_passed,
        "real_tool_route": single_tool_route,
        "credential_re_resolved": all(
            receipt.get("credential", {}).get("resolver") == "local_file"
            for receipt in (single_receipt, *child_receipts)
        ),
        "requests": consumed,
        "root_error_code": None if status == "passed" else root_error_code,
        "lifecycle_consequence": "completed",
        "pause_reached": True,
        "provider_request_sent": consumed > 0,
    }


def _close_live_parent_join(
    profile: LiveProfile,
    *,
    credentials_path: Path,
    parent_session_id: str,
    child_receipts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Reconcile actual child results into a fresh-process durable join."""
    from qitos.config import LocalCredentialFileResolver
    from qitos.config.builder import build_agent_composition
    from qitos.core.session import WorkItemIdentity
    from qitos.core.tool_result import ToolResult
    from qitos.engine import Engine

    resolver = LocalCredentialFileResolver(credentials_path, repository_root=ROOT)
    composition = build_agent_composition(
        profile.config, credential_resolver=resolver
    )
    payload: dict[str, Any]
    try:
        composition.runtime.bind_engine_resources(composition.engine)
        parent = Engine.restore(parent_session_id, runtime=composition.runtime)
        graph = parent._engine._qitos_work_graph
        child_ids = [
            WorkItemIdentity(str(receipt["work_item_id"]))
            for receipt in child_receipts
        ]
        join = next(
            item
            for item in graph.joins
            if set(item.child_work_item_ids) == set(child_ids)
        )
        dispositions: list[str] = []
        for index, (child_id, receipt) in enumerate(
            zip(child_ids, child_receipts, strict=True)
        ):
            child = graph.work_items[child_id]
            outcome = ToolResult(
                output={
                    "status": "passed",
                    "final_result_digest": str(
                        receipt.get("final_result_digest") or ""
                    ),
                }
            )
            disposition = graph.record_completion(
                completion_id=f"g4-l3-live-child-{index}",
                work_item_id=child_id,
                owner_generation=child.owner.generation,
                outcome=outcome,
            )
            dispositions.append(disposition)
            graph.accept_join_result(join.join_id, child_id)
        generation = next(
            item.generation for item in graph.joins if item.join_id == join.join_id
        )
        duplicate = graph.record_completion(
            completion_id="g4-l3-live-child-duplicate",
            work_item_id=child_ids[0],
            owner_generation=graph.work_items[child_ids[0]].owner.generation,
            outcome=ToolResult(
                output={
                    "status": "passed",
                    "final_result_digest": str(
                        child_receipts[0].get("final_result_digest") or ""
                    ),
                }
            ),
        )
        graph.accept_join_result(join.join_id, child_ids[0])
        closed = next(
            item for item in graph.joins if item.join_id == join.join_id
        )
        parent._commit_work_graph()
        payload = {
            "status": (
                "passed"
                if dispositions == ["committed", "committed"]
                and duplicate == "duplicate_ignored"
                and closed.state == "closed"
                and closed.generation == generation == 2
                else "failed"
            ),
            "completion_dispositions": dispositions,
            "duplicate_disposition": duplicate,
            "state": closed.state,
            "generation": closed.generation,
            "terminal_receipt_digest": _sha256_text(
                str(closed.terminal_receipt_ref or "")
            ),
        }
    except Exception as exc:
        payload = {
            "status": "failed",
            "error_code": _exception_error_code(exc, type(exc).__name__),
        }
    finally:
        try:
            composition.close()
        except Exception as exc:
            payload = {
                **payload,
                "status": "failed",
                "error_code": _exception_error_code(
                    exc, "sandbox_cleanup_failed"
                ),
            }
    payload["sandbox_cleanup"] = (
        composition.sandbox_receipt.get("cleanup") == "passed"
    )
    if not payload["sandbox_cleanup"]:
        payload["status"] = "failed"
    return payload


def _trajectory_path(config: Any) -> Path:
    output = Path(config.runtime.trajectory.output).expanduser().resolve()
    return output if output.suffix == ".json" else output / "trajectory.json"


def _prepare_coding_fixture(profile: LiveProfile) -> dict[str, Any]:
    """Restore only the explicitly disposable qualification fixture."""
    workspace = Path(
        profile.config.runtime.environment.workspace
    ).expanduser().resolve()
    marker = workspace / "README.md"
    if (
        workspace.name != "disposable-agent"
        or not marker.is_file()
        or "Disposable qualification fixture"
        not in marker.read_text(encoding="utf-8")
    ):
        raise QualificationConfigurationError(
            "coding qualification workspace is not the declared disposable fixture"
        )
    restore = subprocess.run(
        [
            "git",
            "restore",
            "--worktree",
            "--",
            "calculator.py",
            "tests/test_calculator.py",
            "README.md",
        ],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if restore.returncode != 0:
        raise QualificationConfigurationError(
            "disposable coding fixture could not be restored"
        )
    baseline = subprocess.run(
        ["git", "diff", "--", "calculator.py", "tests/test_calculator.py"],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if baseline.returncode != 0 or baseline.stdout.strip():
        raise QualificationConfigurationError(
            "disposable coding fixture did not return to its clean baseline"
        )
    return {
        "status": "prepared",
        "baseline_digest": _sha256_text(
            (workspace / "calculator.py").read_text(encoding="utf-8")
        ),
    }


def _verify_live_artifacts(
    profile: LiveProfile,
    *,
    session_id: str,
    parent_session_id: str,
) -> dict[str, Any]:
    """Verify source/tests and reopen only canonical trajectory bytes."""
    from qitos.config.builder import build_environment
    from qitos.qita.reader import candidate_file_reader, load_session_payload
    from qitos.tracing.trajectory import PrivacyView
    from qitos.tracing.work_graph_reader import GraphSelector, WorkGraphReader

    env = build_environment(profile.config)
    container = str(getattr(env, "container", "") or "")
    try:
        tests = env.cmd.run("python3 -m pytest -q", timeout=180)
        source_diff = env.cmd.run("git diff -- calculator.py", timeout=30)
    finally:
        env.close()
    cleanup = subprocess.run(
        ["docker", "inspect", container],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    reader = candidate_file_reader(_trajectory_path(profile.config))
    trajectory = reader.read_session(session_id, view=PrivacyView.RAW_PRIVATE)
    qita_session = load_session_payload(reader, session_id)
    graph = WorkGraphReader(reader).read(
        GraphSelector("session", parent_session_id)
    )
    kinds = sorted({record.kind.value for record in trajectory.records})
    tests_passed = int(tests.get("returncode", 1)) == 0
    diff_text = str(source_diff.get("stdout", ""))
    source_changed = (
        int(source_diff.get("returncode", 1)) == 0
        and bool(diff_text.strip())
        and "return max(low, min(value, high))" in diff_text
    )
    qita_readable = (
        qita_session.get("trajectory_meta", {}).get("session_id") == session_id
        and bool(graph.timeline)
        and graph.session_summary.get("work_item_count", 0) >= 3
    )
    status = (
        "passed"
        if tests_passed
        and source_changed
        and cleanup.returncode != 0
        and qita_readable
        else "failed"
    )
    return {
        "status": status,
        "tests_passed": tests_passed,
        "test_output_digest": _sha256_text(
            str(tests.get("stdout", "")) + str(tests.get("stderr", ""))
        ),
        "source_changed": source_changed,
        "source_diff_digest": _sha256_text(diff_text),
        "trajectory_record_count": len(trajectory.records),
        "trajectory_kinds": kinds,
        "qita_session_readable": qita_readable,
        "qita_graph_work_item_count": graph.session_summary.get(
            "work_item_count", 0
        ),
        "verification_container_absent": cleanup.returncode != 0,
    }


def _qualify_capability_loss_profile(
    profile: LiveProfile,
    *,
    credentials_path: Path,
) -> dict[str, Any]:
    """Prove text service and a typed native-tool capability loss via Engine."""
    from qitos.config import LocalCredentialFileResolver
    from qitos.config.builder import build_agent_composition

    resolver = LocalCredentialFileResolver(credentials_path, repository_root=ROOT)
    text_config = replace(
        profile.config,
        tools=(),
        tool_preset="none",
        tool_options={},
        tool_use_policy="disabled",
    )
    text_composition = build_agent_composition(
        text_config, credential_resolver=resolver
    )
    text_counter = _count_model_requests(
        text_composition.model,
        max_attempts=int(profile.config.budgets.max_requests),
    )
    try:
        text_result = text_composition.engine.run(
            "Return a concise plain-text statement naming the repository title."
        )
    finally:
        text_composition.close()
    remaining = int(profile.config.budgets.max_requests) - text_counter["attempts"]
    if remaining < 1:
        raise QualificationError(
            "capability probe has no request budget",
            code="request_budget_exhausted",
        )
    native_composition = build_agent_composition(
        profile.config, credential_resolver=resolver
    )
    native_counter = _count_model_requests(
        native_composition.model, max_attempts=remaining
    )
    try:
        native_result = native_composition.engine.run(
            "Call read_file once for README.md before returning any final answer."
        )
    finally:
        native_composition.close()
    capability_loss = any(
        event.payload.get("code") == "provider_capability_loss"
        for event in native_result.events
    ) or native_result.error_code == "provider_capability_loss"
    requests = text_counter["attempts"] + native_counter["attempts"]
    text_ok = bool(text_result.state.final_result)
    cleanup_ok = (
        text_composition.sandbox_receipt.get("cleanup") == "passed"
        and native_composition.sandbox_receipt.get("cleanup") == "passed"
    )
    return {
        "profile_id": profile.profile_id,
        "role": "capability_loss",
        "status": (
            "passed" if text_ok and capability_loss and cleanup_ok else "failed"
        ),
        "requests": requests,
        "text_available": text_ok,
        "native_tool_capability_loss": capability_loss,
        "false_tool_success_absent": not bool(native_result.tool_calls_by_name),
        "error_code": (
            "provider_capability_loss" if capability_loss else "capability_probe_failed"
        ),
        "sandbox_cleanup": cleanup_ok,
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
        and not any(
            token in rendered
            for token in ("/chat/completions", "https://", "http://")
        )
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
    informational_smoke: bool = False,
) -> dict[str, Any]:
    """Run offline gates, then optional live providers and restore workflows."""
    _validate_source(source_commit, enforce_current=enforce_current_source)
    offline = run_offline_gates(profiles, execute_external=execute_offline_gates)
    created_at = generated_at or datetime.now(timezone.utc).isoformat()
    round_id = "s3-g4-l3-" + _sha256_text(
        f"{source_commit}:{created_at}:{SCHEMA_VERSION}"
    )[:16]
    base: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "qualification_round_id": round_id,
        "generated_at": created_at,
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
    profile_by_id = {profile.profile_id: profile for profile in profiles}
    required_profile_ids = (
        "sii-glm-5-2",
        "sii-dsv4",
        "sii-qwen3-8-27b",
    )
    if informational_smoke:
        if len(profiles) != 1 or profiles[0].profile_id != "sii-glm-5-2":
            raise QualificationConfigurationError(
                "informational smoke requires only the GLM primary profile"
            )
        sandbox_profile = profiles[0]
    elif set(profile_by_id) != set(required_profile_ids):
        raise QualificationConfigurationError(
            "live mode requires the GLM primary, DSV parity, and Qwen capability profiles"
        )
    else:
        sandbox_profile = profile_by_id[required_profile_ids[0]]
    try:
        sandbox = qualify_docker_environment(
            sandbox_profile.config,
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
    if informational_smoke:
        try:
            receipt = _informational_smoke_profile(profiles[0], resolver)
        except Exception as exc:
            receipt = {
                "profile_id": profiles[0].profile_id,
                "role": "informational_smoke",
                "config_digest": profiles[0].config.digest(),
                "status": "framework_invariant_failure",
                "requests": 0,
                "provider_request_sent": False,
                "root_error_code": _exception_error_code(
                    exc, "informational_smoke_runtime_failed"
                ),
                "framework_invariant_failure": True,
            }
        base["profiles"] = [receipt]
        base["workflows"] = {"informational_smoke": receipt}
        base["totals"]["requests"] = int(receipt["requests"])
        base["decision"] = {
            "framework_conformance": "external_required_gate",
            "live_agent_capability_matrix": "informational",
            "glm_smoke": receipt["status"],
            "s3_status": (
                "blocked_framework_invariant"
                if receipt["framework_invariant_failure"]
                else "unchanged"
            ),
            "g4_live": "informational",
            "s4_ready": False,
            "feature_baseline_promoted": False,
            "default_branch_ready": False,
        }
        base["privacy"] = _privacy_report(base, forbidden_values)
        if not base["privacy"]["scan_passed"]:
            receipt["framework_invariant_failure"] = True
            receipt["status"] = "framework_invariant_failure"
            base["decision"]["glm_smoke"] = "framework_invariant_failure"
            base["decision"]["s3_status"] = "blocked_framework_invariant"
        base["evidence_digest"] = _evidence_digest(base)
        return base
    primary = profile_by_id[required_profile_ids[0]]
    parity = profile_by_id[required_profile_ids[1]]
    capability = profile_by_id[required_profile_ids[2]]

    def run_workflow(profile: LiveProfile, role: str) -> dict[str, Any]:
        try:
            fixture = _prepare_coding_fixture(profile)
            workflow = _live_restore_workflows(
                profile,
                credentials_path=credentials_path,
                request_limit=int(profile.config.budgets.max_requests),
            )
            return {
                "profile_id": profile.profile_id,
                "role": role,
                "config_digest": profile.config.digest(),
                "fixture": fixture,
                **workflow,
            }
        except Exception as exc:
            code = _exception_error_code(exc, "workflow_failure")
            return {
                "profile_id": profile.profile_id,
                "role": role,
                "config_digest": profile.config.digest(),
                "status": "failed",
                "requests": 0,
                "error_code": code,
                "root_error_code": code,
                "lifecycle_consequence": "failed",
                "pause_reached": False,
                "provider_request_sent": False,
                "detail_code": type(exc).__name__,
            }

    primary_receipt = run_workflow(primary, "primary")
    base["profiles"].append(primary_receipt)
    base["workflows"]["primary"] = primary_receipt
    if primary_receipt.get("status") == "passed":
        parity_receipt = run_workflow(parity, "provider_parity")
    else:
        parity_receipt = {
            "profile_id": parity.profile_id,
            "role": "provider_parity",
            "status": "not_started",
            "requests": 0,
            "error_code": "primary_dependency_failed",
        }
    base["profiles"].append(parity_receipt)
    base["workflows"]["provider_parity"] = parity_receipt
    if parity_receipt.get("status") == "passed":
        try:
            capability_receipt = _qualify_capability_loss_profile(
                capability,
                credentials_path=credentials_path,
            )
        except Exception as exc:
            capability_receipt = {
                "profile_id": capability.profile_id,
                "role": "capability_loss",
                "status": "failed",
                "requests": 0,
                "error_code": _exception_error_code(
                    exc, "capability_probe_failed"
                ),
                "detail_code": type(exc).__name__,
            }
    else:
        capability_receipt = {
            "profile_id": capability.profile_id,
            "role": "capability_loss",
            "status": "not_started",
            "requests": 0,
            "error_code": "parity_dependency_failed",
        }
    base["profiles"].append(capability_receipt)
    base["workflows"]["capability_loss"] = capability_receipt
    base["totals"]["requests"] = sum(
        int(receipt.get("requests", 0)) for receipt in base["profiles"]
    )

    all_passed = (
        sandbox.status == "passed"
        and all(item.get("status") == "passed" for item in base["profiles"])
        and all(
            int(receipt.get("requests", 0))
            <= int(profile_by_id[receipt["profile_id"]].config.budgets.max_requests)
            for receipt in base["profiles"]
        )
    )
    if all_passed:
        base["decision"] = {
            "s3_status": "closed",
            "g4_live": "passed",
            "s4_ready": True,
            "feature_baseline_promoted": False,
            "default_branch_ready": False,
        }
    else:
        first_failure: Mapping[str, Any] = next(
            (
                item
                for item in base["profiles"]
                if item.get("status") != "passed"
            ),
            {},
        )
        base["decision"]["g4_live"] = str(
            first_failure.get("error_code") or "provider_error"
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
    parser.add_argument("--informational-smoke", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--private-dir")
    parser.add_argument("--restore-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--session-id", help=argparse.SUPPRESS)
    parser.add_argument("--max-requests", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.restore_worker:
        if (
            len(args.config) != 1
            or not args.credentials
            or not args.session_id
            or args.max_requests is None
            or args.max_requests < 1
        ):
            parser.error("restore worker requires one config, credentials, and session id")
        return _restore_worker(
            config_path=Path(args.config[0]).expanduser().resolve(),
            credentials_path=Path(args.credentials).expanduser().resolve(),
            session_id=str(args.session_id),
            max_requests=int(args.max_requests),
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
        informational_smoke=bool(args.informational_smoke),
    )
    if args.private_dir:
        private = _validate_private_dir(args.private_dir)
        _write_json(private / "qualification-receipt.json", result, mode=0o600)
    if args.output:
        _write_json(Path(args.output), result, mode=0o644)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    informational_ok = bool(
        args.informational_smoke
        and result.get("profiles")
        and not result["profiles"][0].get("framework_invariant_failure", False)
        and result.get("privacy", {}).get("scan_passed", False)
    )
    return 0 if (
        informational_ok
        or result["decision"]["g4_live"] in {"passed", "live_flag_required"}
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
