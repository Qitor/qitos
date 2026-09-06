"""Generate static reference MDX from explicit supported imports and source AST."""
import argparse
import ast
from copy import deepcopy
from functools import lru_cache
import importlib
import inspect
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
START, END = "{/* api-reference:start */}", "{/* api-reference:end */}"


def anchor(module, name):
    return (module + "." + name).replace(".", "-").lower()


def definition(obj):
    """Use AST so defaults/signatures are stable across supported Python versions."""
    obj = inspect.unwrap(obj)
    filename = Path(inspect.getsourcefile(obj))
    parts = filename.parts
    index = len(parts) - 1 - list(reversed(parts)).index("qitos")
    relative = Path(*parts[index:])
    source = ROOT / relative
    if filename.read_bytes() != source.read_bytes():
        raise ValueError(f"{relative}: imported QitOS differs from this checkout")
    tree = ast.parse(source.read_text())
    _, line = inspect.getsourcelines(obj)
    nodes = [node for node in ast.walk(tree) if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
             and node.name == obj.__name__]
    node = min(nodes, key=lambda n: abs(n.lineno - line))
    return node, relative


@lru_cache(maxsize=None)
def validate_source_binding(baseline, relative):
    """Every public link must resolve to identical source in outgoing history."""
    reachable = subprocess.run(
        ["git", "merge-base", "--is-ancestor", baseline, "HEAD"], cwd=ROOT,
        capture_output=True,
    )
    if reachable.returncode:
        raise ValueError(f"API source {baseline} is not reachable from HEAD; fetch full history")
    committed = subprocess.run(
        ["git", "show", f"{baseline}:{relative.as_posix()}"], cwd=ROOT,
        capture_output=True,
    )
    if committed.returncode or committed.stdout != (ROOT / relative).read_bytes():
        raise ValueError(f"{relative}: public source binding differs from current implementation")


def signature(node):
    args = deepcopy(node.args)
    if args.args and args.args[0].arg in ("self", "cls"):
        args.args.pop(0)
    result = ast.unparse(node.returns) if node.returns else "Any (see behavior contract)"
    return f"{node.name}({ast.unparse(args)}) -> {result}"


def parameter_table(node):
    positional = [*node.args.posonlyargs, *node.args.args]
    defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
    parameters = list(zip(positional, defaults)) + list(zip(node.args.kwonlyargs, node.args.kw_defaults))
    rows = []
    for argument, default in parameters:
        if argument.arg in ("self", "cls"):
            continue
        annotation = ast.unparse(argument.annotation) if argument.annotation else "not annotated"
        value = ast.unparse(default) if default is not None else "required"
        annotation = annotation.replace("|", "\\|")
        value = value.replace("|", "\\|")
        rows.append(f"| `{argument.arg}` | `{annotation}` | `{value}` |")
    if not rows:
        return []
    return ["| Parameter | Type | Default |", "| --- | --- | --- |", *rows, ""]


def symbol_text(item, baseline, chinese, tutorial):
    module, name = item["module"], item["name"]
    obj = getattr(importlib.import_module(module), name)
    node, relative = definition(obj)
    validate_source_binding(baseline, relative)
    title = anchor(module, name)
    text = [f'<span id="{title}" />', f"## {name}", "", f"```python\nfrom {module} import {name}\n```", "",
            f"[Source @ {baseline[:7]}](https://github.com/WhitzardAgent/WhitzardOS/blob/{baseline}/{relative.as_posix()}#L{node.lineno})", "",
            f"[{'用法与可执行示例' if chinese else 'Usage and executable example'}]({'/zh/' if chinese else '/'}{tutorial})", ""]
    if item.get("example"):
        text += [("用法片段：接续上方完整教程中的对象，不是独立程序。" if chinese else
                  "Usage fragment: continues with objects from the linked complete tutorial; not a standalone program."),
                 "", "```python", item["example"], "```", ""]
    doc = ast.get_docstring(node)
    if doc:
        text += ["```text", doc, "```", ""]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        text += ["```text", signature(node), "```", "", *parameter_table(node)]
    else:
        constructor = next((n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == "__init__"), None)
        if constructor:
            text += ["```text", signature(constructor).replace("__init__(", name + "("), "```", "", *parameter_table(constructor)]
        fields = [n for n in node.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and not n.target.id.startswith("_")]
        if fields:
            text += ["| Field | Type | Default |", "| --- | --- | --- |"]
            for field in fields:
                annotation = ast.unparse(field.annotation).replace("|", "\\|")
                value = ast.unparse(field.value).replace("|", "\\|") if field.value else "required"
                text += [f"| `{field.target.id}` | `{annotation}` | `{value}` |"]
            text += [""]
    for method in item["methods"]:
        member = getattr(obj, method)
        method_node, method_file = definition(member)
        validate_source_binding(baseline, method_file)
        text += [f'<span id="{title}-{method.replace("_", "-")}" />', f"### {name}.{method}", "", "```text", signature(method_node), "```", "", *parameter_table(method_node)]
        doc = ast.get_docstring(method_node)
        if doc:
            text += ["```text", doc, "```", ""]
        text += [f"[Source](https://github.com/WhitzardAgent/WhitzardOS/blob/{baseline}/{method_file.as_posix()}#L{method_node.lineno})", ""]
    return "\n".join(text)


def synchronize(check=False):
    manifest = json.loads((ROOT / "docs/api-contracts.json").read_text())
    errors = []
    for group in manifest["groups"]:
        for prefix in ("", "zh/"):
            page = ROOT / "docs" / f"{prefix}reference/{group['slug']}.mdx"
            text = page.read_text()
            body = "\n\n".join(symbol_text(item, group.get("baseline", manifest["baseline"]), bool(prefix), group["tutorial"]) for item in group["symbols"])
            expected = text.split(START)[0] + START + "\n\n" + body + "\n" + END + text.split(END)[1]
            if text != expected:
                if check:
                    errors.append(f"{page.relative_to(ROOT)}: API signature/field/source drift")
                else:
                    page.write_text(expected)
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    failures = synchronize(args.check)
    print("\n".join(failures) if failures else "Public API imports, signatures and source links synchronized.")
    raise SystemExit(bool(failures))
