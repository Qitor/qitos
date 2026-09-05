"""Explicit, model-free loss authorization for closed exchange selection."""

from __future__ import annotations

import hashlib
import json
from typing import Sequence

from qitos.core.request_view import CompactionReceipt


class ClosedExchangeWindowCompactor:
    """Omit the oldest eligible closed exchanges without a summary.

    RequestView owns eligibility and the ContextBudget recent-window boundary.
    This stateless policy authorizes that derived selection and records its loss;
    it never modifies an ExchangeLog or widens a budget or codec loss setting.
    """

    policy_id = "qitos.context.closed_exchange_window/v1"

    def compact(
        self,
        *,
        exchange_ids: Sequence[str],
        selected_digest: str,
        required_units: int,
        available_units: int,
    ) -> CompactionReceipt | None:
        if required_units <= available_units:
            return None
        identities = tuple(exchange_ids)
        if not identities or len(identities) != len(set(identities)):
            raise ValueError("compaction requires unique eligible exchange identities")
        payload = json.dumps(
            [self.policy_id, identities, selected_digest, required_units, available_units],
            separators=(",", ":"),
        )
        return CompactionReceipt(
            receipt_id="compaction_" + hashlib.sha256(payload.encode()).hexdigest()[:24],
            input_exchange_ids=identities,
            output_digest=selected_digest,
            policy_id=self.policy_id,
            declared_losses=("closed_exchange_omitted_without_summary",),
        )
