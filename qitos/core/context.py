"""Provider-neutral context contribution and selection contracts.

Context is request input with explicit identity, provenance, budget, and loss
semantics.  It is not conversation history, semantic memory, or a provider
prompt template.  The concrete provider placement is decided later by a codec.
"""

from __future__ import annotations

import json
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Optional, Protocol, Sequence

from .artifact import ArtifactRef
from .request_view import (
    CompactionReceipt,
    ContextBudget,
    ContextContribution,
    ContextContributor,
    RequestContractError,
    RequestTarget,
    _json_text,
)


class ContextPolicyError(RequestContractError):
    """Base failure for deterministic context contribution/selection."""

    code = "context_policy_error"


class RequiredContextMissingError(ContextPolicyError):
    code = "required_context_missing"


class ContextCompactionRequiredError(ContextPolicyError):
    code = "context_compaction_required"


@dataclass(frozen=True)
class ContextRequest:
    """Stable input supplied to explicitly configured contributors."""

    request_key: str
    target: RequestTarget
    session_id: Optional[str] = None
    project_id: Optional[str] = None
    user_id: Optional[str] = None
    runtime_instruction_digest: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.request_key or "").strip():
            raise ContextPolicyError("context request_key must be non-empty")
        try:
            isolated = json.loads(_json_text(dict(self.metadata), "context.metadata"))
        except (TypeError, ValueError, RequestContractError) as exc:
            raise ContextPolicyError("context request metadata must be bounded JSON") from exc
        object.__setattr__(self, "metadata", isolated)


UnitCounter = Callable[[Any, str], int]


def default_unit_counter(value: Any, unit: str) -> int:
    """Deterministic fallback counter used when no model tokenizer is injected."""

    try:
        text = _json_text(value, "context.counter")
    except RequestContractError as exc:
        raise ContextPolicyError("context value is not bounded JSON") from exc
    if unit == "characters":
        return len(text)
    if unit == "tokens":
        # A stable conservative approximation. Model-aware policies may inject
        # a tokenizer-backed counter without changing contributor contracts.
        return max(1, (len(text) + 3) // 4)
    raise ContextPolicyError(f"unsupported context budget unit: {unit!r}")


@dataclass(frozen=True)
class ContextSelection:
    selected: tuple[ContextContribution, ...]
    omitted: tuple[ContextContribution, ...]
    selected_units: int
    omitted_units: int
    unit: str
    policy_id: str
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        selected_ids = [item.contribution_id for item in self.selected]
        omitted_ids = [item.contribution_id for item in self.omitted]
        if len(selected_ids) != len(set(selected_ids)):
            raise ContextPolicyError("selected context identities must be unique")
        if len(omitted_ids) != len(set(omitted_ids)):
            raise ContextPolicyError("omitted context identities must be unique")
        if set(selected_ids) & set(omitted_ids):
            raise ContextPolicyError("context cannot be selected and omitted")


class ContextSelectionPolicy(Protocol):
    policy_id: str

    def select(
        self,
        contributions: Iterable[ContextContribution],
        *,
        budget: ContextBudget,
        already_used_units: int = 0,
        counter: UnitCounter = default_unit_counter,
    ) -> ContextSelection:
        ...


@dataclass(frozen=True)
class PriorityContextSelectionPolicy:
    """Default deterministic priority/identity selection policy."""

    policy_id: str = "qitos.context.priority/v1"

    def select(
        self,
        contributions: Iterable[ContextContribution],
        *,
        budget: ContextBudget,
        already_used_units: int = 0,
        counter: UnitCounter = default_unit_counter,
    ) -> ContextSelection:
        ordered = sorted(
            tuple(contributions),
            key=lambda item: (not item.required, -item.priority, item.contribution_id),
        )
        identities = [item.contribution_id for item in ordered]
        if len(identities) != len(set(identities)):
            raise ContextPolicyError("context contribution identities must be unique")
        selected: list[ContextContribution] = []
        omitted: list[ContextContribution] = []
        selected_units = 0
        omitted_units = 0
        used = max(0, int(already_used_units))
        for contribution in ordered:
            units = counter(contribution.content_value, budget.unit)
            if not contribution.model_visible:
                if contribution.required:
                    raise RequiredContextMissingError("required context is not model-visible")
                omitted.append(contribution)
                omitted_units += units
                continue
            if used + units <= budget.available_input_units:
                selected.append(contribution)
                selected_units += units
                used += units
                continue
            if contribution.required:
                raise RequiredContextMissingError(
                    "required context "
                    f"{contribution.contribution_id!r} exceeds the request budget"
                )
            omitted.append(contribution)
            omitted_units += units
        return ContextSelection(
            selected=tuple(selected),
            omitted=tuple(omitted),
            selected_units=selected_units,
            omitted_units=omitted_units,
            unit=budget.unit,
            policy_id=self.policy_id,
            reasons=("required_then_priority_then_identity", "required_context_fails_closed"),
        )


class ContextBudgetPolicy(Protocol):
    policy_id: str

    def budget_for(
        self,
        *,
        target: RequestTarget,
        declared_max_input_units: Optional[int],
        reserved_output_units: int,
        declared_max_output_units: Optional[int] = None,
    ) -> ContextBudget:
        ...


@dataclass(frozen=True)
class DeclaredContextBudgetPolicy:
    """Use adapter-declared capacity; never infer it from a model name."""

    default_max_input_units: int = 120_000
    unit: str = "characters"
    protected_recent_exchanges: int = 1
    policy_id: str = "qitos.context.declared_budget/v1"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.default_max_input_units, int)
            or isinstance(self.default_max_input_units, bool)
            or self.default_max_input_units <= 0
        ):
            raise ContextPolicyError("default context budget must be positive")
        if self.unit not in {"characters", "tokens"}:
            raise ContextPolicyError("context budget unit is unsupported")
        if (
            not isinstance(self.protected_recent_exchanges, int)
            or isinstance(self.protected_recent_exchanges, bool)
            or self.protected_recent_exchanges < 0
        ):
            raise ContextPolicyError(
                "protected recent exchange count must be non-negative"
            )

    def budget_for(
        self,
        *,
        target: RequestTarget,
        declared_max_input_units: Optional[int],
        reserved_output_units: int,
        declared_max_output_units: Optional[int] = None,
    ) -> ContextBudget:
        _ = target
        if declared_max_input_units is not None and (
            not isinstance(declared_max_input_units, int)
            or isinstance(declared_max_input_units, bool)
            or declared_max_input_units <= 0
        ):
            raise ContextPolicyError("declared input budget must be positive")
        maximum = declared_max_input_units or self.default_max_input_units
        if (
            not isinstance(reserved_output_units, int)
            or isinstance(reserved_output_units, bool)
            or reserved_output_units < 0
        ):
            raise ContextPolicyError("reserved output budget must be non-negative")
        if declared_max_output_units is not None and (
            not isinstance(declared_max_output_units, int)
            or isinstance(declared_max_output_units, bool)
            or declared_max_output_units <= 0
        ):
            raise ContextPolicyError("declared output budget must be positive")
        reserve = reserved_output_units
        if (
            declared_max_output_units is not None
            and reserve > declared_max_output_units
        ):
            raise ContextPolicyError(
                "requested output budget exceeds provider capability"
            )
        if reserve >= maximum:
            raise ContextPolicyError(
                "reserved output units must be below declared input capacity"
            )
        return ContextBudget(
            max_input_units=maximum,
            reserved_output_units=reserve,
            unit=self.unit,  # type: ignore[arg-type]
            protected_recent_exchanges=self.protected_recent_exchanges,
        )


class CompactionPolicy(Protocol):
    policy_id: str

    def compact(
        self,
        *,
        exchange_ids: Sequence[str],
        selected_digest: str,
        required_units: int,
        available_units: int,
    ) -> Optional[CompactionReceipt]:
        ...


@dataclass(frozen=True)
class RejectingCompactionPolicy:
    """Safe default: never manufacture summaries or undeclared loss."""

    policy_id: str = "qitos.context.no_compaction/v1"

    def compact(
        self,
        *,
        exchange_ids: Sequence[str],
        selected_digest: str,
        required_units: int,
        available_units: int,
    ) -> Optional[CompactionReceipt]:
        _ = exchange_ids
        _ = selected_digest
        if required_units > available_units:
            raise ContextCompactionRequiredError(
                "request exceeds budget and the configured compaction policy "
                "does not declare a lossy transform"
            )
        return None


@dataclass(frozen=True)
class StaticContextContributor:
    """Small reusable contributor for project/user/session context."""

    contributor_id: str
    source: str
    value: Any = field(repr=False)
    priority: int = 0
    requested_placement: str = "developer"
    required: bool = False
    persistence_horizon: str = "request"
    sensitivity: str = "internal"

    def contribute(self, request: ContextRequest) -> Sequence[ContextContribution]:
        _ = request
        return (
            ContextContribution(
                contribution_id=self.contributor_id,
                source=self.source,
                content=self.value,
                priority=self.priority,
                requested_placement=self.requested_placement,
                required=self.required,
                persistence_horizon=self.persistence_horizon,
                sensitivity=self.sensitivity,
            ),
        )


class ProjectContextContributor(StaticContextContributor):
    pass


class UserContextContributor(StaticContextContributor):
    pass


class SessionContextContributor(StaticContextContributor):
    pass


@dataclass(frozen=True)
class RuntimeInstructionContributor:
    contributor_id: str
    instructions: tuple[str, ...]
    source: str = "runtime:instructions"
    priority: int = 100
    required: bool = True

    def contribute(self, request: ContextRequest) -> Sequence[ContextContribution]:
        _ = request
        cleaned = tuple(str(item).strip() for item in self.instructions if str(item).strip())
        if not cleaned and self.required:
            raise RequiredContextMissingError("required runtime instructions are empty")
        if not cleaned:
            return ()
        return (
            ContextContribution(
                contribution_id=self.contributor_id,
                source=self.source,
                content={"instructions": list(cleaned)},
                priority=self.priority,
                requested_placement="developer",
                persistence_horizon="request",
                sensitivity="internal",
                required=self.required,
            ),
        )


@dataclass(frozen=True)
class ArtifactRefContributor:
    contributor_id: str
    artifact_refs: tuple[ArtifactRef, ...]
    source: str = "artifact:references"
    priority: int = 20

    def contribute(self, request: ContextRequest) -> Sequence[ContextContribution]:
        _ = request
        visible = [
            item.to_model_projection()
            for item in self.artifact_refs
        ]
        return (
            ContextContribution(
                contribution_id=self.contributor_id,
                source=self.source,
                content={"artifacts": visible},
                priority=self.priority,
                # Tool-produced metadata is evidence, never privileged policy.
                requested_placement="user",
                persistence_horizon="request",
                sensitivity="internal",
                required=any(item.required for item in self.artifact_refs),
            ),
        ) if visible else ()


def collect_context_contributions(
    contributors: Iterable[ContextContributor], request: ContextRequest
) -> tuple[ContextContribution, ...]:
    """Collect, isolate, and validate explicit contributors deterministically."""

    collected: list[ContextContribution] = []
    contributor_ids: set[str] = set()
    contribution_ids: set[str] = set()
    for contributor in sorted(
        tuple(contributors), key=lambda item: str(getattr(item, "contributor_id", ""))
    ):
        contributor_id = str(getattr(contributor, "contributor_id", "")).strip()
        if not contributor_id:
            raise ContextPolicyError("context contributor_id must be non-empty")
        if contributor_id in contributor_ids:
            raise ContextPolicyError("context contributor identities must be unique")
        contributor_ids.add(contributor_id)
        contribute = contributor.contribute
        try:
            signature = inspect.signature(contribute)
            values = (
                contribute()
                if len(signature.parameters) == 0
                else contribute(request)
            )
        except ContextPolicyError:
            raise
        except (TypeError, ValueError) as exc:
            raise ContextPolicyError(
                "context contributor invocation failed"
            ) from exc
        if not isinstance(values, Sequence):
            raise ContextPolicyError("context contributor must return a sequence")
        for contribution in values:
            if not isinstance(contribution, ContextContribution):
                raise ContextPolicyError(
                    "context contributor returned a non-ContextContribution value"
                )
            if contribution.contribution_id in contribution_ids:
                raise ContextPolicyError("context contribution identities must be unique")
            contribution_ids.add(contribution.contribution_id)
            collected.append(ContextContribution.from_dict(contribution.to_dict()))
    return tuple(collected)


__all__ = [
    "ContextPolicyError",
    "RequiredContextMissingError",
    "ContextCompactionRequiredError",
    "ContextRequest",
    "ContextContributor",
    "ContextSelection",
    "ContextSelectionPolicy",
    "PriorityContextSelectionPolicy",
    "ContextBudgetPolicy",
    "DeclaredContextBudgetPolicy",
    "CompactionPolicy",
    "RejectingCompactionPolicy",
    "StaticContextContributor",
    "ProjectContextContributor",
    "UserContextContributor",
    "SessionContextContributor",
    "RuntimeInstructionContributor",
    "ArtifactRefContributor",
    "collect_context_contributions",
    "default_unit_counter",
]
