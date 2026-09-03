"""Read-only qita inspection façade over the structural TrajectoryReader."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple


class QitaReadError(RuntimeError):
    """Typed, non-echoing read failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class InspectionResult:
    view: str
    records: Tuple[Dict[str, Any], ...]
    loss: Any
    unknown: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "view": self.view,
            "records": copy.deepcopy(list(self.records)),
            "unknown": self.unknown,
            "loss": self.loss.to_dict(),
        }


class ReadOnlyInspection:
    """Reader-only board, lineage, execution, and live-polling queries.

    The façade deliberately has no pause, resume, fork, handoff, or WorkGraph
    mutation method. Runtime control belongs to Session/qit.
    """

    def __init__(self, reader: Any) -> None:
        required = (
            "discover_runs",
            "read_run",
            "read_session",
            "replay",
            "validate_integrity",
        )
        if any(not callable(getattr(reader, name, None)) for name in required):
            raise QitaReadError("trajectory_reader_unavailable")
        self._reader = reader

    def board(self) -> Tuple[Dict[str, Any], ...]:
        return tuple(summary.to_dict() for summary in self._reader.discover_runs())

    def run(self, run_id: str) -> Any:
        from qitos.tracing.trajectory import PrivacyView

        try:
            return self._reader.read_run(
                run_id, view=PrivacyView.REDACTED_PUBLIC
            )
        except (FileNotFoundError, LookupError, OSError, RuntimeError, ValueError) as exc:
            raise QitaReadError("run_source_unavailable") from exc

    def session(self, session_id: str) -> Any:
        from qitos.tracing.trajectory import PrivacyView

        if not bool(getattr(self._reader.capabilities, "session_query", False)):
            raise QitaReadError("session_source_unavailable")
        try:
            return self._reader.read_session(
                session_id, view=PrivacyView.REDACTED_PUBLIC
            )
        except (FileNotFoundError, LookupError, OSError, RuntimeError, ValueError) as exc:
            raise QitaReadError("session_source_unavailable") from exc

    def _selected(
        self,
        *,
        run_id: Optional[str],
        session_id: Optional[str],
    ) -> Any:
        if (run_id is None) == (session_id is None):
            raise QitaReadError("exactly_one_selection_required")
        return self.run(run_id) if run_id is not None else self.session(str(session_id))

    @staticmethod
    def _result(
        name: str,
        trajectory: Any,
        records: Iterable[Any],
        *,
        unavailable_code: Optional[str] = None,
    ) -> InspectionResult:
        selected = tuple(records)
        loss = trajectory.loss
        unknown = not selected and unavailable_code is not None
        if unknown:
            from qitos.tracing.trajectory import LossEntry, LossReport

            loss = loss.merged(
                LossReport(
                    policy_id="qitos.qita/unknown",
                    entries=(
                        LossEntry(
                            unavailable_code or "fact_unavailable",
                            scope=name,
                            consequence="fact_unavailable",
                        ),
                    ),
                )
            )
        return InspectionResult(
            view=name,
            records=tuple(record.to_dict() for record in selected),
            loss=loss,
            unknown=unknown,
        )

    def timeline(
        self, *, run_id: Optional[str] = None, session_id: Optional[str] = None
    ) -> InspectionResult:
        trajectory = self._selected(run_id=run_id, session_id=session_id)
        return self._result("timeline", trajectory, trajectory.records)

    def graph(
        self, *, run_id: Optional[str] = None, session_id: Optional[str] = None
    ) -> InspectionResult:
        from qitos.tracing.trajectory import RecordKind

        trajectory = self._selected(run_id=run_id, session_id=session_id)
        return self._result(
            "graph",
            trajectory,
            (record for record in trajectory.records if record.kind == RecordKind.WORK_GRAPH),
            unavailable_code="work_graph_fact_unavailable",
        )

    def item(
        self,
        record_id: str,
        *,
        run_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> InspectionResult:
        trajectory = self._selected(run_id=run_id, session_id=session_id)
        selected = tuple(
            record for record in trajectory.records if record.record_id == record_id
        )
        if not selected:
            raise QitaReadError("trajectory_item_not_found")
        return self._result("item", trajectory, selected)

    def _by_kind(
        self,
        name: str,
        kinds: Tuple[Any, ...],
        *,
        run_id: Optional[str],
        session_id: Optional[str],
        unavailable_code: str,
    ) -> InspectionResult:
        trajectory = self._selected(run_id=run_id, session_id=session_id)
        return self._result(
            name,
            trajectory,
            (record for record in trajectory.records if record.kind in kinds),
            unavailable_code=unavailable_code,
        )

    def attempts(
        self, *, run_id: Optional[str] = None, session_id: Optional[str] = None
    ) -> InspectionResult:
        trajectory = self._selected(run_id=run_id, session_id=session_id)
        return self._result(
            "attempt",
            trajectory,
            (record for record in trajectory.records if record.attempt_id is not None),
            unavailable_code="attempt_fact_unavailable",
        )

    def ownership(
        self, *, run_id: Optional[str] = None, session_id: Optional[str] = None
    ) -> InspectionResult:
        from qitos.tracing.trajectory import RecordKind

        trajectory = self._selected(run_id=run_id, session_id=session_id)
        return self._result(
            "ownership",
            trajectory,
            (
                record
                for record in trajectory.records
                if record.kind == RecordKind.OWNERSHIP
                or record.owner_generation is not None
            ),
            unavailable_code="ownership_fact_unavailable",
        )

    def budgets(
        self, *, run_id: Optional[str] = None, session_id: Optional[str] = None
    ) -> InspectionResult:
        from qitos.tracing.trajectory import RecordKind

        return self._by_kind(
            "budget",
            (RecordKind.BUDGET,),
            run_id=run_id,
            session_id=session_id,
            unavailable_code="budget_fact_unavailable",
        )

    def sandbox(
        self, *, run_id: Optional[str] = None, session_id: Optional[str] = None
    ) -> InspectionResult:
        from qitos.tracing.trajectory import RecordKind

        return self._by_kind(
            "sandbox",
            (RecordKind.SANDBOX,),
            run_id=run_id,
            session_id=session_id,
            unavailable_code="sandbox_fact_unavailable",
        )

    def losses(
        self, *, run_id: Optional[str] = None, session_id: Optional[str] = None
    ) -> InspectionResult:
        from qitos.tracing.trajectory import RecordKind

        trajectory = self._selected(run_id=run_id, session_id=session_id)
        return self._result(
            "loss",
            trajectory,
            (
                record
                for record in trajectory.records
                if record.kind == RecordKind.LOSS or not record.loss.is_lossless
            ),
            unavailable_code="loss_fact_unavailable",
        )

    def replay(
        self,
        query: Any,
        *,
        view: Any = None,
    ) -> Tuple[Any, ...]:
        from qitos.tracing.trajectory import PrivacyView

        selected_view = view or PrivacyView.REDACTED_PUBLIC
        try:
            return tuple(self._reader.replay(query, view=selected_view))
        except (FileNotFoundError, LookupError, OSError, RuntimeError, ValueError) as exc:
            raise QitaReadError("replay_source_unavailable") from exc

    def export(
        self,
        exporter: Any,
        *,
        run_id: Optional[str] = None,
        session_id: Optional[str] = None,
        view: Any = None,
    ) -> Any:
        from qitos.tracing.trajectory import PrivacyView

        trajectory = self._selected(run_id=run_id, session_id=session_id)
        export = getattr(exporter, "export", None)
        if not callable(export):
            raise QitaReadError("trajectory_exporter_unavailable")
        return export(trajectory, view=view or PrivacyView.REDACTED_PUBLIC)

    def poll(
        self,
        *,
        run_id: str,
        after_sequence: int,
        limit: int = 256,
    ) -> Tuple[Any, ...]:
        from qitos.tracing.trajectory import TrajectoryQuery

        if limit <= 0:
            raise QitaReadError("invalid_poll_limit")
        return self.replay(
            TrajectoryQuery(
                run_id=run_id,
                after_sequence=after_sequence,
                limit=limit,
            )
        )


__all__ = ["InspectionResult", "QitaReadError", "ReadOnlyInspection"]
