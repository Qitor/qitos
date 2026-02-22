"""MkDocs build hooks for QitOS docs."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import re
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


REPO_BASE = "https://github.com/Qitor/qitos/blob/main"


def _slug(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "item"


def _iter_modules(package_name: str) -> Iterable[str]:
    pkg = importlib.import_module(package_name)
    if not hasattr(pkg, "__path__"):
        return []
    names: List[str] = []
    for mod in pkgutil.walk_packages(pkg.__path__, prefix=f"{package_name}."):
        if mod.name.endswith(".__main__"):
            continue
        if ".__pycache__" in mod.name:
            continue
        names.append(mod.name)
    return sorted(set(names))


def _group_key(module_name: str) -> str:
    parts = module_name.split(".")
    if len(parts) >= 2:
        return ".".join(parts[:2])
    return module_name


def _first_line_doc(obj: object) -> str:
    doc = inspect.getdoc(obj) or ""
    if not doc:
        return ""
    return doc.strip().splitlines()[0].strip()


def _signature(obj: object) -> str:
    try:
        return str(inspect.signature(obj))
    except Exception:
        return "()"


def _public_symbols(module) -> Tuple[List[Tuple[str, object]], List[Tuple[str, object]]]:
    classes: List[Tuple[str, object]] = []
    funcs: List[Tuple[str, object]] = []
    for name, member in inspect.getmembers(module):
        if name.startswith("_"):
            continue
        if inspect.isclass(member) and getattr(member, "__module__", "") == module.__name__:
            classes.append((name, member))
        if inspect.isfunction(member) and getattr(member, "__module__", "") == module.__name__:
            funcs.append((name, member))
    return classes, funcs


def _write_module_page(module_name: str, out_path: Path, locale: str = "en") -> None:
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        title = "Failed to import this module during docs build." if locale == "en" else "构建文档时导入模块失败。"
        out_path.write_text(
            "\n".join([f"# `{module_name}`", "", title, "", f"- Error: `{exc}`"]),
            encoding="utf-8",
        )
        return

    classes, funcs = _public_symbols(module)
    source_rel = module_name.replace(".", "/") + ".py"

    if locale == "en":
        sections = {
            "quick_jump": "Quick Jump",
            "classes": "Classes",
            "functions": "Functions",
            "none": "_None_",
            "source_index": "Source Index",
            "source": "Source",
            "module_group": "Module Group",
        }
    else:
        sections = {
            "quick_jump": "快速跳转",
            "classes": "类",
            "functions": "函数",
            "none": "_无_",
            "source_index": "Source Index",
            "source": "源码",
            "module_group": "模块分组",
        }

    lines: List[str] = [
        f"# `{module_name}`",
        "",
        f"- {sections['module_group']}: `{_group_key(module_name)}`",
        f"- {sections['source']}: [{source_rel}]({REPO_BASE}/{source_rel})",
        "",
        f"## {sections['quick_jump']}",
        "",
        f"- [{sections['classes']}](#classes)",
        f"- [{sections['functions']}](#functions)",
    ]

    for name, _ in classes:
        lines.append(f"- [Class: `{name}`](#class-{_slug(name)})")
    for name, _ in funcs:
        lines.append(f"- [Function: `{name}`](#function-{_slug(name)})")
    lines.append("")

    lines.append("## Classes")
    lines.append("")
    if classes:
        for name, cls in classes:
            sig = _signature(cls.__init__)
            doc = _first_line_doc(cls)
            anchor = f"class-{_slug(name)}"
            lines.append(f'<a id="{anchor}"></a>')
            lines.append(f'???+ note "Class: `{name}{sig}`"')
            if doc:
                lines.append(f"    {doc}")
            else:
                lines.append("    _No summary available._")
            lines.append("")
    else:
        lines.append(f"- {sections['none']}")
        lines.append("")

    lines.append("## Functions")
    lines.append("")
    if funcs:
        for name, fn in funcs:
            sig = _signature(fn)
            doc = _first_line_doc(fn)
            anchor = f"function-{_slug(name)}"
            lines.append(f'<a id="{anchor}"></a>')
            lines.append(f'???+ note "Function: `{name}{sig}`"')
            if doc:
                lines.append(f"    {doc}")
            else:
                lines.append("    _No summary available._")
            lines.append("")
    else:
        lines.append(f"- {sections['none']}")
        lines.append("")

    lines.append(f"## {sections['source_index']}")
    lines.append("")
    lines.append(f"- [{source_rel}]({REPO_BASE}/{source_rel})")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def _write_grouped_index(modules: List[str], out_path: Path, locale: str = "en") -> None:
    grouped: Dict[str, List[str]] = {}
    for mod in modules:
        grouped.setdefault(_group_key(mod), []).append(mod)

    group_names = sorted(grouped.keys())

    if locale == "en":
        lines: List[str] = [
            "# API Reference (Auto-Generated)",
            "",
            "This section is generated automatically at build time from the `qitos` package.",
            "",
            "## Group Jump",
            "",
        ]
    else:
        lines = [
            "# API 参考（自动生成）",
            "",
            "本节在构建时自动从 `qitos` 包同步生成。",
            "",
            "## 分组跳转",
            "",
        ]

    for group in group_names:
        lines.append(f'- [{group}](#group-{_slug(group)})')
    lines.append("")

    if locale == "en":
        lines.append("## Modules by Group")
    else:
        lines.append("## 按模块分组")
    lines.append("")

    for group in group_names:
        lines.append(f'<a id="group-{_slug(group)}"></a>')
        lines.append(f"### `{group}`")
        lines.append("")
        for mod in grouped[group]:
            rel = mod.replace(".", "/") + ".md"
            lines.append(f"- [`{mod}`]({rel})")
        lines.append("")

    lines.extend(["## Source Index", "", "- [qitos/](https://github.com/Qitor/qitos/tree/main/qitos)"])
    out_path.write_text("\n".join(lines), encoding="utf-8")


def _sync_api_reference(docs_dir: Path) -> None:
    out_en = docs_dir / "reference" / "api_generated"
    out_zh = docs_dir / "zh" / "reference" / "api_generated"
    out_en.mkdir(parents=True, exist_ok=True)
    out_zh.mkdir(parents=True, exist_ok=True)

    modules = [m for m in _iter_modules("qitos") if not m.endswith(".__init__")]

    for mod in modules:
        rel = mod.replace(".", "/") + ".md"
        en_page = out_en / rel
        zh_page = out_zh / rel
        en_page.parent.mkdir(parents=True, exist_ok=True)
        zh_page.parent.mkdir(parents=True, exist_ok=True)
        _write_module_page(mod, en_page, locale="en")
        _write_module_page(mod, zh_page, locale="zh")

    _write_grouped_index(modules, out_en / "index.md", locale="en")
    _write_grouped_index(modules, out_zh / "index.md", locale="zh")


def on_config(config, **kwargs):  # noqa: ANN001
    docs_dir = Path(config["docs_dir"])
    _sync_api_reference(docs_dir)
    return config


def on_pre_build(config, **kwargs):  # noqa: ANN001
    return None
