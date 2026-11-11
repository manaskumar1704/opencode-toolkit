"""Security regression tests: state permissions and the static scanner."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from octk.approvals import create_approval

ROOT = Path(__file__).resolve().parents[1]


def _load_scanner():
    path = ROOT / "scripts" / "security_scan.py"
    spec = importlib.util.spec_from_file_location("octk_security_scan", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_approvals_file_is_owner_only(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("POSIX permission bits only")
    create_approval(tmp_path, "some task")
    path = tmp_path / ".toolkit" / "approvals.json"
    assert path.is_file()
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600, f"approvals.json is {oct(mode)}"


def test_scan_has_no_high_findings() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "security_scan.py"), "--json"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    findings = json.loads(proc.stdout)
    high = [f for f in findings if f["severity"] == "HIGH"]
    assert not high, high
    assert proc.returncode == 0


def test_scanner_detects_shell_true(tmp_path: Path) -> None:
    scanner = _load_scanner()
    source = tmp_path / "bad.py"
    source.write_text(
        "import subprocess\nsubprocess.run('ls', shell=True)\n", encoding="utf-8"
    )

    import ast

    findings = scanner.check_shell_and_exec(
        source, ast.parse(source.read_text(encoding="utf-8"))
    )

    assert any(f.check == "shell-true" and f.severity == "HIGH" for f in findings)


def test_scanner_detects_hardcoded_secret(tmp_path: Path) -> None:
    scanner = _load_scanner()
    source = tmp_path / "secret.py"
    source.write_text('api_key = "abcdefghijklmnopqrstuvwx"\n', encoding="utf-8")

    findings = scanner.check_secrets(source)

    assert any(f.check == "hardcoded-secret" for f in findings)


def test_scanner_flags_subprocess_without_timeout(tmp_path: Path) -> None:
    scanner = _load_scanner()
    source = tmp_path / "slow.py"
    source.write_text(
        "import subprocess\nsubprocess.run(['ls'])\n", encoding="utf-8"
    )

    import ast

    findings = scanner.check_subprocess_timeout(
        source, ast.parse(source.read_text(encoding="utf-8"))
    )

    assert any(f.check == "subprocess-no-timeout" for f in findings)
