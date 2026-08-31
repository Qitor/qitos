from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import pytest

from qitos.core.artifact import ArtifactRef
from qitos.core.context import (
    ArtifactRefContributor,
    ContextPolicyError,
    ContextRequest,
    ContextSelection,
    PriorityContextSelectionPolicy,
    RequiredContextMissingError,
    RuntimeInstructionContributor,
    collect_context_contributions,
)
from qitos.core.conversation import ExchangeLog, UserItem
from qitos.core.multimodal import ContentBlock
from qitos.core.request_view import (
    CompactionReceipt,
    ContextBudget,
    ContextContribution,
    RequestTarget,
    RequestView,
)


TARGET = RequestTarget("fixture", "fixture-model", "fixture-wire", "fixture-api")


@dataclass
class RequestAwareContributor:
    contributor_id: str = "z.request-aware"

    def contribute(
        self, request: ContextRequest
    ) -> Sequence[ContextContribution]:
        return (
            ContextContribution(
                contribution_id="context.request-aware",
                source="extension:request-aware",
                content={
                    "request_key": request.request_key,
                    "project_id": request.project_id,
                },
                priority=30,
                required=True,
            ),
        )


@dataclass
class LegacyShapeContributor:
    contributor_id: str = "a.legacy-shape"

    def contribute(self) -> Sequence[ContextContribution]:
        return (
            ContextContribution(
                contribution_id="context.legacy.first",
                source="extension:legacy",
                content=["alpha", {"kind": "structured"}],
                priority=10,
            ),
            ContextContribution(
                contribution_id="context.legacy.second",
                source="extension:legacy",
                content="omega",
                priority=5,
            ),
        )


def _context_request() -> ContextRequest:
    return ContextRequest(
        request_key="request-fixture",
        target=TARGET,
        session_id="session-fixture",
        project_id="project-fixture",
        user_id="user-fixture",
    )


def _log() -> ExchangeLog:
    log = ExchangeLog(log_id="context-log")
    log.append(
        UserItem(
            item_id="user-context",
            exchange_id="exchange-context",
            content=[ContentBlock(type="text", text="Inspect the context.")],
        )
    )
    return log


def test_distinct_custom_contributors_share_one_deterministic_contract() -> None:
    contributors = (RequestAwareContributor(), LegacyShapeContributor())

    first = collect_context_contributions(contributors, _context_request())
    second = collect_context_contributions(reversed(contributors), _context_request())

    assert [item.contribution_id for item in first] == [
        "context.legacy.first",
        "context.legacy.second",
        "context.request-aware",
    ]
    assert [item.to_dict() for item in first] == [item.to_dict() for item in second]
    assert first[-1].content_value == {
        "project_id": "project-fixture",
        "request_key": "request-fixture",
    }


def test_contributor_and_contribution_identities_are_unique() -> None:
    with pytest.raises(ContextPolicyError):
        collect_context_contributions(
            (LegacyShapeContributor(), LegacyShapeContributor()),
            _context_request(),
        )

    class DuplicateContribution(RequestAwareContributor):
        contributor_id = "duplicate-contribution"

        def contribute(
            self, request: ContextRequest
        ) -> Sequence[ContextContribution]:
            _ = request
            item = ContextContribution(
                contribution_id="duplicate",
                source="extension:duplicate",
                content="same",
            )
            return item, item

    with pytest.raises(ContextPolicyError):
        collect_context_contributions((DuplicateContribution(),), _context_request())


def test_required_context_fails_closed_when_explicit_budget_is_exhausted() -> None:
    required = ContextContribution(
        contribution_id="required",
        source="extension:required",
        content="too-large",
        required=True,
    )
    policy = PriorityContextSelectionPolicy()

    with pytest.raises(RequiredContextMissingError):
        policy.select(
            (required,),
            budget=ContextBudget(
                max_input_units=2,
                reserved_output_units=1,
                unit="characters",
                protected_recent_exchanges=0,
            ),
            counter=lambda value, unit: 10,
        )


class ReverseSelectionPolicy:
    policy_id = "x.fixture.reverse/v1"

    def select(
        self,
        contributions: Iterable[ContextContribution],
        *,
        budget: ContextBudget,
        already_used_units: int = 0,
        counter: Any,
    ) -> ContextSelection:
        _ = budget
        _ = already_used_units
        ordered = tuple(reversed(tuple(contributions)))
        selected = ordered[:1]
        omitted = ordered[1:]
        return ContextSelection(
            selected=selected,
            omitted=omitted,
            selected_units=sum(counter(item.content_value, "characters") for item in selected),
            omitted_units=sum(counter(item.content_value, "characters") for item in omitted),
            unit="characters",
            policy_id=self.policy_id,
            reasons=("fixture_reverse",),
        )


def test_request_view_uses_replaceable_selection_policy_and_receipt() -> None:
    contributions = collect_context_contributions(
        (RequestAwareContributor(), LegacyShapeContributor()), _context_request()
    )
    view = RequestView.from_exchange_log(
        _log(),
        target=TARGET,
        context_contributions=contributions,
        context_selection_policy=ReverseSelectionPolicy(),
        context_budget=ContextBudget(
            max_input_units=10_000,
            reserved_output_units=1,
            unit="characters",
        ),
    )

    assert view.selection.selected_context_ids == ("context.request-aware",)
    assert view.selection.omitted_context_ids == (
        "context.legacy.second",
        "context.legacy.first",
    )
    assert "context_policy:x.fixture.reverse/v1" in view.selection.reasons
    assert "fixture_reverse" in view.selection.reasons


def test_runtime_instruction_and_artifact_contributors_are_provider_neutral() -> None:
    artifact = ArtifactRef(
        artifact_id="artifact-fixture",
        resolver_key="artifact:fixture",
        sha256="a" * 64,
        media_type="text/plain",
        byte_length=7,
        model_summary="fixture artifact",
    )
    contributions = collect_context_contributions(
        (
            RuntimeInstructionContributor(
                contributor_id="runtime",
                instructions=("Do one thing.", "", "Then stop."),
            ),
            ArtifactRefContributor(
                contributor_id="artifacts", artifact_refs=(artifact,)
            ),
        ),
        _context_request(),
    )

    by_id = {item.contribution_id: item for item in contributions}
    assert by_id["runtime"].content_value == {
        "instructions": ["Do one thing.", "Then stop."]
    }
    assert by_id["artifacts"].content_value["artifacts"][0]["artifact_id"] == (
        "artifact-fixture"
    )
    assert "fixture" not in {
        by_id["runtime"].requested_placement,
        by_id["artifacts"].requested_placement,
    }


def test_custom_compaction_policy_must_declare_loss_in_receipt() -> None:
    class SummaryCompactionPolicy:
        policy_id = "x.fixture.summary/v1"

        def compact(
            self,
            *,
            exchange_ids: Sequence[str],
            selected_digest: str,
            required_units: int,
            available_units: int,
        ) -> CompactionReceipt:
            assert required_units > available_units
            return CompactionReceipt(
                receipt_id="receipt-summary",
                input_exchange_ids=tuple(exchange_ids),
                output_digest=hashlib.sha256(selected_digest.encode()).hexdigest(),
                policy_id=self.policy_id,
                declared_losses=("verbatim_history",),
                model_reference="summary:fixture",
            )

    receipt = SummaryCompactionPolicy().compact(
        exchange_ids=("exchange-1", "exchange-2"),
        selected_digest="selected",
        required_units=100,
        available_units=50,
    )

    assert receipt.policy_id == "x.fixture.summary/v1"
    assert receipt.declared_losses == ("verbatim_history",)
    assert len(receipt.output_digest) == 64
