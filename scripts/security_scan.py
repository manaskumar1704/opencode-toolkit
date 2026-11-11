#!/usr/bin/env python3
"""Static security scan for OCTK (R-4).

No third-party dependencies. AST-based where possible so string literals and
comments do not create false positives.

Usage:
    python scripts/security_scan.py [--json] [--root PATH]

Exit codes: 0 = no HIGH findings, 1 = at least one HIGH finding.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}

SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]"
)


@dataclass(frozen=True)
class Finding:
    check: str
    severity: str
    path: str
    line: int
    message: str


def _iter_python(root: Path):
    for path in sorted(root.rglob("*.py")):
        if any(part in {"__pycache__", ".venv", ".git"} for part in path.parts):
            continue
        yield path


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def check_shell_and_exec(path: Path, tree: ast.AST) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)
        if name in {"os.system", "os.popen", "subprocess.getoutput", "subprocess.getstatusoutput"}:
            findings.append(
                Finding("shell-exec", "HIGH", str(path), node.lineno, f"{name} spawns a shell")
            )
        if name.startswith("subprocess.") and any(
            kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True
            for kw in node.keywords
        ):
            findings.append(
                Finding("shell-true", "HIGH", str(path), node.lineno, "subprocess call uses shell=True")
            )
        if (
            name in {"eval", "exec", "compile"}
            and node.args
            and not isinstance(node.args[0], ast.Constant)
        ):
            findings.append(
                Finding("dynamic-exec", "HIGH", str(path), node.lineno, f"{name} on a non-literal")
            )
        if name in {"pickle.load", "pickle.loads", "marshal.loads"}:
            findings.append(
                Finding("unsafe-deserialize", "HIGH", str(path), node.lineno, f"{name} on untrusted data")
            )
        if name == "yaml.load":
            safe = any(
                kw.arg == "Loader"
                and "Safe" in _call_name(kw.value)
                for kw in node.keywords
            )
            if not safe:
                findings.append(
                    Finding("unsafe-yaml", "HIGH", str(path), node.lineno, "yaml.load without SafeLoader")
                )
    return findings


def check_subprocess_timeout(path: Path, tree: ast.AST) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _call_name(node.func) not in {"subprocess.run", "subprocess.check_output", "subprocess.call"}:
            continue
        if not any(kw.arg == "timeout" for kw in node.keywords):
            findings.append(
                Finding(
                    "subprocess-no-timeout",
                    "MEDIUM",
                    str(path),
                    node.lineno,
                    "subprocess call without a timeout",
                )
            )
    return findings


def check_permissions_and_tempfiles(path: Path, tree: ast.AST) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)
        if name == "os.chmod" and len(node.args) >= 2:
            mode = node.args[1]
            if (
                isinstance(mode, ast.Constant)
                and isinstance(mode.value, int)
                and mode.value & 0o077
            ):
                findings.append(
                    Finding(
                        "permissive-chmod",
                        "MEDIUM",
                        str(path),
                        node.lineno,
                        f"chmod mode {oct(mode.value)} grants group/other access",
                    )
                )
        if name == "tempfile.mktemp":
            findings.append(
                Finding("predictable-tempfile", "HIGH", str(path), node.lineno, "tempfile.mktemp is racy")
            )
    return findings


def check_secrets(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if SECRET_RE.search(line):
            findings.append(
                Finding("hardcoded-secret", "HIGH", str(path), number, "possible hardcoded credential")
            )
    return findings


def check_guards(root: Path) -> list[Finding]:
    """Positive checks: guards that must exist. Absence is the finding."""
    findings: list[Finding] = []

    proxy = root / "octk" / "mcp_proxy.py"
    if proxy.is_file():
        text = proxy.read_text(encoding="utf-8")
        if "SERVER_RE" not in text or "SERVER_RE.match" not in text:
            findings.append(
                Finding("mcp-name-guard", "HIGH", str(proxy), 0, "external MCP server names are not validated")
            )
    else:
        findings.append(Finding("mcp-name-guard", "INFO", str(proxy), 0, "mcp_proxy.py not found"))

    browser = root / "octk" / "runtime" / "browser.py"
    if browser.is_file():
        text = browser.read_text(encoding="utf-8")
        if 'startswith(("http://", "https://"))' not in text:
            findings.append(
                Finding("browser-scheme-guard", "HIGH", str(browser), 0, "browser accepts non-http(s) URLs")
            )
        if "blocked" not in text and "169.254.169.254" not in text:
            findings.append(
                Finding(
                    "browser-metadata-egress",
                    "MEDIUM",
                    str(browser),
                    0,
                    "no link-local/metadata host block; local SSRF to cloud metadata is possible",
                )
            )

    approvals = root / "octk" / "approvals.py"
    if approvals.is_file():
        text = approvals.read_text(encoding="utf-8")
        if "0o600" not in text:
            findings.append(
                Finding(
                    "approval-file-mode",
                    "MEDIUM",
                    str(approvals),
                    0,
                    "approvals.json is written without restrictive permissions",
                )
            )
    return findings


def check_dependencies(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return findings
    text = pyproject.read_text(encoding="utf-8")
    in_deps = False
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("dependencies = ["):
            in_deps = True
            continue
        if in_deps and stripped == "]":
            in_deps = False
            continue
        if in_deps and stripped.startswith('"') and "<" not in stripped:
            findings.append(
                Finding(
                    "unbounded-dependency",
                    "LOW",
                    str(pyproject),
                    number,
                    f"dependency without an upper bound: {stripped}",
                )
            )
    return findings


def scan(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in _iter_python(root / "octk"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        findings += check_shell_and_exec(path, tree)
        findings += check_subprocess_timeout(path, tree)
        findings += check_permissions_and_tempfiles(path, tree)
        findings += check_secrets(path)
    findings += check_guards(root)
    findings += check_dependencies(root)
    return sorted(
        findings,
        key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.path, f.line, f.check),
    )


def render(findings: list[Finding]) -> str:
    if not findings:
        return "No findings."
    lines = ["| severity | check | file:line | detail |", "|---|---|---|---|"]
    for finding in findings:
        location = f"{finding.path}:{finding.line}" if finding.line else finding.path
        lines.append(
            f"| {finding.severity} | {finding.check} | {location} | {finding.message} |"
        )
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda kv: SEVERITY_ORDER[kv[0]]))
    return "\n".join(lines) + f"\n\nSummary: {summary}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Static security scan for OCTK.")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    findings = scan(Path(args.root).resolve())
    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        print(render(findings))
    return 1 if any(f.severity == "HIGH" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
