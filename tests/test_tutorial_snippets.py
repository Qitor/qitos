"""Compile bilingual public Python examples and resolve imported symbols.

Blocks are explicitly illustrative unless bound to a complete executable file
in tutorial-contracts.json. No arbitrary documentation shell is executed.
"""
import ast
import importlib
from pathlib import Path
import re
import textwrap

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
BLOCK = re.compile(r"```(python|yaml|json)[^\n]*\n(.*?)```", re.S)
CASES = [(str(p.relative_to(DOCS)), i, lang, textwrap.dedent(code))
         for p in sorted(DOCS.rglob("*.mdx"))
         for i, (lang, code) in enumerate(BLOCK.findall(p.read_text()))]


@pytest.mark.parametrize("page,index,language,code", CASES,
                         ids=[f"{p}:block-{i}" for p, i, _, _ in CASES])
def test_public_snippet(page, index, language, code, tmp_path):
    if language != "python":
        # Shell/template interpolation and documented config fragments are illustrative.
        if language == "json":
            import json
            json.loads(code)
        else:
            parsed = yaml.safe_load(code)
            if isinstance(parsed, dict) and parsed.get("schema") == "qitos.agent":
                from qitos.config import load_agent_config
                target = tmp_path / "agent.yaml"
                target.write_text(code)
                load_agent_config(target)
        return
    filename = f"{page}:block-{index}"
    compile(code, filename, "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "qitos" or alias.name.startswith("qitos."):
                    importlib.import_module(alias.name)
        elif (isinstance(node, ast.ImportFrom) and node.module
              and (node.module == "qitos" or node.module.startswith("qitos."))):
            module = importlib.import_module(node.module)
            for alias in node.names:
                if alias.name != "*":
                    assert hasattr(module, alias.name), f"{filename}: missing {node.module}.{alias.name}"
