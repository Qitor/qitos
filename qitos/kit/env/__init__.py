"""Concrete environment implementations for QitOS."""

from .desktop import ContainerDesktopProvider, DesktopEnv, MockDesktopProvider
from .docker_env import DockerEnv, DockerEnvScheduler
from .docker_qualification import (
    SandboxIdentity,
    SandboxQualificationReceipt,
    qualify_docker_environment,
)
from .host_env import HostEnv
from .repo_env import RepoEnv
from .screenshot_env import ScreenshotEnv, ScreenshotObserverOps, MockGUIControllerOps
from .text_web_env import TextWebEnv, TextWebBrowserOps
from .tmux_env import TmuxEnv, TmuxTerminalCapability
from .web import MockBrowserProvider, PlaywrightBrowserProvider, WebBrowserEnv
from .sandbox import (
    DockerSandboxBackend,
    SandboxAllocation,
    SandboxBackend,
    SandboxCapabilities,
    SandboxCleanupReceipt,
    SandboxExecutionReceipt,
    SandboxHandle,
    SandboxLease,
    SandboxPolicy,
    SandboxResourceLimits,
    SandboxSnapshotComponent,
    assert_sandbox_backend_conformance,
    run_sandbox_backend_conformance,
)

__all__ = [
    "HostEnv",
    "DesktopEnv",
    "ContainerDesktopProvider",
    "MockDesktopProvider",
    "DockerEnv",
    "DockerEnvScheduler",
    "DockerSandboxBackend",
    "SandboxAllocation",
    "SandboxBackend",
    "SandboxCapabilities",
    "SandboxCleanupReceipt",
    "SandboxExecutionReceipt",
    "SandboxHandle",
    "SandboxIdentity",
    "SandboxLease",
    "SandboxPolicy",
    "SandboxQualificationReceipt",
    "SandboxResourceLimits",
    "SandboxSnapshotComponent",
    "assert_sandbox_backend_conformance",
    "run_sandbox_backend_conformance",
    "qualify_docker_environment",
    "RepoEnv",
    "ScreenshotEnv",
    "ScreenshotObserverOps",
    "MockGUIControllerOps",
    "TextWebEnv",
    "TextWebBrowserOps",
    "TmuxEnv",
    "TmuxTerminalCapability",
    "WebBrowserEnv",
    "MockBrowserProvider",
    "PlaywrightBrowserProvider",
]
