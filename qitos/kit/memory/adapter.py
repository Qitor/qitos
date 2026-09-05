"""Borrowed Memory to request-context adaptation; no resource ownership."""

from __future__ import annotations

import copy
import hashlib
import re
from typing import Any, Mapping, Sequence

from qitos.core.context import ContextPolicyError, RequiredContextMissingError
from qitos.core.memory import Memory, MemoryRecord
from qitos.core.request_view import ContextContribution


class MemorySourceAdapter:
    """Recall a factory-bound namespace as user-level context data.

    Namespace is a logical label, not a directory selector or an authorization.
    The factory must bind the correct Memory resource. No global memory is read
    by this adapter. Every request recalls fresh data, including after restore;
    revision is provenance, never a permanent suppression cache.
    """

    def __init__(
        self,
        memory: Memory,
        *,
        namespace: str,
        query: Mapping[str, Any] | None = None,
        required: bool = False,
        priority: int = 0,
    ) -> None:
        if not isinstance(namespace, str) or not re.fullmatch(
            r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}", namespace
        ):
            raise ContextPolicyError("memory namespace must be a logical label")
        if not isinstance(required, bool):
            raise ContextPolicyError("memory required must be boolean")
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise ContextPolicyError("memory priority must be an integer")
        self.memory = memory
        self.namespace = namespace
        self.query = copy.deepcopy(dict(query)) if query is not None else None
        self.required = required
        self.priority = priority
        self.contributor_id = "memory:" + namespace

    def contribute(self, request: Any) -> Sequence[ContextContribution]:
        _ = request
        records = self.memory.retrieve(query=copy.deepcopy(self.query))
        if not isinstance(records, (list, tuple)) or any(
            not isinstance(record, MemoryRecord) for record in records
        ):
            raise ContextPolicyError("memory must retrieve MemoryRecord values")
        if not records and self.required:
            raise RequiredContextMissingError("required memory recall is empty")
        contributions: dict[str, ContextContribution] = {}
        for record in records:
            identity = hashlib.sha256(record.record_id.encode()).hexdigest()
            contribution = ContextContribution(
                contribution_id=f"{self.contributor_id}:{identity}",
                source=self.contributor_id,
                content=record.content,
                requested_placement="user",
                persistence_horizon="request",
                required=self.required,
                priority=self.priority,
            )
            # Reconstruct with the canonical content digest as its revision.
            value = contribution.to_dict()
            value["revision"] = contribution.digest
            contribution = ContextContribution.from_dict(value)
            previous = contributions.get(identity)
            if previous is not None and previous.digest != contribution.digest:
                raise ContextPolicyError("memory returned conflicting record revisions")
            contributions[identity] = contribution
        return tuple(contributions[key] for key in sorted(contributions))

    def reset(self, run_id: str | None = None) -> None:
        """No owned state; never reset the borrowed memory."""

    def close(self) -> None:
        """No owned resources; never close the borrowed memory."""
