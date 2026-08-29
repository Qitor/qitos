#!/usr/bin/env python3
"""Execute the repository's contribution-time tool schema qualification."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib
import inspect
import json
from pathlib import Path
import pkgutil
import sys
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qitos.core.tool import BaseTool, ToolSpec
from qitos.core.tool_registry import ToolRegistry


@dataclass(frozen=True)
class QualificationReport:
    package: str
    modules_imported: int
    class_definitions: int
    class_tools_qualified: int
    class_tools_requiring_construction_args: int
    registered_class_tools: int
    fixture_specs_qualified: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "package": self.package,
            "modules_imported": self.modules_imported,
            "class_definitions": self.class_definitions,
            "class_tools_qualified": self.class_tools_qualified,
            "class_tools_requiring_construction_args": (
                self.class_tools_requiring_construction_args
            ),
            "registered_class_tools": self.registered_class_tools,
            "fixture_specs_qualified": self.fixture_specs_qualified,
        }


class ToolSchemaQualificationError(ValueError):
    """A stable contribution-gate failure with an inventory location."""

    def __init__(self, code: str, location: str, detail: str) -> None:
        self.code = code
        self.location = location
        self.detail = detail
        super().__init__(f"{code}: {location}: {detail}")


def _json_tree(value: Any, *, location: str) -> None:
    try:
        json.dumps(value, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ToolSchemaQualificationError(
            "non_json_schema_value", location, str(exc)
        ) from exc


def qualify_tool_spec(spec: ToolSpec, *, location: str) -> None:
    """Validate the contribution-facing shape common to registered ToolSpecs."""

    if not isinstance(spec, ToolSpec):
        raise ToolSchemaQualificationError(
            "invalid_tool_spec_type", location, "expected ToolSpec"
        )
    if not isinstance(spec.name, str) or not spec.name.strip():
        raise ToolSchemaQualificationError(
            "invalid_tool_name", location, "name must be a non-empty string"
        )
    if not isinstance(spec.description, str) or not spec.description.strip():
        raise ToolSchemaQualificationError(
            "invalid_tool_description",
            location,
            "description must be a non-empty string",
        )
    if not isinstance(spec.parameters, dict):
        raise ToolSchemaQualificationError(
            "invalid_tool_parameters", location, "parameters must be an object"
        )
    for name, schema in spec.parameters.items():
        if not isinstance(name, str) or not name:
            raise ToolSchemaQualificationError(
                "invalid_parameter_name", location, "parameter keys must be strings"
            )
        if not isinstance(schema, dict):
            raise ToolSchemaQualificationError(
                "invalid_parameter_schema",
                f"{location}.parameters.{name}",
                "parameter schema must be an object",
            )
    if not isinstance(spec.required, list) or any(
        not isinstance(name, str) for name in spec.required
    ):
        raise ToolSchemaQualificationError(
            "invalid_required_parameters",
            location,
            "required must be a list of strings",
        )
    unknown_required = sorted(set(spec.required).difference(spec.parameters))
    if unknown_required:
        raise ToolSchemaQualificationError(
            "unknown_required_parameter",
            location,
            f"required names are not declared: {unknown_required}",
        )
    if not isinstance(spec.input_schema, dict):
        raise ToolSchemaQualificationError(
            "invalid_input_schema", location, "input_schema must be an object"
        )
    if spec.input_schema.get("type") != "object":
        raise ToolSchemaQualificationError(
            "invalid_input_schema_root",
            location,
            "input_schema root type must be object",
        )
    if spec.output_schema is not None and not isinstance(spec.output_schema, dict):
        raise ToolSchemaQualificationError(
            "invalid_output_schema", location, "output_schema must be an object"
        )
    _json_tree(spec.parameters, location=f"{location}.parameters")
    _json_tree(spec.input_schema, location=f"{location}.input_schema")
    _json_tree(spec.output_schema, location=f"{location}.output_schema")


def _required_constructor_parameters(tool_class: type[BaseTool]) -> list[str]:
    try:
        signature = inspect.signature(tool_class)
    except (TypeError, ValueError) as exc:
        raise ToolSchemaQualificationError(
            "uninspectable_tool_constructor",
            f"{tool_class.__module__}.{tool_class.__qualname__}",
            str(exc),
        ) from exc
    return [
        parameter.name
        for parameter in signature.parameters.values()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind
        in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        }
    ]


def qualify_repository_tools(package_name: str = "qitos.kit.tool") -> QualificationReport:
    """Import the real tool inventory and qualify constructible public class tools."""

    package = importlib.import_module(package_name)
    package_path = getattr(package, "__path__", None)
    if package_path is None:
        raise ToolSchemaQualificationError(
            "invalid_tool_package", package_name, "package has no import path"
        )

    module_names = [package_name]
    module_names.extend(
        module_info.name
        for module_info in pkgutil.walk_packages(
            package_path, prefix=f"{package_name}."
        )
    )

    modules_imported = 0
    class_definitions = 0
    class_tools_qualified = 0
    requiring_args = 0
    registered_class_tools = 0
    for module_name in module_names:
        module = importlib.import_module(module_name)
        modules_imported += 1
        for attribute_name, value in vars(module).items():
            if attribute_name.startswith("_"):
                continue
            if not inspect.isclass(value) or value is BaseTool:
                continue
            if not issubclass(value, BaseTool) or inspect.isabstract(value):
                continue
            if value.__module__ != module_name:
                continue
            class_definitions += 1
            if _required_constructor_parameters(value):
                requiring_args += 1
                continue
            location = f"{module_name}.{value.__qualname__}"
            try:
                tool = value()
            except Exception as exc:
                raise ToolSchemaQualificationError(
                    "tool_construction_failed", location, str(exc)
                ) from exc
            qualify_tool_spec(tool.spec, location=location)
            class_tools_qualified += 1

            registry = ToolRegistry()
            try:
                registry.register(tool)
            except Exception as exc:
                raise ToolSchemaQualificationError(
                    "tool_registration_failed", location, str(exc)
                ) from exc
            if registry.get(tool.spec.name) is None:
                raise ToolSchemaQualificationError(
                    "registered_tool_missing",
                    location,
                    "registry could not resolve the registered class tool",
                )
            registered_class_tools += 1

    if modules_imported < 2:
        raise ToolSchemaQualificationError(
            "empty_tool_module_inventory",
            package_name,
            "expected package discovery to import at least two modules",
        )
    if class_definitions == 0 or class_tools_qualified == 0:
        raise ToolSchemaQualificationError(
            "empty_class_tool_inventory",
            package_name,
            "no constructible public BaseTool subclasses were qualified",
        )
    if registered_class_tools != class_tools_qualified:
        raise ToolSchemaQualificationError(
            "incomplete_registration_inventory",
            package_name,
            "every qualified class tool must pass the real ToolRegistry path",
        )
    return QualificationReport(
        package=package_name,
        modules_imported=modules_imported,
        class_definitions=class_definitions,
        class_tools_qualified=class_tools_qualified,
        class_tools_requiring_construction_args=requiring_args,
        registered_class_tools=registered_class_tools,
    )


def _specs_from_fixture(path: Path) -> Iterable[tuple[str, ToolSpec]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolSchemaQualificationError(
            "invalid_spec_fixture", path.as_posix(), str(exc)
        ) from exc
    if not isinstance(document, dict) or set(document) != {"specs"}:
        raise ToolSchemaQualificationError(
            "invalid_spec_fixture",
            path.as_posix(),
            "fixture must be an object containing only a specs list",
        )
    specs = document["specs"]
    if not isinstance(specs, list) or not specs:
        raise ToolSchemaQualificationError(
            "invalid_spec_fixture", path.as_posix(), "specs must be a non-empty list"
        )
    allowed = {
        "name",
        "description",
        "parameters",
        "required",
        "input_schema",
        "output_schema",
    }
    for index, payload in enumerate(specs):
        location = f"{path.as_posix()}#specs[{index}]"
        if not isinstance(payload, dict) or not set(payload).issubset(allowed):
            raise ToolSchemaQualificationError(
                "invalid_spec_fixture_entry",
                location,
                "spec entry must be an object containing supported ToolSpec fields",
            )
        try:
            yield location, ToolSpec(**payload)
        except TypeError as exc:
            raise ToolSchemaQualificationError(
                "invalid_spec_fixture_entry", location, str(exc)
            ) from exc


def qualify_fixture(path: Path) -> QualificationReport:
    count = 0
    for location, spec in _specs_from_fixture(path):
        qualify_tool_spec(spec, location=location)
        count += 1
    return QualificationReport(
        package="fixture",
        modules_imported=0,
        class_definitions=0,
        class_tools_qualified=0,
        class_tools_requiring_construction_args=0,
        registered_class_tools=0,
        fixture_specs_qualified=count,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", default="qitos.kit.tool")
    parser.add_argument(
        "--spec-fixture",
        type=Path,
        help="validate a controlled ToolSpec JSON fixture instead of repository tools",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = (
            qualify_fixture(args.spec_fixture)
            if args.spec_fixture is not None
            else qualify_repository_tools(args.package)
        )
    except ToolSchemaQualificationError as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "code": exc.code,
                    "location": exc.location,
                    "detail": exc.detail,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps({"status": "qualified", **report.to_dict()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
