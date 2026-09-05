"""Operation work counters; byte verification is distinct from decoding."""
from dataclasses import dataclass


@dataclass
class TrajectoryWork:
    read_bytes: int = 0
    hash_bytes: int = 0
    decoded_records: int = 0
    copied_records: int = 0
    retained_records: int = 0
    peak_retained_records: int = 0
    visited_index_entries: int = 0
    written_index_entries: int = 0
    fsync_calls: int = 0

    def retain(self, count: int) -> None:
        self.retained_records = count
        self.peak_retained_records = max(self.peak_retained_records, count)
