"""Convert MCP JSON Schema to QitOS ToolSpec.

MCP tools describe their inputs using JSON Schema objects that follow the
conventions of the MCP specification.  QitOS uses ``ToolSpec`` with a flat
``parameters`` dict and a ``required`` list.  This module bridges the two.

Key conversion rules:

- ``properties`` entries become entries in ``ToolSpec.parameters``.
- ``required`` arrays map directly.
- Nested ``$defs`` / ``definitions`` are resolved inline for simple cases.
- ``anyOf`` with a null type (nullable) is unwrapped to the non-null type.
- ``additionalProperties: false`` on objects is preserved as a hint.
- Parameter descriptions are extracted from the per-property ``description`` key.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional

from ..core.tool import ToolPermission, ToolSpec
from ..core.tool_runtime import ToolEffectDeclaration
from .server import MCPToolInfo


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def convert_mcp_schema_to_tool_spec(
    mcp_tool: MCPToolInfo,
    name_prefix: Optional[str] = None,
) -> ToolSpec:
    """Convert an ``MCPToolInfo`` into a QitOS ``ToolSpec``.

    :param mcp_tool: The MCP tool descriptor.
    :param name_prefix: Optional prefix to avoid name collisions across
        multiple MCP servers.  When provided, the tool name becomes
        ``{prefix}__{original_name}``.
    :returns: A ``ToolSpec`` suitable for constructing a ``FunctionTool``.
    """
    tool_name = mcp_tool.name
    if name_prefix:
        tool_name = f"{name_prefix}__{tool_name}"

    schema = deepcopy(mcp_tool.input_schema) if mcp_tool.input_schema else {}

    # Resolve $defs / definitions so we can inline simple ref patterns.
    defs = _extract_defs(schema)

    properties: Dict[str, Any] = schema.get("properties", {})
    required_list: List[str] = list(schema.get("required", []))

    parameters: Dict[str, Dict[str, Any]] = {}
    for param_name, param_schema in properties.items():
        resolved = _resolve_refs(param_schema, defs)
        parameters[param_name] = _convert_property(resolved)

    # Build the full input_schema for ToolSpec (preserving the original MCP schema
    # shape but with resolved refs for the parameters sub-dict).
    resolved_properties: Dict[str, Any] = {}
    for param_name, param_schema in properties.items():
        resolved_properties[param_name] = _resolve_refs(param_schema, defs)

    input_schema = {
        "type": "object",
        "properties": resolved_properties,
        "required": required_list,
    }
    # Preserve additionalProperties if present.
    if "additionalProperties" in schema:
        input_schema["additionalProperties"] = schema["additionalProperties"]

    return ToolSpec(
        name=tool_name,
        description=mcp_tool.description or "",
        parameters=parameters,
        required=required_list,
        input_schema=input_schema,
        # MCP 2024-11-05 schemas do not reliably declare effects.  Unknown
        # remote authority is conservative: policy must explicitly admit it.
        permissions=ToolPermission(
            filesystem_read=True,
            filesystem_write=True,
            network=True,
            command=True,
        ),
        read_only=False,
        concurrency_safe=False,
        needs_approval=True,
        effect=ToolEffectDeclaration(
            effect_ref=f"mcp:{tool_name}",
            metadata={"kind": "remote_mcp_request"},
        ),
    )


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _extract_defs(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Pull $defs and definitions out of a schema into a flat lookup dict."""
    defs: Dict[str, Any] = {}
    for key in ("$defs", "definitions"):
        section = schema.get(key, {})
        if isinstance(section, dict):
            defs.update(section)
    return defs


def _resolve_refs(schema: Any, defs: Dict[str, Any], depth: int = 0) -> Any:
    """Recursively resolve ``$ref`` pointers using the defs dict.

    Guarded against infinite recursion (max depth 10).
    """
    if depth > 10:
        return schema
    if isinstance(schema, dict):
        if "$ref" in schema:
            ref_path = schema["$ref"]
            # Handle #/$defs/Name or #/definitions/Name patterns
            if ref_path.startswith("#/"):
                parts = ref_path[2:].split("/")
                resolved = defs
                for part in parts:
                    if part in ("$defs", "definitions"):
                        continue
                    if isinstance(resolved, dict):
                        resolved = resolved.get(part, {})
                    else:
                        return schema
                if resolved and isinstance(resolved, dict):
                    return _resolve_refs(resolved, defs, depth + 1)
            return schema
        return {k: _resolve_refs(v, defs, depth + 1) for k, v in schema.items()}
    if isinstance(schema, list):
        return [_resolve_refs(item, defs, depth + 1) for item in schema]
    return schema


def _convert_property(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a single JSON Schema property to a QitOS parameter dict.

    Returns a dict with at least ``type`` and ``description`` keys.
    Handles: string, integer, number, boolean, array, object, anyOf (nullable),
    and falls back to ``"any"`` for unknown patterns.
    """
    result: Dict[str, Any] = {}

    # Handle anyOf with nullable (e.g. [{"type": "string"}, {"type": "null"}])
    if "anyOf" in schema:
        non_null = [s for s in schema["anyOf"] if not _is_null_type(s)]
        if len(non_null) == 1:
            # Nullable: use the non-null branch but mark it as nullable
            converted = _convert_property(non_null[0])
            converted["nullable"] = True
            return converted
        # Multiple non-null options: fall through to type inference
        if non_null:
            converted = _convert_property(non_null[0])
            return converted

    # Handle allOf by merging (later parts override earlier ones)
    if "allOf" in schema:
        parts = schema["allOf"]
        if len(parts) == 1:
            return _convert_property(parts[0])
        merged: Dict[str, Any] = {}
        for part in parts:
            converted = _convert_property(part)
            # Only merge keys that have meaningful (non-default) values so that
            # a later allOf element without a "type" does not overwrite an
            # earlier one that had it.
            for k, v in converted.items():
                if v is not None and v != "" and v != "any":
                    merged[k] = v
                elif k not in merged:
                    merged[k] = v
        return merged

    # Handle oneOf by picking the first variant
    if "oneOf" in schema:
        variants = schema["oneOf"]
        if variants:
            return _convert_property(variants[0])

    # Map JSON Schema type to QitOS type string
    type_str = _map_type(schema)
    result["type"] = type_str
    result["description"] = schema.get("description", "")

    # String format hint
    if type_str == "string" and "format" in schema:
        result["format"] = schema["format"]

    # Enum values
    if "enum" in schema:
        result["enum"] = list(schema["enum"])

    # Default value
    if "default" in schema:
        result["default"] = schema["default"]

    # Array items
    if type_str == "array" and "items" in schema:
        items_schema = schema["items"]
        if isinstance(items_schema, dict):
            result["items"] = _convert_property(items_schema)

    # Object properties
    if type_str == "object":
        if "properties" in schema and isinstance(schema["properties"], dict):
            result["properties"] = {
                k: _convert_property(v) for k, v in schema["properties"].items()
            }
        if "additionalProperties" in schema:
            result["additionalProperties"] = schema["additionalProperties"]

    return result


def _map_type(schema: Dict[str, Any]) -> str:
    """Map a JSON Schema type string to QitOS type string."""
    json_type = schema.get("type", "any")
    mapping = {
        "string": "string",
        "integer": "integer",
        "number": "number",
        "boolean": "boolean",
        "array": "array",
        "object": "object",
        "null": "any",
    }
    return mapping.get(json_type, "any")


def _is_null_type(schema: Any) -> bool:
    """Check if a schema represents the null type."""
    if isinstance(schema, dict):
        return schema.get("type") == "null"
    return False
