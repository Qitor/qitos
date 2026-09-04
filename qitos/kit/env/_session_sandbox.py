"""Session snapshot owner for artifact-backed cold Docker restoration."""

from dataclasses import replace
from typing import Any

from qitos.core.artifact import ArtifactRef
from qitos.core.env import EnvCapabilityError, ProcessHandle
from qitos.core.session import SessionSnapshot
from qitos.core.work_graph import WorkGraph
from qitos.kit.env.docker_env import DockerEnv, DockerProcessControlCapability
from qitos.kit.env.sandbox import (
    SANDBOX_SNAPSHOT_COMPONENT_CODEC, DockerSandboxBackend, SandboxIdentity,
    SandboxSnapshotComponent,
)
from qitos.kit.env._workspace_artifact import retain_workspace, restore_workspace


class SessionSandboxComponent:
    codec = replace(SANDBOX_SNAPSHOT_COMPONENT_CODEC, required=True)

    def __init__(self, env: DockerEnv, backend: DockerSandboxBackend, store: Any, resolver: Any):
        self.prototype = env
        self.initial_backend = backend
        self.store = store
        self.resolver = resolver
        self.allocations: dict[tuple[str, str], tuple[DockerEnv, DockerSandboxBackend]] = {}
        self.on_bind: Any = None

    def _bind(self, context: Any) -> tuple[DockerEnv, DockerSandboxBackend]:
        session = context.session
        if session is None:
            raise EnvCapabilityError("sandbox_session_identity_missing", "sandbox requires a Session identity")
        key = (session.session_id.value, session.run_id.value)
        existing = self.allocations.get(key)
        if existing is None or existing[0]._closed:
            previous = existing[0].output_artifact if existing else None
            env = DockerEnv(
                image=self.prototype.image, host_workspace=self.prototype._source_workspace,
                workspace_root=self.prototype.container_workspace, auto_create=True,
                remove_on_close=True, strict_workspace=True, policy=self.prototype.policy,
            )
            identity = SandboxIdentity(sandbox_id=env._sandbox_id, session_id=key[0], run_id=key[1],
                                       work_item_id=session.work_item_id.value,
                                       attempt_id=session.attempt_id.value, owner_generation=context.generation)
            env._logical_identity = identity.to_dict()
            env._artifact_resolver = self.resolver
            backend = DockerSandboxBackend(env, config_digest=self.initial_backend.config_digest, identity=identity)
            try:
                backend.prepare()
                if previous is not None:
                    restore_workspace(env, previous)
            except Exception:
                backend.cleanup()
                raise
            self.allocations[key] = (env, backend)
            existing = env, backend
            if not self.prototype._closed:
                self.initial_backend.cleanup()
        env, backend = existing
        context.engine.env = env
        context.engine.runtime.bind_engine_resources(context.engine)

        def guard() -> None:
            head = self.store.get_session_head(key[0])
            if head is not None and head.owner_run_id != key[1]:
                raise EnvCapabilityError("stale_sandbox_owner", "sandbox owner has been superseded")
            if head is not None:
                record = self.store.get_session_snapshot(head.snapshot_id)
                snapshot = SessionSnapshot.from_dict(record.payload, component_registry=context.engine.runtime.component_registry)
                component = next((item for item in snapshot.components if item.slot == "work_graph"), None)
                if component is not None:
                    value = component.decode(context.engine.runtime.component_registry)
                    if value.graph is not None:
                        work = WorkGraph.from_canonical_dict(value.graph).work_items.get(session.work_item_id)
                        if work is not None and work.owner.agent_id.value != context.owner_id:
                            raise EnvCapabilityError("stale_sandbox_owner", "work ownership has been transferred")
        env._owner_guard = guard
        if self.on_bind is not None:
            self.on_bind(context.engine, env, backend)
        return env, backend

    def capture(self, context: Any) -> SandboxSnapshotComponent:
        key = (context.session.session_id.value, context.session.run_id.value)
        allocation = self.allocations.get(key)
        if allocation is None:
            allocation = self._bind(context)
        env, backend = allocation
        context.engine.env = env
        if self.on_bind is not None:
            self.on_bind(context.engine, env, backend)
        quiescence = "processes_terminal"
        processes = env.processes
        if not isinstance(processes, DockerProcessControlCapability):
            raise EnvCapabilityError("sandbox_process_control_unsupported", "sandbox requires owned Docker process control")
        for identity in tuple(processes._owned):
            if processes.poll(ProcessHandle(identity, processes.generation))["worker_still_running"]:
                quiescence = "worker_still_running"
        if quiescence != "processes_terminal" and context.lifecycle.value in {"pausing", "paused", "waiting_input"}:
            raise EnvCapabilityError("sandbox_worker_still_running", "workspace cannot be snapshotted while a worker is active")
        if not env._closed and quiescence == "processes_terminal":
            retain_workspace(env)
        reference = env.output_artifact
        if reference is None:
            raise EnvCapabilityError("sandbox_artifact_unavailable", "workspace snapshot was not retained")
        receipt = backend.durability_receipt()
        return SandboxSnapshotComponent(
            logical_identity=backend.identity.to_dict(), backend_type="docker",
            policy_digest=receipt["policy_digest"], image_digest=receipt["image_digest"],
            capability_set=("artifact_cold_restore",), lease={
                "lease_id": "lease:" + backend.identity.sandbox_id,
                "owner_generation": backend.identity.owner_generation,
                "state": "closed" if env._closed else "active",
            },
            workspace_digest=reference.sha256, input_digest=env.input_digest,
            quiescence=quiescence, cleanup_state="cleaned" if env._closed else "pending",
            workspace_artifact=reference.to_dict(),
        )

    def restore(self, value: SandboxSnapshotComponent, context: Any) -> None:
        if value.quiescence != "processes_terminal" or value.workspace_artifact is None:
            raise EnvCapabilityError("sandbox_restore_unsupported", "sandbox snapshot lacks a quiescent workspace artifact")
        source = value.logical_identity
        own = context.session.session_id.value
        fork = context.session.fork_receipt
        if source["session_id"] != own and (fork is None or source["session_id"] != fork.source_session_id):
            raise EnvCapabilityError("sandbox_identity_mismatch", "sandbox snapshot belongs to another Session")
        if source["session_id"] == own and source["owner_generation"] > context.generation:
            raise EnvCapabilityError("sandbox_generation_mismatch", "sandbox snapshot has a future owner generation")
        env, backend = self._bind(context)
        receipt = backend.durability_receipt()
        if receipt["policy_digest"] != value.policy_digest or receipt["image_digest"] != value.image_digest:
            raise EnvCapabilityError("sandbox_attestation_mismatch", "restored sandbox policy or image changed")
        reference = ArtifactRef.from_dict(value.workspace_artifact)
        restore_workspace(env, reference)
        if env.input_digest != value.input_digest:
            raise EnvCapabilityError("sandbox_input_mismatch", "workspace input identity changed")
        # Native process/memory resume remains unsupported; this owner restores files.
        if backend._receipt is None:
            raise EnvCapabilityError("sandbox_attestation_missing", "restored sandbox lacks an attested receipt")
        backend._receipt = replace(backend._receipt, workspace_digest=reference.sha256,
                                   input_digest=value.input_digest)

    def close(self) -> None:
        failures = []
        for backend in (self.initial_backend, *(item[1] for item in self.allocations.values())):
            try:
                backend.cleanup()
            except Exception:
                failures.append(backend.identity.sandbox_id)
        if failures:
            raise EnvCapabilityError("sandbox_cleanup_incomplete", "owned sandbox cleanup or output retention failed")
