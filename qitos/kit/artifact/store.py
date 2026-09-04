"""Content-addressed artifact bodies behind the existing resolver contract."""

import hashlib
import os
from pathlib import Path
import tempfile
import stat

from qitos.core.artifact import ArtifactContractError, ArtifactRef, ResolvedArtifact


class FileArtifactStore:
    """Durable local bodies; only logical references cross runtime boundaries."""

    resolver_key = "tool-result-output"

    def __init__(self, root: str | Path, *, max_artifact_bytes: int = 16 * 1024 * 1024):
        if max_artifact_bytes <= 0:
            raise ValueError("artifact bound must be positive")
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._max_bytes = max_artifact_bytes

    def put(self, reference: ArtifactRef, body: bytes) -> None:
        ResolvedArtifact(reference, body)
        if reference.resolver_key != self.resolver_key or len(body) > self._max_bytes:
            raise ArtifactContractError("artifact_store_limit", "artifact cannot be admitted")
        descriptor, temporary = tempfile.mkstemp(prefix=".artifact-", dir=self._root)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, self._root / reference.sha256, follow_symlinks=False)
            except FileExistsError:
                self.resolve(reference)
            directory = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            raise ArtifactContractError("artifact_write_failed", "artifact persistence failed") from None
        finally:
            os.unlink(temporary)

    def resolve(self, reference: ArtifactRef) -> ResolvedArtifact:
        reference.to_dict()
        if reference.resolver_key != self.resolver_key or reference.byte_length > self._max_bytes:
            raise ArtifactContractError("artifact_resolver_mismatch", "artifact cannot be resolved")
        try:
            descriptor = os.open(self._root / reference.sha256, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                    raise ArtifactContractError("artifact_special_file", "artifact body is not a regular file")
                body = handle.read(self._max_bytes + 1)
        except OSError:
            raise ArtifactContractError("missing_required_artifact", "artifact body is unavailable") from None
        return ResolvedArtifact(reference, body)

    def probe(self, reference: ArtifactRef) -> bool:
        try:
            return hashlib.sha256(self.resolve(reference).body).hexdigest() == reference.sha256
        except ArtifactContractError:
            return False
