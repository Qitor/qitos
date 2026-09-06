"""Public source/signature rendering must agree on supported Python versions."""
import ast
from pathlib import Path

import pytest

from scripts.sync_api_reference import unparse, validate_source_binding


@pytest.mark.parametrize("source", [
    "field(default_factory=lambda: uuid4().hex)",
    "field(default_factory=lambda: 'literal lambda : remains unchanged')",
    "(lambda: 1, lambda: 2, lambda x: x)",
])
def test_lambda_rendering_is_portable_without_rewriting_literals(source):
    assert unparse(ast.parse(source, mode="eval").body) == source


@pytest.mark.parametrize("source", [
    "1710b2723238648e3d7394b262f06e97290cd093",
    "df9316415db7ec76f1e5d70a11ceabfd47744169",
])
def test_public_bindings_reject_unreachable_producer_history(source):
    with pytest.raises(ValueError, match="not reachable from HEAD"):
        validate_source_binding(source, Path("qitos/core/context.py"))


def test_public_bindings_reject_reachable_but_stale_source():
    with pytest.raises(ValueError, match="differs from current implementation"):
        validate_source_binding(
            "4dfb570fb7eef504c1e6d247c21a1984251b80e4", Path("qitos/models/openai.py")
        )
