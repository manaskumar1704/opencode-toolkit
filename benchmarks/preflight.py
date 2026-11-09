"""Pre-flight checks for the benchmark cohort.

The primary cohort is locked to OpenCode + ``opencode-go/beam-free`` at
``high`` effort. The runner must refuse to start otherwise.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MODEL_ID = "opencode-go/beam-free"
EFFORT_REQUIRED = "high"


@dataclass
class PreflightResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    opencode_version: str = ""
    model_available: bool = False
    effort_values: dict[str, str] = field(default_factory=dict)
    effort_ok: bool = False
    opencode_json_present: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "opencode_version": self.opencode_version,
            "model_available": self.model_available,
            "effort_values": dict(self.effort_values),
            "effort_ok": self.effort_ok,
            "opencode_json_present": self.opencode_json_present,
        }


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, errors="replace"
        )
        return proc.returncode, proc.stdout, proc.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 127, "", str(exc)


def check_opencode_binary() -> tuple[bool, str]:
    """Return (present, path_or_error)."""
    path = shutil.which("opencode")
    if path is None:
        return False, "opencode binary not found on PATH"
    return True, path


def check_opencode_version() -> tuple[bool, str]:
    code, out, err = _run(["opencode", "--version"])
    text = (out + "\n" + err).strip()
    if code != 0:
        return False, f"opencode --version failed ({code}): {text}"
    # first line is the version
    first = text.splitlines()[0] if text else ""
    return True, first


def check_model_available() -> tuple[bool, str]:
    """Confirm opencode-go/beam-free is in the catalogue."""
    code, out, err = _run(["opencode", "models"])
    text = (out + "\n" + err).strip()
    if code != 0:
        return False, f"opencode models failed ({code}): {text}"
    if MODEL_ID in text:
        return True, MODEL_ID
    # fall back to scanning for the catalogue entry
    if "beam-free" in text:
        return False, f"catalogue entry 'beam-free' found but full id {MODEL_ID!r} not present"
    return False, f"{MODEL_ID!r} not found in opencode models"


def check_effort(root: Path) -> tuple[bool, dict[str, str]]:
    """Read .opencode/agents/*.md frontmatter and collect effort values."""
    agents_dir = root / ".opencode" / "agents"
    if not agents_dir.is_dir():
        return False, {}
    values: dict[str, str] = {}
    for path in sorted(agents_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        match = re.search(r"(?m)^effort:\s*(\S+)\s*$", text)
        values[path.stem] = match.group(1) if match else ""
    if not values:
        return False, values
    ok = all(value == EFFORT_REQUIRED for value in values.values())
    return ok, values


def check_opencode_json(root: Path) -> bool:
    path = root / "opencode.json"
    if not path.exists():
        return False
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return False
    return isinstance(data, dict)


def run_preflight(root: Path) -> PreflightResult:
    """Run every check and return a structured result. Never raises."""
    errors: list[str] = []
    result = PreflightResult(ok=False)

    present, detail = check_opencode_binary()
    if not present:
        errors.append(detail)
        result.errors = errors
        return result

    ok, version = check_opencode_version()
    if not ok:
        errors.append(version)
    else:
        result.opencode_version = version

    ok, model_detail = check_model_available()
    result.model_available = ok
    if not ok:
        errors.append(model_detail)

    effort_ok, effort_values = check_effort(root)
    result.effort_values = effort_values
    result.effort_ok = effort_ok
    if not effort_ok:
        if not effort_values:
            errors.append("no agent files found; run `octk init` first")
        else:
            bad = {k: v for k, v in effort_values.items() if v != EFFORT_REQUIRED}
            errors.append(f"effort must be {EFFORT_REQUIRED!r}; got {bad}")

    result.opencode_json_present = check_opencode_json(root)
    if not result.opencode_json_present:
        errors.append("opencode.json missing or invalid; run `octk init`")

    result.errors = errors
    result.ok = not errors
    return result
