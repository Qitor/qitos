"""Parser presets."""

from __future__ import annotations

from qitos.core.parser import JsonDecisionParser, ReActTextParser, XmlDecisionParser


def react_parser() -> ReActTextParser:
    return ReActTextParser()


def json_parser() -> JsonDecisionParser:
    return JsonDecisionParser()


def xml_parser() -> XmlDecisionParser:
    return XmlDecisionParser()


__all__ = ["react_parser", "json_parser", "xml_parser"]
