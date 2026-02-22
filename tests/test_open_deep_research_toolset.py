from __future__ import annotations

from qitos.kit.tool import OpenDeepResearchToolSet


def test_open_deep_research_page_navigation():
    ts = OpenDeepResearchToolSet(workspace_root=".")
    ts._state.lines = [f"line {i}" for i in range(120)]  # type: ignore[attr-defined]
    ts._state.url = "https://example.com"  # type: ignore[attr-defined]
    ts._state.title = "Example"  # type: ignore[attr-defined]
    ts._state.cursor = 0  # type: ignore[attr-defined]

    down = ts.page_down(lines=20)
    assert down["status"] == "success"
    assert down["line_start"] == 20

    up = ts.page_up(lines=10)
    assert up["status"] == "success"
    assert up["line_start"] == 10


def test_open_deep_research_find_and_file_inspect(tmp_path):
    ts = OpenDeepResearchToolSet(workspace_root=str(tmp_path))
    ts._state.lines = ["alpha", "beta", "target value", "omega"]  # type: ignore[attr-defined]
    ts._state.url = "https://example.com"  # type: ignore[attr-defined]
    ts._state.title = "Example"  # type: ignore[attr-defined]
    ts._state.cursor = 0  # type: ignore[attr-defined]

    found = ts.find_in_page("target")
    assert found["status"] == "success"
    assert found["matched_line"] == 2

    file_path = tmp_path / "note.txt"
    file_path.write_text("hello file", encoding="utf-8")
    inspected = ts.inspect_file_as_text("note.txt")
    assert inspected["status"] == "success"
    assert "hello file" in inspected["content"]

