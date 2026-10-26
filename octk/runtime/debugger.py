"""Debug runner with output pruning. Pure pruning, no logging."""

from __future__ import annotations

import re
import shlex
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from ..config import DEFAULT_CONFIG
from . import safety

EXCLUDED_PARTS = {".venv", "venv", "site-packages", "node_modules", "__pycache__"}
PYTEST_HEADER_RE = re.compile(r"^(?P<path>[\w~./\\: -]*\.py):(?P<line>\d+):[ ]?(?P<msg>.*)$")
PY_FILE_RE = re.compile(r"^(?P<path>[\w~./\\: -]*\.py):(?P<line>\d+):")
STD_FRAME_RE = re.compile(r'^\s*File "(?P<path>[^"]+)", line (?P<line>\d+), in (?P<func>.*)$')
LOCALS_RE = re.compile(r"^\s{2,}(local\s+\w+\s*=|\w+\s*=\s)")
EXC_LINE_RE = re.compile(r"^(Uncaught exception:|[\w.]*\b\w*(Error|Exception|Warning)\b[^:]*: \w+)")
SUMMARY_RE = re.compile(r"^(=|(FAILED|ERROR|PASSED)|.+=.*=)")
TRUNCATED_NOTE = "octk note: pruned"


@dataclass
class DebugResult:
    text: str
    raw_chars: int
    pruned_chars: int


def _norm(path_str: str, root: Path) -> Path | None:
    """Resolve a printed path (relative or absolute, / or \\) under root."""
    clean = path_str.strip().strip('"').replace("\\", "/")
    if not clean:
        return None
    candidate = Path(clean)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        candidate = candidate.resolve()
        candidate.relative_to(root.resolve())
    except (ValueError, OSError):
        return None
    return candidate


def _is_project_path(path_str: str, root: Path) -> bool:
    """Under root and not inside an excluded dir."""
    resolved = _norm(path_str, root)
    if resolved is None:
        return False
    parts = {part.lower().replace("\\", "/") for part in resolved.parts}
    return not (parts & EXCLUDED_PARTS)


def _keep_frame_block(lines: list[str], i: int) -> tuple[list[str], int]:
    """Header + following code line + locals lines (pre-E-line)."""
    block = [lines[i]]
    j = i + 1
    while j < len(lines):
        line = lines[j]
        if PY_FILE_RE.match(line) or STD_FRAME_RE.match(line) or line.startswith("E "):
            break
        if not line.strip():
            break
        if LOCALS_RE.match(line) or line.startswith("    "):
            block.append(line)
            j += 1
            continue
        break
    return block, j


def _parse_and_prune(text: str, root: Path) -> tuple[str, int]:
    """Project-frame aware prune; returns (kept_text, kept_frame_count)."""
    lines = text.splitlines()
    kept: list[str] = []
    kept_frames = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        header = PY_FILE_RE.match(line)
        std_frame = STD_FRAME_RE.match(line)
        is_frame = bool(header or std_frame)
        if is_frame:
            path_str = (header.group("path") if header else std_frame.group("path"))
            if _is_project_path(path_str, root):
                block, i = _keep_frame_block(lines, i)
                kept.extend(block)
                kept_frames += 1
                continue
            # skipped frame: drop only the header; its code/locals lines
            # never match the keep rules below, so they are silenced
            i += 1
            continue
        if line.startswith("E ") or EXC_LINE_RE.match(line) or SUMMARY_RE.match(line):
            kept.append(line)
        i += 1
    return "\n".join(kept) + ("\n" if kept else ""), kept_frames


def prune_output(text: str, root: Path, max_chars: int = 2500) -> str:
    """Keep project frames + signals; drop third-party/stdlib/venv frames."""
    if not text.strip():
        return ""
    kept_text, kept_frames = _parse_and_prune(text, root)
    if kept_frames == 0:
        tail = text[-1500:]
        first_line = text.splitlines()[0] if text else ""
        return (f"{first_line}\n{TRUNCATED_NOTE}: project-filtered\n{tail}\n(no project frames found)\n")
    kept_text = f"{TRUNCATED_NOTE}: dropped third-party/stdlib frames\n{kept_text}"
    return _truncate_kept(kept_text, max_chars)


def _truncate_kept(text: str, max_chars: int) -> str:
    """Head + tail cut that provably lands under max_chars."""
    if len(text) <= max_chars:
        return text
    head = text[: max(1, max_chars // 2)]
    marker_hint = "\n... [truncated 99999 chars]\n"  # ~28 chars
    tail = text[-max(1, max_chars - len(head) - len(marker_hint)):]
    excess = len(text) - len(head) - len(tail)
    marker = f"\n... [truncated {excess} chars]\n"
    out = head + marker + tail
    if len(out) > max_chars:
        out = out[: max_chars - len(marker)] + marker
    return out


def _pytest_route(argv: list[str], config: dict) -> list[str]:
    if "--tb" in argv or "-x" in argv:
        return argv
    return argv + config.get("pytest_flags", ["--tb=short", "--showlocals", "-q", "-x"])


def run_smart_debugger(command: str, root: Path, config: dict | None = None) -> DebugResult:
    """Route pytest/python scripts to runners with pruned output."""
    config = {**DEFAULT_CONFIG, **(config or {})}
    # Normalize Windows separators BEFORE shlex, which treats \ as escapes
    argv = (
        shlex.split(command.replace("\\", "/"))
        if isinstance(command, str) and command.strip()
        else list(command)
    )
    if not argv:
        return DebugResult(text="", raw_chars=0, pruned_chars=0)
    allowed = list(config.get("allowed_commands", []))
    py_tokens = {"python", "python3", sys.executable}
    route_pytest = argv[0] == "pytest" or (
        argv[0] in py_tokens and len(argv) > 2 and argv[1] == "-m" and argv[2] == "pytest"
    )
    route_python_script = not route_pytest and argv[0] in py_tokens and len(argv) > 1 and argv[1].endswith(".py")
    if route_pytest and argv[0] in py_tokens:
        argv = ["pytest", *argv[3:]]
    if route_pytest and argv and argv[0] == "pytest" and shutil.which("pytest") is None:
        argv = [sys.executable, "-m", "pytest", *argv[1:]]
    if route_pytest:
        argv = _pytest_route(argv, config)
    elif route_python_script:
        argv = [sys.executable, "-m", "octk.runtime._trace_wrapper", *argv[1:]]
    result = safety.run_command(argv, root, allowed, int(config.get("command_timeout_s", 120)))
    raw_text = result.stdout + result.stderr
    text = prune_output(raw_text, root, int(config.get("max_output_chars", 2500)))
    return DebugResult(text=text, raw_chars=len(raw_text), pruned_chars=len(text))
