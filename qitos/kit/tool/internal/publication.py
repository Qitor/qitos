"""Caller-authorized source publication through the canonical tool boundary."""

import hashlib
from pathlib import Path
from typing import Any, Iterable

from qitos.core.artifact import ArtifactRef
from qitos.core.env import EnvCapabilityError
from qitos.core.tool import BaseTool, ToolPermission, ToolSpec
from qitos.core.tool_result import ToolResult
from qitos.core.tool_runtime import ToolEffectDeclaration
from qitos.kit.env._publication import _path, publish_files


class SandboxPublicationTool(BaseTool):
    """Opt-in tool restricted to paths and input digest approved by its caller."""

    def __init__(self, env: Any, *, paths: Iterable[str], expected_input_digest: str):
        self._env = env
        self._paths = tuple(_path(name) for name in paths)
        self._digest = expected_input_digest
        self._generation = env.processes.generation
        super().__init__(ToolSpec(
            name="publish_workspace", description="Publish only caller-authorized sandbox outputs.",
            parameters={}, required=[], permissions=ToolPermission(filesystem_write=True),
            needs_approval=True, concurrency_safe=False,
            effect=lambda args, context: ToolEffectDeclaration(
                effect_ref=f"publication:{expected_input_digest}",
                metadata={"kind": "explicit_source_publication", "paths": list(self._paths)},
            ),
        ))

    def execute(self, args: Any, runtime_context: Any = None) -> ToolResult:
        context = runtime_context or {}
        artifacts = []
        try:
            if self._env._owner_guard is not None:
                self._env._owner_guard()
            if args or context.get("env") is not self._env:
                raise EnvCapabilityError("publication_authority_mismatch", "publication authority is invalid")
            if self._env.processes.generation != self._generation:
                raise EnvCapabilityError("stale_generation", "publication owner is stale")
            retained = self._env._closed and self._env.cleanup_receipt.get("container_absent") is True
            if not self._digest or self._digest != self._env.input_digest or not (retained or self._env._owns_container()):
                raise EnvCapabilityError("publication_input_mismatch", "publication input identity is invalid")
            resolver = context.get("artifact_resolver")
            if resolver is None or not callable(getattr(resolver, "put", None)):
                raise EnvCapabilityError("artifact_store_unavailable", "publication requires retained output artifacts")
            outputs = {}
            for name in self._paths:
                if retained:
                    from qitos.kit.env._workspace_artifact import selected_output
                    body = selected_output(self._env, name)
                else:
                    snapshot = self._env.fs.snapshot(name)
                    body = self._env.fs.read_text(name).encode("utf-8")
                    if hashlib.sha256(body).hexdigest() != snapshot.sha256:
                        raise EnvCapabilityError("publication_output_conflict", "sandbox output changed during capture")
                digest = hashlib.sha256(body).hexdigest()
                reference = ArtifactRef(artifact_id=f"sha256:{digest}",
                                        resolver_key=resolver.resolver_key, sha256=digest,
                                        byte_length=len(body), media_type="text/plain")
                resolver.put(reference, body)
                artifacts.append(reference)
                outputs[name] = body
            result = publish_files(Path(self._env._source_workspace), self._env._input_files, outputs)
            return ToolResult(output=result, model_output=result, artifact_refs=tuple(artifacts),
                              tool_name=self.name)
        except Exception as exc:
            code = str(getattr(exc, "code", "publication_failed"))
            return ToolResult.execution_error(
                code=code, error="explicit publication failed", tool_name=self.name,
                artifact_refs=tuple(artifacts), outcome_unknown=code == "publication_rollback_unknown",
            )
