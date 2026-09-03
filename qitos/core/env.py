"""Environment abstraction contracts for QitOS."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class EnvCapabilityError(RuntimeError):
    """Typed refusal or failure at an environment capability boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = str(code)
        super().__init__(f"{self.code}: {message}")


@dataclass(frozen=True)
class FileSnapshot:
    """Portable file identity used for optimistic, atomic mutation."""

    path: str
    sha256: str
    byte_length: int
    version: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "byte_length": self.byte_length,
            "version": self.version,
        }


@dataclass(frozen=True)
class ProcessHandle:
    """Opaque environment-owned bounded-process reference."""

    process_id: str
    owner_generation: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "process_id": self.process_id,
            "owner_generation": self.owner_generation,
        }


@dataclass
class EnvSpec:
    """Declarative environment requirement attached to a task."""

    type: str
    config: Dict[str, Any] = field(default_factory=dict)
    required_tools: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EnvObservation:
    """Structured environment observation payload."""

    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EnvStepResult:
    """Structured result emitted by one environment step."""

    observation: EnvObservation = field(default_factory=EnvObservation)
    done: bool = False
    reward: Optional[float] = None
    info: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class Env(ABC):
    """Canonical environment interface for agent-world interaction."""

    name: str = "env"
    version: str = "1.0"

    @abstractmethod
    def reset(
        self, task: Any = None, workspace: Optional[str] = None, **kwargs: Any
    ) -> EnvObservation:
        """Initialize environment state for a task and return first observation."""

    @abstractmethod
    def observe(self, state: Any = None) -> EnvObservation:
        """Return current environment observation without applying actions."""

    @abstractmethod
    def step(self, action: Any, state: Any = None) -> EnvStepResult:
        """Apply one action to environment and return step result."""

    def setup(
        self, task: Any = None, workspace: Optional[str] = None, **kwargs: Any
    ) -> None:
        """Prepare env before reset/run."""
        return None

    def health_check(self) -> Dict[str, Any]:
        """Return health probe result used by runtime preflight."""
        return {"ok": True}

    def get_ops(self, group: str) -> Any:
        """Return concrete ops implementation for one capability group."""
        return None

    def has_ops(self, group: str) -> bool:
        """Whether this env provides one capability group."""
        return self.get_ops(group) is not None

    def is_terminal(
        self, state: Any = None, last_result: Optional[EnvStepResult] = None
    ) -> bool:
        """Return whether environment should terminate the episode."""
        if last_result is None:
            return False
        return bool(last_result.done)

    def close(self) -> None:
        """Release environment resources."""
        return None

    def teardown(self) -> None:
        """Symmetric shutdown hook called by runtime."""
        self.close()


class FileSystemCapability(ABC):
    """Filesystem capability contract used by env implementations."""

    @abstractmethod
    def read_text(self, path: str) -> str:
        """Read UTF-8 text from file path."""

    @abstractmethod
    def write_text(self, path: str, content: str) -> None:
        """Write UTF-8 text to file path."""

    @abstractmethod
    def list_files(self, path: str = ".", limit: int = 200) -> List[str]:
        """List files relative to capability root."""

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check if path exists within capability scope."""

    def snapshot(self, path: str) -> FileSnapshot:
        """Return a content/version snapshot when the backend supports it."""
        raise EnvCapabilityError(
            "unsupported_capability", "file snapshots are not supported"
        )

    def atomic_write_text(
        self,
        path: str,
        content: str,
        *,
        expected_sha256: Optional[str] = None,
    ) -> FileSnapshot:
        """Atomically write text, optionally rejecting a stale snapshot."""
        raise EnvCapabilityError(
            "unsupported_capability", "atomic file writes are not supported"
        )


class CommandCapability(ABC):
    """Command execution capability contract used by env implementations."""

    @abstractmethod
    def run(self, command: str, timeout: int = 30) -> Dict[str, Any]:
        """Run one command and return standardized result payload."""


class ProcessControlCapability(ABC):
    """Bounded control of processes created and owned by one Env."""

    @abstractmethod
    def start(self, command: str) -> ProcessHandle:
        """Start one environment-owned process and return an opaque handle."""

    @abstractmethod
    def poll(self, handle: ProcessHandle) -> Dict[str, Any]:
        """Return bounded current output and terminal state."""

    @abstractmethod
    def terminate(self, handle: ProcessHandle, timeout: int = 5) -> Dict[str, Any]:
        """Request termination of an owned process and report what is proven."""

    def close(self) -> None:
        """Release all processes owned by this capability."""
        return None


class TerminalCapability(ABC):
    """Interactive terminal capability contract used by env implementations."""

    @abstractmethod
    def send_keys(
        self,
        keys: str | list[str],
        min_timeout_sec: float = 0.0,
        block: bool = False,
        max_timeout_sec: float = 180.0,
    ) -> Dict[str, Any]:
        """Send raw keystrokes to the terminal and optionally wait."""

    @abstractmethod
    def capture_screen(self) -> str:
        """Return the currently visible terminal screen."""

    @abstractmethod
    def capture_buffer(self) -> str:
        """Return the full terminal scrollback buffer when available."""

    @abstractmethod
    def get_incremental_output(self) -> str:
        """Return new output since the previous capture, or the current screen."""

    @abstractmethod
    def is_session_alive(self) -> bool:
        """Whether the interactive terminal session is still alive."""

    @abstractmethod
    def get_timestamp(self) -> float | None:
        """Return a backend-specific timestamp if available."""


class GUIObserverCapability(ABC):
    """GUI observation capability for multimodal environments."""

    @abstractmethod
    def capture_observation(self, state: Any = None) -> Dict[str, Any]:
        """Return a normalized GUI observation pack payload."""


class GUIControllerCapability(ABC):
    """GUI control capability for click/type/scroll style actions."""

    @abstractmethod
    def perform(self, action: Dict[str, Any], state: Any = None) -> Dict[str, Any]:
        """Apply one GUI action and return a structured result."""


class OCRCapability(ABC):
    """OCR capability contract for multimodal environments."""

    @abstractmethod
    def extract_text(self, source: Any) -> List[Dict[str, Any]]:
        """Extract OCR rows or spans from the provided source."""


class GroundingCapability(ABC):
    """Grounding capability contract for GUI element linking."""

    @abstractmethod
    def ground(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """Return grounding metadata for a multimodal observation pack."""


__all__ = [
    "EnvSpec",
    "EnvObservation",
    "EnvStepResult",
    "Env",
    "FileSystemCapability",
    "CommandCapability",
    "TerminalCapability",
    "GUIObserverCapability",
    "GUIControllerCapability",
    "OCRCapability",
    "GroundingCapability",
]
