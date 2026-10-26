"""AST spec-to-code drift detection (Elephant-Goldfish Model).

Scans every ``.py`` file in the repo (excluding vendored/test dirs) with the
stdlib ``ast`` module, extracts defined classes, function signatures, and
FastAPI-style route decorators, then compares them against
``.toolkit/specs/architecture.md`` and ``.toolkit/specs/roadmap.md``.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from .config import ToolkitPaths

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "site-packages",
    "node_modules",
    "__pycache__",
    ".toolkit",
    "dist",
    "build",
    "tests",
}
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


@dataclass
class DriftResult:
    report: str
    raw_chars: int
    pruned_chars: int


def _iter_py_files(root: Path) -> list[Path]:
    """Every tracked ``.py`` file, excluding vendored/test/hidden dirs."""
    out: list[Path] = []
    for dirpath, dirnames, filenames in root.walk():
        dirnames[:] = [
            d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
        ]
        for name in filenames:
            if name.endswith(".py"):
                out.append(dirpath / name)
    return out


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = [a.arg for a in node.args.args]
    if node.args.vararg:
        args.append(f"*{node.args.vararg.arg}")
    return f"{node.name}({', '.join(args)})"


def _route_from_decorator(dec: ast.expr) -> str | None:
    """Extract ``app.get /path`` style routes from a decorator node."""
    if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
        return None
    method = dec.func.attr
    if method not in HTTP_METHODS:
        return None
    prefix = ""
    if isinstance(dec.func.value, ast.Name):
        prefix = dec.func.value.id + "."
    path = ""
    if (
        dec.args
        and isinstance(dec.args[0], ast.Constant)
        and isinstance(dec.args[0].value, str)
    ):
        path = dec.args[0].value
    return f"{prefix}{method} {path}"


def _collect_symbols(paths: list[Path]) -> tuple[list[str], list[str], list[str]]:
    """Return (classes, function-signatures, routes) across all files."""
    classes: list[str] = []
    functions: list[str] = []
    routes: list[str] = []
    for path in paths:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(_signature(node))
                for dec in node.decorator_list:
                    route = _route_from_decorator(dec)
                    if route:
                        routes.append(route)
    return classes, functions, routes


def _read_spec(root: Path, name: str) -> str:
    path = ToolkitPaths(root).specs / f"{name}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _mentions_in_spec(spec_text: str) -> list[str]:
    """Backticked identifiers that look like code symbols in the spec text."""
    import re

    return re.findall(r"`([A-Za-z_][A-Za-z0-9_.]*(?:\([^)]*\))?)`", spec_text)


def check_drift(root: Path) -> DriftResult:
    """Compare live code symbols against architecture.md + roadmap.md."""
    py_files = _iter_py_files(root)
    classes, functions, routes = _collect_symbols(py_files)

    arch = _read_spec(root, "architecture")
    roadmap = _read_spec(root, "roadmap")
    spec_text = arch + "\n" + roadmap

    undocumented: list[str] = []
    undocumented += [f"class {c}" for c in classes if c not in spec_text]
    undocumented += [
        f"def {fn}" for fn in functions if fn.split("(")[0] not in spec_text
    ]
    undocumented += [f"route {r}" for r in routes if r.split(" ")[-1] not in spec_text]

    code_symbols = set(classes) | {fn.split("(")[0] for fn in functions}
    missing_in_code = [
        m
        for m in _mentions_in_spec(spec_text)
        if m.split("(")[0].split(".")[-1] not in code_symbols and "(" not in m
    ]

    lines: list[str] = ["Spec drift report"]
    if undocumented:
        lines.append("undocumented in specs:")
        lines += [f"  - {u}" for u in undocumented]
    if missing_in_code:
        lines.append("mentioned in specs, missing in code:")
        lines += [f"  - {m}" for m in missing_in_code]
    if not undocumented and not missing_in_code:
        lines.append("No drift detected.")

    report = "\n".join(lines)

    raw_chars = sum(p.stat().st_size for p in py_files)
    arch_path = ToolkitPaths(root).specs / "architecture.md"
    if arch_path.exists():
        raw_chars += arch_path.stat().st_size
    return DriftResult(report=report, raw_chars=raw_chars, pruned_chars=len(report))
