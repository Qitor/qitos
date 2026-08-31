"""Independent structural reader used by the S3 Lane D conformance suite."""

from __future__ import annotations

from typing import Any

from qitos.tracing.readers import ReaderCapabilities, ReaderIntegrityReport, RunSummary
from qitos.tracing.sinks import project_record
from qitos.tracing.trajectory import (
    PrivacyView,
    Trajectory,
    TrajectoryQuery,
    filter_records,
)


class ThirdPartyGraphReader:
    """A reader implementation with no dependency on QitOS store classes."""

    def __init__(self, records: tuple[Any, ...]) -> None:
        self._records = records

    @property
    def capabilities(self) -> ReaderCapabilities:
        return ReaderCapabilities(
            reader_id="example.third_party_graph_reader",
            source_kind="third_party_fixture",
            supported_views=tuple(PrivacyView),
            session_query=True,
        )

    def discover_runs(self) -> tuple[RunSummary, ...]:
        run_ids = tuple(dict.fromkeys(record.run_id for record in self._records if record.run_id))
        return tuple(
            RunSummary(run_id, None, None, 0, len([r for r in self._records if r.run_id == run_id]), None)
            for run_id in run_ids
        )

    def _trajectory(self, records: tuple[Any, ...], view: PrivacyView) -> Trajectory:
        projected = tuple(project_record(record, view) for record in records)
        return Trajectory(
            records=projected,
            privacy_view=view,
            provenance={"reader_id": self.capabilities.reader_id},
        )

    def read_run(self, run_id: str, *, view: PrivacyView = PrivacyView.REDACTED_PUBLIC) -> Trajectory:
        return self._trajectory(tuple(record for record in self._records if record.run_id == run_id), view)

    def read_session(self, session_id: str, *, view: PrivacyView = PrivacyView.REDACTED_PUBLIC) -> Trajectory:
        return self._trajectory(tuple(record for record in self._records if record.session_id == session_id), view)

    def replay(self, query: TrajectoryQuery, *, view: PrivacyView = PrivacyView.REDACTED_PUBLIC) -> tuple[Any, ...]:
        return tuple(project_record(record, view) for record in filter_records(self._records, query))

    def validate_integrity(self) -> ReaderIntegrityReport:
        invalid = tuple(record.record_id for record in self._records if not record.validate_integrity())
        return ReaderIntegrityReport(not invalid, self.capabilities.source_kind, len(self._records), invalid)
