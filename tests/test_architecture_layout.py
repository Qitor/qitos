from pathlib import Path


def test_kit_has_only_package_root_file():
    root = Path(__file__).resolve().parents[1] / "qitos" / "kit"
    top_level_py = sorted(p.name for p in root.glob("*.py"))
    assert top_level_py == ["__init__.py"]


def test_required_kit_packages_exist():
    root = Path(__file__).resolve().parents[1] / "qitos" / "kit"
    expected = {"memory", "parser", "planning", "tool", "prompts", "state", "critic", "env"}
    actual = {p.name for p in root.iterdir() if p.is_dir()}
    assert expected.issubset(actual)
