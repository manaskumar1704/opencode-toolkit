"""Roadmap parsing and gated status updates."""

from __future__ import annotations

import re
import time
from pathlib import Path

from . import approvals
from .config import ToolkitPaths

LINE_RE = re.compile(r"^\s*- \[( |~|x)\] (.+)$")
STATUS_ALIASES = {"done": "x", "current": "~", "todo": " "}


class RoadmapError(Exception):
    """Raised when the roadmap file or requested task is inconsistent."""


class GateError(Exception):
    """Raised when 'done' lacks a valid human approval."""


def parse_roadmap(root: Path) -> list[dict[str, object]]:
    """Parse roadmap lines into {line_no, status, text} entries."""
    path = ToolkitPaths(root).roadmap
    if not path.exists():
        raise RoadmapError(f"roadmap not found: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, object]] = []
    for line_no, line in enumerate(lines, start=1):
        match = LINE_RE.match(line)
        if match:
            out.append(
                {"line_no": line_no, "status": match.group(1), "text": match.group(2)}
            )
    return out


def _read_preserving(path: Path) -> tuple[list[str], str]:
    """Return logical lines and the dominant line ending."""
    text = path.read_text(encoding="utf-8")
    ending = "\r\n" if "\r\n" in text else "\n"
    return text.splitlines(), ending


def _write_preserving(path: Path, lines: list[str], ending: str, trailing: str) -> None:
    path.write_text(ending.join(lines) + trailing, encoding="utf-8")


def _select(matches: list[dict[str, object]], task_substring: str) -> dict[str, object]:
    if not matches:
        raise RoadmapError(f"no roadmap line matches: {task_substring!r}")
    if len(matches) > 1:
        texts = "; ".join(str(m.get("text")) for m in matches)
        raise RoadmapError(f"ambiguous substring matches {len(matches)} lines: {texts}")
    return matches[0]


def _update_current_task(root: Path, action: str, task_text: str) -> None:
    """Rewrite the '**Current task:**' line in index.md."""
    index = ToolkitPaths(root).index
    if not index.exists():
        return
    lines, ending = _read_preserving(index)
    trailing = "\n" if lines and index.read_text(encoding="utf-8").endswith("\n") else ""
    if action == "current":
        value = task_text
    else:
        value = "none"
    marker = "**Current task:**"
    for i, line in enumerate(lines):
        if line.strip().startswith(marker):
            lines[i] = f"{marker} {value}"
            break
    _write_preserving(index, lines, ending, trailing)


def set_status(
    root: Path, task_substring: str, new_status: str, now: float | None = None
) -> str:
    """Set exactly one roadmap line's status behind the approval gate."""
    now = time.time() if now is None else now
    path = ToolkitPaths(root).roadmap
    alias = STATUS_ALIASES.get(new_status, new_status)
    if alias not in ("x", "~", " "):
        raise RoadmapError(f"unknown new_status: {new_status!r}")
    entries = parse_roadmap(root)
    matches = [
        e for e in entries if task_substring.casefold() in str(e.get("text")).casefold()
    ]
    selected = _select(matches, task_substring)
    line_no = int(selected["line_no"]) - 1
    task_text = str(selected["text"])

    if alias == "x":
        granted = approvals.find_valid_approval(root, task_text, now)
        if granted is None:
            raise GateError(f"no valid approval for: {task_text}")
        approvals.consume_approval(root, granted, now)
    elif alias == "~" and any(
        e.get("status") == "~" and e["line_no"] != line_no + 1 for e in entries
    ):
        raise RoadmapError("another line is already current ([~])")

    lines, ending = _read_preserving(path)
    trailing = "\n" if path.read_text(encoding="utf-8").endswith("\n") else ""
    lines[line_no] = re.sub(
        r"\[( |~|x)\]", f"[{alias}]", lines[line_no], count=1
    )
    _write_preserving(path, lines, ending, trailing)
    _update_current_task(root, new_status, task_text)
    return lines[line_no].lstrip()
