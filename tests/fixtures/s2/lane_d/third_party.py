"""Independent third-party-style fakes used by Lane D conformance tests."""

from __future__ import annotations

from typing import Iterable

from qitos.tracing.sinks import (
    BackpressurePolicy,
    DurabilityReceipt,
    DurabilityStatus,
    SinkCapabilities,
)
from qitos.tracing.store import (
    IndexRebuildReport,
    StorageMeasurement,
    StoreCapabilities,
    StoreConflictError,
    StoreIntegrityReport,
)
from qitos.tracing.trajectory import (
    STORE_SCHEMA_VERSION,
    ArtifactRef,
    LossReport,
    PrivacyView,
    Trajectory,
    TrajectoryQuery,
    TrajectoryRecord,
    canonical_json_bytes,
    filter_records,
)


class ThirdPartySink:
    """Structural EventSink implementation without QitOS inheritance."""

    def __init__(self) -> None:
        self.items: list[TrajectoryRecord] = []
        self.closed = False

    @property
    def capabilities(self) -> SinkCapabilities:
        return SinkCapabilities(
            sink_id="third_party.fake_sink",
            durability_receipts=True,
            backpressure=BackpressurePolicy.FAIL,
        )

    def receive(self, record: TrajectoryRecord) -> DurabilityReceipt:
        if self.closed:
            raise RuntimeError("closed")
        self.items.append(TrajectoryRecord.from_dict(record.to_dict()))
        return DurabilityReceipt(
            status=DurabilityStatus.ACCEPTED,
            accepted_count=1,
        )

    def flush(self) -> DurabilityReceipt:
        if self.closed:
            raise RuntimeError("closed")
        return DurabilityReceipt(
            status=DurabilityStatus.PERSISTED,
            accepted_count=len(self.items),
            persisted_count=len(self.items),
        )

    def close(self) -> DurabilityReceipt:
        self.closed = True
        return DurabilityReceipt(
            status=DurabilityStatus.PERSISTED,
            persisted_count=len(self.items),
        )


class ThirdPartyStore:
    """Independent in-memory TrajectoryStore implementation."""

    def __init__(self) -> None:
        self.items: list[TrajectoryRecord] = []
        self.closed = False

    @property
    def capabilities(self) -> StoreCapabilities:
        return StoreCapabilities(
            store_id="third_party.fake_store",
            atomic_batch=True,
            durable=False,
        )

    def append(self, record: TrajectoryRecord) -> DurabilityReceipt:
        return self.append_batch((record,))

    def append_batch(
        self, records: Iterable[TrajectoryRecord]
    ) -> DurabilityReceipt:
        if self.closed:
            raise RuntimeError("closed")
        batch = tuple(records)
        existing = {item.record_id for item in self.items}
        incoming = [item.record_id for item in batch]
        if len(set(incoming)) != len(incoming) or existing.intersection(incoming):
            raise StoreConflictError("duplicate record")
        if any(not item.validate_integrity() for item in batch):
            raise ValueError("invalid record")
        start = len(self.items)
        staged = [item.with_sequence(start + index) for index, item in enumerate(batch)]
        self.items = self.items + staged
        return DurabilityReceipt(
            status=DurabilityStatus.ACCEPTED,
            accepted_count=len(batch),
        )

    def query(self, query: TrajectoryQuery) -> tuple[TrajectoryRecord, ...]:
        return tuple(
            TrajectoryRecord.from_dict(item.to_dict())
            for item in filter_records(self.items, query)
        )

    def read_run(self, run_id: str) -> Trajectory:
        return Trajectory(
            records=self.query(TrajectoryQuery(run_id=run_id)),
            metadata={"store_id": self.capabilities.store_id},
            provenance={"source": "third_party_fake"},
            privacy_view=PrivacyView.RAW_PRIVATE,
            loss=LossReport(policy_id="qitos.loss/none"),
        )

    def read_session(self, session_id: str) -> Trajectory:
        return Trajectory(
            records=self.query(TrajectoryQuery(session_id=session_id)),
            metadata={"store_id": self.capabilities.store_id},
            provenance={"source": "third_party_fake"},
            privacy_view=PrivacyView.RAW_PRIVATE,
            loss=LossReport(policy_id="qitos.loss/none"),
        )

    def replay(self, query: TrajectoryQuery) -> tuple[TrajectoryRecord, ...]:
        return self.query(query)

    def artifact_refs(self, query: TrajectoryQuery) -> tuple[ArtifactRef, ...]:
        refs = {}
        for record in self.query(query):
            for ref in record.artifact_refs:
                refs[ref.sha256] = ref
        return tuple(refs.values())

    def validate_integrity(self) -> StoreIntegrityReport:
        invalid = tuple(
            record.record_id
            for record in self.items
            if not record.validate_integrity()
        )
        sequences = [record.sequence for record in self.items]
        gaps = tuple(
            index for index, value in enumerate(sequences) if value != index
        )
        return StoreIntegrityReport(
            valid=not invalid and not gaps,
            record_count=len(self.items),
            invalid_record_ids=invalid,
            sequence_gaps=gaps,
        )

    def rebuild_index(self) -> IndexRebuildReport:
        return IndexRebuildReport(
            record_count=len(self.items),
            run_count=len({item.run_id for item in self.items if item.run_id}),
            session_count=len(
                {item.session_id for item in self.items if item.session_id}
            ),
            work_item_count=len(
                {item.work_item_id for item in self.items if item.work_item_id}
            ),
        )

    def measure_storage(self) -> StorageMeasurement:
        payload = [item.to_dict() for item in self.items]
        return StorageMeasurement(
            storage_schema=STORE_SCHEMA_VERSION,
            record_count=len(self.items),
            size_bytes=len(canonical_json_bytes(payload)),
            measurement_kind="third_party_fake_json_bytes",
        )

    def flush(self) -> DurabilityReceipt:
        return DurabilityReceipt(
            status=DurabilityStatus.ACCEPTED,
            accepted_count=len(self.items),
        )

    def close(self) -> DurabilityReceipt:
        self.closed = True
        return DurabilityReceipt(
            status=DurabilityStatus.ACCEPTED,
            accepted_count=len(self.items),
        )
