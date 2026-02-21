"""
QitOS Built-in Skills

内置技能集，提供常用的文件操作、系统命令和网络请求功能。

Usage:
    from qitos.skills import WriteFile, ReadFile, ListFiles
    from qitos.skills import RunCommand
    from qitos.skills import HTTPGet, HTTPPost
"""

from qitos.skills.file import WriteFile, ReadFile, ListFiles
from qitos.skills.library import InMemorySkillLibrary, SkillArtifact
from qitos.skills.shell import RunCommand
from qitos.skills.web import HTTPGet, HTTPPost

__all__ = [
    "WriteFile",
    "ReadFile",
    "ListFiles",
    "InMemorySkillLibrary",
    "SkillArtifact",
    "RunCommand",
    "HTTPGet",
    "HTTPPost",
]
