"""Draft courses still require full, synchronized, syntactically valid source."""

import ast
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_lab_complete_files_match_both_languages():
    spec = importlib.util.spec_from_file_location(
        "lab_docs", ROOT / "scripts/sync_tutorial_docs.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    contract = json.loads((ROOT / "docs/agent-design-lab-contracts.json").read_text())
    assert len(contract["units"]) == 6
    for unit in contract["units"]:
        en = module.complete_files(ROOT / "docs" / (unit["page"] + ".mdx"))
        zh = module.complete_files(ROOT / "docs/zh" / (unit["page"] + ".mdx"))
        assert en == zh
        assert set(en) == {item["target"] for item in unit["files"]}
        assert "pyproject.toml" in en
        for item in unit["files"]:
            source = (ROOT / item["source"]).read_text()
            assert en[item["target"]] == source.rstrip() + "\n"
            if item["target"].endswith(".py"):
                tree = ast.parse(source)
                assert not any(
                    isinstance(node, ast.Constant) and node.value is Ellipsis
                    for node in ast.walk(tree)
                )
        assert (
            len(
                json.loads(
                    next(
                        body for name, body in en.items() if name.endswith("tasks.json")
                    )
                )
            )
            == 3
        )
