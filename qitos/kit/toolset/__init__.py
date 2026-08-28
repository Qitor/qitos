"""Scenario-oriented preset toolsets and registry builders."""

from __future__ import annotations

from qitos.kit.tool.notebook import NotebookToolSet
from qitos.kit.tool.report import ReportToolSet
from qitos.kit.tool.skill import SkillToolSet
from qitos.kit.tool.task import TaskToolSet
from qitos.kit.tool.thinking import ThinkingToolSet
from qitos.kit.tool.toolset import BaseToolSet, StaticToolSet, ToolSet, toolset_from_tools
from .advanced import AdvancedCodingToolSet, advanced_coding_tools
from .builders import math_tools
from .codebase import CodebaseToolSet, FilesToolSet, codebase_tools
from .computer_use import ComputerUseToolSet, computer_use_tools
from .coding import CodingToolSet, FullCodingToolSet, coding_tools
from .editor import EditorToolSet, editor_tools
from .epub import EpubToolSet, epub_tools
from .notebook import notebook_tools
from .report import report_tools
from .task import task_tools
from .thinking import thinking_tools
from .web import WebToolSet, web_tools

__all__ = [
    "AdvancedCodingToolSet",
    "BaseToolSet",
    "CodebaseToolSet",
    "ComputerUseToolSet",
    "CodingToolSet",
    "EditorToolSet",
    "EpubToolSet",
    "FilesToolSet",
    "FullCodingToolSet",
    "NotebookToolSet",
    "ReportToolSet",
    "SkillToolSet",
    "StaticToolSet",
    "TaskToolSet",
    "ThinkingToolSet",
    "ToolSet",
    "WebToolSet",
    "advanced_coding_tools",
    "codebase_tools",
    "computer_use_tools",
    "coding_tools",
    "editor_tools",
    "epub_tools",
    "math_tools",
    "notebook_tools",
    "report_tools",
    "task_tools",
    "thinking_tools",
    "toolset_from_tools",
    "web_tools",
]


def __getattr__(name: str):
    """Load security-research compatibility exports only on explicit access.

    Importing ``qitos.kit`` reaches this package while resolving the curated
    coding toolsets.  Eagerly importing the deprecated security compatibility
    modules here made that otherwise-safe import load the experimental
    security implementation as a side effect.  The names remain available for
    compatibility, but accessing either one is now the opt-in boundary.
    """

    if name == "SecurityAuditToolSet":
        from qitos.kit.tool.security_audit import SecurityAuditToolSet

        return SecurityAuditToolSet
    if name == "security_audit_tools":
        from .security_audit import security_audit_tools

        return security_audit_tools
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
