"""Graph freshness check and audit workflow (instruct vs subprocess)."""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .runtime import safety

CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx"}
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", ".toolkit", "__pycache__", "dist", "build"}
RUNNER = Callable[..., safety.CommandResult]


@dataclass
class AuditResult:
    text: str
    raw_chars: int
    pruned_chars: int


def _newest_mtime(paths: list[Path]) -> float | None:
    found = [p.stat().st_mtime for p in paths if p.exists()]
    return max(found) if found else None


def graph_is_fresh(root: Path, config: dict) -> tuple[bool, str]:
    """Fresh when the newest graph report mtime >= newest code-file mtime."""
    reports = [
        root / rel for rel in config.get("graph_report_paths", []) if isinstance(rel, str)
    ]
    graph_mtime = _newest_mtime(reports)
    if graph_mtime is None:
        return False, "missing"
    code_files: list[Path] = []
    for dirpath, dirnames, filenames in root.walk():
        dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS]
        for name in filenames:
            if Path(name).suffix.lower() in CODE_EXTS:
                code_files.append(dirpath / name)
    code_mtime = _newest_mtime(code_files)
    if code_mtime is None:
        return True, "no-code"
    return graph_mtime >= code_mtime, "compared"


def _truncate(text: str, limit: int = 3000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated {len(text) - limit} chars]"


def run_audit_workflow(
    root: Path,
    config: dict,
    audit_cmd: str | None = None,
    runner: RUNNER = safety.run_command,
    which_fn: Callable[[str], str | None] = shutil.which,
) -> AuditResult:
    """Instruct mode never executes; subprocess mode runs graph then audit."""
    fresh, why = graph_is_fresh(root, config)
    graph_cmd = str(config.get("graph_cmd", "graphify"))
    configured_audit = str(config.get("audit_cmd", "ponytail-review"))
    audit_name = configured_audit if audit_cmd in (None, "") else audit_cmd

    if config.get("audit_mode", "instruct") == "subprocess":
        allowed = list(config.get("allowed_commands", []))
        timeout_s = int(config.get("command_timeout_s", 120))
        if audit_name != configured_audit:
            msg = f"octk audit refused: {audit_name!r} != configured {configured_audit!r}"
            return AuditResult(text=msg, raw_chars=len(msg), pruned_chars=len(msg))
        if not which_fn(graph_cmd.split()[0]) or not which_fn(audit_name.split()[0]):
            msg = f"octk audit: '{graph_cmd}' / '{audit_name}' not installed; use audit_mode='instruct'"
            return AuditResult(text=msg, raw_chars=len(msg), pruned_chars=len(msg))
        pieces: list[str] = []
        raw_total = 0
        if not fresh:
            out = runner([graph_cmd], root, allowed, timeout_s)
            raw_total += len(out.stdout) + len(out.stderr)
            pieces.append(f"$ {graph_cmd}\n{_truncate(out.stdout + out.stderr)}")
        out = runner([audit_name], root, allowed, timeout_s)
        raw_total += len(out.stdout) + len(out.stderr)
        pieces.append(f"$ {audit_name}\n{_truncate(out.stdout + out.stderr)}")
        text = "\n".join(pieces)
        return AuditResult(text=text, raw_chars=raw_total, pruned_chars=len(text))

    if fresh:
        text = f"Graph is fresh: run `{configured_audit}` now."
    else:
        text = f"Graph is stale/missing ({why}): run `/graphify .` first, then `/ponytail-review`."
    now = time.strftime("%Y-%m-%d")
    text = f"{text} (checked {now}, mode=instruct)"
    return AuditResult(text=text, raw_chars=len(text), pruned_chars=len(text))
