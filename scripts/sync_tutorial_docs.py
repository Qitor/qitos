"""Materialize reviewed source files into MDX; --check never writes files."""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
START = "{/* tutorial-files:start */}"
END = "{/* tutorial-files:end */}"
FILE_BLOCK = re.compile(r'```(?:python|yaml|json) title="([^"]+)"\n(.*?)\n```', re.S)


def contracts():
    return json.loads((ROOT / "docs/tutorial-contracts.json").read_text())


def complete_files(page):
    """Only the explicit complete-file region is executable, never prose shell."""
    content = page.read_text(encoding="utf-8")
    if content.count(START) != 1 or content.count(END) != 1:
        raise ValueError(f"{page}: expected one complete-file region")
    region = content.split(START)[1].split(END)[0]
    files = {}
    for name, code in FILE_BLOCK.findall(region):
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or name in files:
            raise ValueError(f"{page}: unsafe or duplicate filename {name}")
        files[name] = code + "\n"
    return files


def render_files(unit, chinese):
    heading = "完整文件：复制到项目根目录" if chinese else "Complete files: save in the project root"
    blocks = [START, "", f"## {heading}", ""]
    for item in unit["files"]:
        source = ROOT / item["source"]
        language = {".py": "python", ".yaml": "yaml", ".json": "json"}[source.suffix]
        blocks.extend([f'```{language} title="{item["target"]}"', source.read_text().rstrip(), "```", ""])
    blocks.append(END)
    return "\n".join(blocks)


def synchronize(check=False):
    errors = []
    for unit in contracts()["units"]:
        for prefix in ("", "zh/"):
            page = ROOT / "docs" / f"{prefix}{unit['page']}.mdx"
            text = page.read_text()
            if text.count(START) != 1 or text.count(END) != 1:
                errors.append(f"{page}: missing complete-file markers")
                continue
            expected = text.split(START)[0] + render_files(unit, bool(prefix)) + text.split(END)[1]
            # Named excerpts in the prose are checked against the same source.
            pattern = r'\{/\* tutorial-snippet:([^:]+):([^ ]+) \*/\}.*?\{/\* tutorial-snippet:end \*/\}'

            def excerpt(match):
                filename, name = match.group(1, 2)
                source = ROOT / unit["source_dir"] / filename
                body = source.read_text().split(f"# docs:start {name}\n")[1].split(f"# docs:end {name}")[0].rstrip()
                return (f'{{/* tutorial-snippet:{filename}:{name} */}}\n```python\n{body}\n```\n'
                        '{/* tutorial-snippet:end */}')
            expected = re.sub(pattern, excerpt, expected, flags=re.S)
            if text != expected:
                if check:
                    errors.append(f"{page.relative_to(ROOT)}: source/code drift; run scripts/sync_tutorial_docs.py")
                else:
                    page.write_text(expected, encoding="utf-8")
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    failures = synchronize(args.check)
    print("\n".join(failures) if failures else "Tutorial complete files and excerpts synchronized.")
    raise SystemExit(bool(failures))
