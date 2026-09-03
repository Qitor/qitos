from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Sequence

import pytest

from qitos.core.artifact import (
    ArtifactContractError,
    ArtifactRef,
    ArtifactResolver,
    ResolvedArtifact,
    require_artifact,
)
from qitos.core.context import (
    ContextPolicyError,
    ContextRequest,
    DeclaredContextBudgetPolicy,
    collect_context_contributions,
)
from qitos.core.memory import MemorySource
from qitos.core.request_view import ContextContribution, RequestTarget


TARGET = RequestTarget("fixture", "model", "wire", "api")


@dataclass
class SemanticRecallSource:
    contributor_id: str = "memory.semantic"

    def contribute(
        self,
        request: ContextRequest,
    ) -> Sequence[ContextContribution]:
        return (
            ContextContribution(
                contribution_id="memory.fact.one",
                source="memory:semantic",
                content={"request_key": request.request_key, "fact": "stable"},
                priority=15,
                persistence_horizon="session",
            ),
        )


class ByteResolver:
    resolver_key = "artifact:fixture"

    def __init__(self, body: bytes | None) -> None:
        self.body = body

    def probe(self, reference: ArtifactRef) -> bool:
        _ = reference
        return self.body is not None

    def resolve(self, reference: ArtifactRef) -> ResolvedArtifact:
        if self.body is None:
            raise LookupError("missing")
        return ResolvedArtifact(reference, self.body)


def _artifact(body: bytes, *, required: bool = True) -> ArtifactRef:
    return ArtifactRef(
        artifact_id="artifact-fixture",
        resolver_key="artifact:fixture",
        sha256=hashlib.sha256(body).hexdigest(),
        media_type="text/plain",
        byte_length=len(body),
        model_summary="retrievable fixture",
        required=required,
    )


def test_memory_source_is_structural_and_selection_input_is_deterministic() -> None:
    source = SemanticRecallSource()
    request = ContextRequest(request_key="request-one", target=TARGET)

    assert isinstance(source, MemorySource)
    first = collect_context_contributions((source,), request)
    second = collect_context_contributions((source,), request)
    assert [item.to_dict() for item in first] == [item.to_dict() for item in second]


def test_artifact_resolver_verifies_identity_without_persisting_body() -> None:
    body = b"artifact body"
    reference = _artifact(body)
    resolver = ByteResolver(body)

    assert isinstance(resolver, ArtifactResolver)
    require_artifact(reference, resolver)
    resolved = resolver.resolve(reference)
    assert resolved.body == body
    assert "body" not in reference.to_dict()
    assert "resolver_key" not in reference.to_model_projection()


def test_required_artifact_missing_or_corrupt_is_typed() -> None:
    body = b"artifact body"
    reference = _artifact(body)

    with pytest.raises(ArtifactContractError) as missing:
        require_artifact(reference, ByteResolver(None))
    assert missing.value.code == "missing_required_artifact"

    with pytest.raises(ArtifactContractError) as corrupt:
        ByteResolver(b"wrong").resolve(reference)
    assert corrupt.value.code == "artifact_integrity_mismatch"


def test_context_budget_intersects_provider_input_and_output_capabilities() -> None:
    policy = DeclaredContextBudgetPolicy(
        default_max_input_units=20_000,
        unit="tokens",
    )
    budget = policy.budget_for(
        target=TARGET,
        declared_max_input_units=16_000,
        declared_max_output_units=4_000,
        reserved_output_units=4_000,
    )
    assert budget.max_input_units == 16_000
    assert budget.available_input_units == 12_000

    with pytest.raises(ContextPolicyError):
        policy.budget_for(
            target=TARGET,
            declared_max_input_units=16_000,
            declared_max_output_units=4_000,
            reserved_output_units=4_001,
        )

