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

__all__ = [
    "HostEnv",
    "DesktopEnv",
    "ContainerDesktopProvider",
    "MockDesktopProvider",
    "DockerEnv",
    "DockerEnvScheduler",
    "SandboxIdentity",
    "SandboxQualificationReceipt",
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
