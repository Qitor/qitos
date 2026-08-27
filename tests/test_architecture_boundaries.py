"""Architecture boundary checks.

Enforces the dependency rules documented in ``docs/architecture/module-boundaries.md``
against the real import graph (module-level imports only, relative imports resolved).

Design: ratchet. Current legacy violations are listed in ``LEGACY_MODULE_EDGES`` /
``TOLERATED_CYCLES``; any NEW violation fails, and fixing a violation should remove
its allowlist entry in the same change. Function-level (lazy) imports are not counted
here — but remember they are still real dependencies (see architecture-debt.md D3);
never promote a lazy import to module level to satisfy this test.

Run: pytest tests/test_architecture_boundaries.py -q
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
QITOS = REPO / "qitos"

# ---------------------------------------------------------------------------
# Target dependency rules (see docs/architecture/module-boundaries.md)
# ---------------------------------------------------------------------------

# None = wildcard: edge dispatchers may import any qitos package.

ALLOWED_MODULE_DEPS: dict[str, frozenset[str] | None] = {
    # "(root)" = qitos/__init__.py; "cli" = qitos/cli.py
    "(root)": frozenset({"core", "engine"}),
    "cli": None,  # edge dispatcher: may import any qitos package
    "core": frozenset({"protocols", "prompting"}),
    "engine": frozenset(
        {"core", "protocols", "prompting", "models", "harness", "checkpoint", "trace", "tracing"}
    ),
    "kit": frozenset(
        {"core", "engine", "models", "protocols", "prompting", "evaluate", "metric", "trace"}
    ),
    "models": frozenset({"core", "protocols", "harness"}),
    "harness": frozenset({"protocols"}),
    "protocols": frozenset(),
    "prompting": frozenset(),
    "trace": frozenset({"tracing"}),
    "tracing": frozenset(),
    "render": frozenset({"core", "engine", "tracing"}),
    "checkpoint": frozenset(),
    "cache": frozenset({"models"}),
    "mcp": frozenset({"core"}),
    "evaluate": frozenset({"core"}),
    "metric": frozenset(),
    "benchmark": frozenset({"core", "engine", "kit", "trace", "tracing"}),  # deprecated
    "recipes": frozenset(
        {"core", "engine", "kit", "models", "trace", "render", "evaluate", "metric", "harness"}
    ),
    "config": frozenset({"core", "models", "engine"}),
    "experiment": frozenset({"core", "engine", "config", "cache", "checkpoint"}),
    "leaderboard": frozenset({"benchmark", "core"}),
    "hf": frozenset(),
    "demo": frozenset({"core", "kit", "models"}),
    "qita": frozenset(),
    "debug": frozenset(),
    "func": frozenset({"core"}),
}

# Known violations (architecture-debt.md). Keys: (src_pkg, dst_pkg) -> offending files.
LEGACY_MODULE_EDGES: dict[tuple[str, str], frozenset[str]] = {
    ("kit", "benchmark"): frozenset({"kit/evaluate/cybench.py"}),  # D6 / V5
    ("benchmark", "recipes"): frozenset(  # D1 / V2 migration-era cycle
        {
            "benchmark/cybench/runner.py",
            "benchmark/desktop/runner.py",
            "benchmark/gaia/runner.py",
            "benchmark/osworld/runner.py",
            "benchmark/tau_bench/runner.py",
        }
    ),
    ("recipes", "benchmark"): frozenset(  # D1 / V2 migration-era cycle
        {
            "recipes/benchmarks/_shared.py",
            "recipes/benchmarks/cybench.py",
            "recipes/benchmarks/cybergym.py",
            "recipes/benchmarks/gaia.py",
            "recipes/benchmarks/tau_bench.py",
        }
    ),
}

# Package-level import cycles tolerated today (each must have a debt entry + exit plan).
# {benchmark, kit, recipes} is one SCC: benchmark <-> recipes (D1) joined by kit -> benchmark (D6).
TOLERATED_CYCLES: frozenset[frozenset[str]] = frozenset(
    {frozenset({"benchmark", "kit", "recipes"})}
)

# Harness documents that must exist (AGENTS coverage for real architecture boundaries).
REQUIRED_DOCS = (
    "AGENTS.md",
    "ARCHITECTURE.md",
    "qitos/AGENTS.md",
    "qitos/core/AGENTS.md",
    "qitos/engine/AGENTS.md",
    "qitos/kit/AGENTS.md",
    "docs/architecture/architecture-audit.md",
    "docs/architecture/module-boundaries.md",
    "docs/architecture/change-guide.md",
    "docs/architecture/architecture-debt.md",
)

# Markdown files whose relative links are verified.
LINK_CHECKED_DOCS = [
    *REQUIRED_DOCS[:6],
    "docs/architecture/architecture-audit.md",
    "docs/architecture/module-boundaries.md",
    "docs/architecture/change-guide.md",
    "docs/architecture/architecture-debt.md",
]


# ---------------------------------------------------------------------------
# Import-graph extraction (module-level only)
# ---------------------------------------------------------------------------

_UNDECLARED = object()  # sentinel: source package missing from ALLOWED_MODULE_DEPS


def _pkg_of(rel: str) -> str:
    parts = rel.split("/")
    if len(parts) == 1:
        return "(root)" if parts[0] == "__init__.py" else parts[0][: -len(".py")]
    return parts[0]


def _resolve_relative(rel: str, level: int, module: str) -> str:
    base = rel.split("/")[:-1]
    for _ in range(level - 1):
        base = base[:-1]
    return ".".join(["qitos"] + base + ([n for n in module.split(".")] if module else []))


def _module_level_imports(tree: ast.Module):
    def walk(stmts):
        for node in stmts:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue  # lazy imports are not module-level dependencies
            if isinstance(node, ast.ClassDef):
                walk(node.body)
                continue
            if isinstance(node, ast.If):
                test = node.test
                is_type_checking = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
                    isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
                )
                if not is_type_checking:
                    walk(node.body)
                    walk(node.orelse)
                continue
            if isinstance(node, ast.Try):
                walk(node.body)
                for handler in node.handlers:
                    walk(handler.body)
                walk(node.orelse)
                walk(node.finalbody)
                continue
            if isinstance(node, ast.Import):
                for alias in node.names:
                    yield alias.name
            elif isinstance(node, ast.ImportFrom):
                yield node.module or ""

    yield from walk(tree.body)


def collect_module_edges() -> dict[tuple[str, str], set[str]]:
    edges: dict[tuple[str, str], set[str]] = {}
    for path in sorted(QITOS.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(QITOS).as_posix()
        src = _pkg_of(rel)
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        for dotted in _module_level_imports(tree):
            if dotted == "qitos":
                target = "(root)"
            elif dotted.startswith("qitos."):
                target = dotted.split(".")[1]
            else:
                continue
            if target != src:
                edges.setdefault((src, target), set()).add(rel)
    return edges


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_new_forbidden_module_level_dependencies() -> None:
    edges = collect_module_edges()
    violations: list[str] = []
    for (src, dst), files in sorted(edges.items()):
        allowed = ALLOWED_MODULE_DEPS.get(src, _UNDECLARED)
        if allowed is _UNDECLARED:
            violations.append(
                f"qitos/{src} is not declared in ALLOWED_MODULE_DEPS — declare its allowed "
                f"dependencies (docs/architecture/module-boundaries.md). Offending: -> {dst}"
            )
            continue
        if allowed is None or dst in allowed:
            continue  # None = wildcard (edge dispatchers); else allowed edge
        legacy = LEGACY_MODULE_EDGES.get((src, dst), frozenset())
        new = files - legacy
        gone = legacy - files
        if new:
            violations.append(
                f"qitos/{src} -> qitos/{dst} is not allowed. New offending files: "
                f"{sorted(new)}. Rules: docs/architecture/module-boundaries.md"
            )
        if gone:
            violations.append(
                f"qitos/{src} -> qitos/{dst}: legacy violation fixed ({sorted(gone)}) — "
                f"remove its allowlist entry in tests/test_architecture_boundaries.py"
            )
    assert not violations, "\n".join(violations)


def test_no_new_module_level_import_cycles() -> None:
    edges = collect_module_edges()
    graph: dict[str, set[str]] = {}
    for (src, dst) in edges:
        graph.setdefault(src, set()).add(dst)

    # Tarjan-free simple SCC detection (graph is small).
    index_counter = [0]
    stack: list[str] = []
    lowlink: dict[str, int] = {}
    index: dict[str, int] = {}
    on_stack: set[str] = set()
    sccs: list[set[str]] = []

    def strongconnect(v: str) -> None:
        work = [(v, iter(sorted(graph.get(v, ()))))]
        index[v] = lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        while work:
            node, it = work[-1]
            advanced = False
            for w in it:
                if w not in index:
                    index[w] = lowlink[w] = index_counter[0]
                    index_counter[0] += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, iter(sorted(graph.get(w, ())))))
                    advanced = True
                    break
                if w in on_stack:
                    lowlink[node] = min(lowlink[node], index[w])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])
            if lowlink[node] == index[node]:
                scc: set[str] = set()
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    scc.add(w)
                    if w == node:
                        break
                if len(scc) > 1:
                    sccs.append(scc)

    for v in sorted(graph):
        if v not in index:
            strongconnect(v)

    unexpected = [scc for scc in sccs if scc not in TOLERATED_CYCLES]
    assert not unexpected, (
        f"New module-level import cycle(s): {[sorted(s) for s in unexpected]}. "
        "See docs/architecture/architecture-debt.md; break the cycle or (if truly "
        "unavoidable) document it and add to TOLERATED_CYCLES with an exit plan."
    )


def test_architecture_harness_docs_exist() -> None:
    missing = [doc for doc in REQUIRED_DOCS if not (REPO / doc).is_file()]
    assert not missing, f"Architecture harness documents missing: {missing}"


def test_harness_doc_links_resolve() -> None:
    link_re = re.compile(r"\]\(([^)\s]+)\)")
    broken: list[str] = []
    for doc in LINK_CHECKED_DOCS:
        path = REPO / doc
        if not path.is_file():
            continue
        for target in link_re.findall(path.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            target = target.split("#", 1)[0]
            if not target:
                continue
            if not (path.parent / target).resolve().exists() and not (REPO / target).exists():
                broken.append(f"{doc}: broken link -> {target}")
    assert not broken, "\n".join(broken)
