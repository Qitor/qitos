"""Producer tests for the canonical S1 identity vocabulary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qitos.core.session import (
    AgentIdentity,
    AttemptIdentity,
    CheckpointIdentity,
    ContinuationIdentity,
    IdentityKind,
    IdentityRelation,
    IdentityRelationship,
    RunIdentity,
    SessionContractError,
    SessionErrorCode,
    SessionIdentity,
    SnapshotIdentity,
    ToolCallIdentity,
    WorkItemIdentity,
    identity_from_dict,
)


FIXTURE = Path(__file__).parents[1] / "fixtures" / "session" / "identity-vocabulary.json"


IDENTITY_TYPES = {
    IdentityKind.SESSION: SessionIdentity,
    IdentityKind.RUN: RunIdentity,
    IdentityKind.SNAPSHOT: SnapshotIdentity,
    IdentityKind.CHECKPOINT: CheckpointIdentity,
    IdentityKind.WORK_ITEM: WorkItemIdentity,
    IdentityKind.ATTEMPT: AttemptIdentity,
    IdentityKind.TOOL_CALL: ToolCallIdentity,
    IdentityKind.AGENT: AgentIdentity,
    IdentityKind.CONTINUATION: ContinuationIdentity,
}


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_every_identity_kind_has_one_distinct_type_and_round_trips() -> None:
    fixture = _fixture()
    assert fixture["schema_version"] == 1
    assert fixture["contract"] == "qitos.session.identity"
    decoded = {}
    for name, payload in fixture["identities"].items():
        identity = identity_from_dict(payload)
        decoded[name] = identity
        assert type(identity) is IDENTITY_TYPES[IdentityKind(name)]
        assert identity.to_dict() == payload
    assert len(set(decoded.values())) == len(IdentityKind)


def test_framework_generates_valid_opaque_identity_for_every_kind() -> None:
    for kind, identity_type in IDENTITY_TYPES.items():
        identity = identity_type.generate()
        assert identity.KIND is kind
        assert identity.value.startswith(f"{identity_type.PREFIX}_")
        assert identity_from_dict(identity.to_dict()) == identity


def test_identity_types_cannot_impersonate_each_other() -> None:
    session = SessionIdentity.generate()
    with pytest.raises(SessionContractError) as exc_info:
        RunIdentity(session.value)
    assert exc_info.value.error_code is SessionErrorCode.INVALID_IDENTITY_RELATIONSHIP
    assert session != RunIdentity.generate()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"kind": "session"},
        {"kind": "session", "value": 7},
        {"kind": "session", "value": "session_0000000000000000", "extra": True},
        {"kind": "unknown", "value": "unknown_0000000000000000"},
    ],
)
def test_identity_reader_is_strict_and_does_not_echo_raw_values(payload: dict) -> None:
    with pytest.raises(SessionContractError) as exc_info:
        identity_from_dict(payload)
    failure = exc_info.value.to_dict()
    assert failure["error_code"] == "invalid_identity_relationship"
    assert "unknown_0000000000000000" not in json.dumps(failure)


def test_declared_relationship_fixture_round_trips() -> None:
    for payload in _fixture()["relationships"]:
        relationship = IdentityRelationship.from_dict(payload)
        assert relationship.to_dict() == payload


def test_relationship_rejects_wrong_endpoint_kinds_without_name_inference() -> None:
    with pytest.raises(SessionContractError) as exc_info:
        IdentityRelationship(
            relation=IdentityRelation.SESSION_RUN,
            source=RunIdentity.generate(),
            target=SessionIdentity.generate(),
        )
    error = exc_info.value
    assert error.error_code is SessionErrorCode.INVALID_IDENTITY_RELATIONSHIP
    assert error.metadata == {
        "relation": "session_run",
        "source_kind": "run",
        "target_kind": "session",
    }


def test_generation_and_attempt_are_not_interchangeable() -> None:
    attempt = AttemptIdentity.generate()
    assert not isinstance(attempt, int)
    with pytest.raises(SessionContractError):
        AttemptIdentity("attempt_3")
