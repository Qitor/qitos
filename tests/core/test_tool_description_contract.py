from qitos.core.tool import BaseTool, FunctionTool, ToolMeta, ToolSpec
from qitos.core.tool_registry import ToolRegistry
from qitos.protocols import render_react_tool_schema


class _ExplicitTool(BaseTool):
    def __init__(self) -> None:
        super().__init__(
            ToolSpec(
                name="explicit",
                description="Authored model-facing contract.",
                prompt="Long prompt contract.",
            )
        )

    def execute(self, args, runtime_context=None):
        """Implementation detail that must not replace the contract."""
        return args


class _FallbackTool(BaseTool):
    def __init__(self) -> None:
        super().__init__(ToolSpec(name="fallback", description=""))

    def execute(self, args, runtime_context=None):
        """Fallback description from the implementation docstring."""
        return args


def _documented_function(value: str) -> str:
    """Function docstring fallback."""
    return value


def test_explicit_tool_spec_description_and_prompt_are_preserved() -> None:
    tool = _ExplicitTool()
    assert tool.spec.description == "Authored model-facing contract."
    assert tool.spec.prompt == "Long prompt contract."

    registry = ToolRegistry().register(tool)
    native = registry.get_all_specs()[0]["function"]
    assert native["description"] == "Authored model-facing contract."
    rendered = render_react_tool_schema(registry)
    assert "Long prompt contract." in rendered
    assert "Implementation detail" not in rendered


def test_blank_tool_spec_description_uses_docstring_fallback() -> None:
    assert _FallbackTool().spec.description == (
        "Fallback description from the implementation docstring."
    )


def test_function_tool_explicit_metadata_wins_over_docstring() -> None:
    tool = FunctionTool(
        _documented_function,
        meta=ToolMeta(description="Explicit function contract."),
    )
    assert tool.spec.description == "Explicit function contract."


def test_function_tool_uses_docstring_without_explicit_metadata() -> None:
    tool = FunctionTool(_documented_function)
    assert tool.spec.description == "Function docstring fallback."


def test_strip_param_docs_drops_continuation_lines_but_keeps_dedented_prose() -> None:
    from qitos.core.tool import _strip_param_docs

    doc = (
        "Summarize a file.\n"
        "\n"
        "Longer prose about behavior.\n"
        "\n"
        ":param path: File to summarize.\n"
        "    May be relative to the workspace root.\n"
        "    Continuation without a colon is still part of the param.\n"
        ":returns: The file summary.\n"
        "\n"
        "Trailing note after the param block.\n"
    )

    stripped = _strip_param_docs(doc)

    assert "Summarize a file." in stripped
    assert "Longer prose about behavior." in stripped
    assert ":param" not in stripped
    assert "May be relative to the workspace root." not in stripped
    assert "Continuation without a colon" not in stripped
    assert ":returns" not in stripped
    assert "Trailing note after the param block." in stripped


def test_build_tool_spec_fills_param_descriptions_from_docstring() -> None:
    from qitos.core.tool import build_tool_spec
    from qitos.core.tool import ToolMeta

    def documented(path: str, limit: int = 5) -> str:
        """Summarize a file.

        :param path: File to summarize.
            May be relative to the workspace root.
        :param limit: Maximum lines to include.
        """
        return path[:limit]

    spec = build_tool_spec(documented, ToolMeta(name="documented"))

    assert spec.description == "Summarize a file."
    assert spec.parameters["path"]["description"] == (
        "File to summarize. May be relative to the workspace root."
    )
    assert spec.parameters["limit"]["description"] == "Maximum lines to include."
