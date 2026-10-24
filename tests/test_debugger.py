"""Debugger pruning: hand-written samples plus two real runs."""

from __future__ import annotations

import sys
from pathlib import Path

from octk.runtime.debugger import prune_output, run_smart_debugger
from octk.runtime.safety import CommandNotAllowed

PYTEST_SAMPLE = """\
================================== FAILURES ==================================
_________________________________ test_load __________________________________

.venv/lib/python3.12/site-packages/_pytest/runner.py:511: in from_call
    result = func()
F841 ignored
FakeLib: third-party noise line
/usr/lib/python3.12/json/decoder.py:355: in raw_decode
        obj, end = self.scan_once(s, idx)
E       json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)

.venv/lib/python3.12/site-packages/fakelib/wrap.py:10: in pass_through
        return pass_through_payload(data)
        payload    = '{noise at non-project frame}'
project_loader.py:9: in decode
        return json.loads(data)
        payload    = '{bad json payload...long...}'
E       ValueError: bad json
=========================== short test summary info =========================
FAILED tests/test_x.py::test_load - ValueError: bad json
==================== 1 failed, 0 passed in 0.10s ============================
"""

STD_SAMPLE = """\
Traceback (most recent call last):
  File "C:/Users/proj/.venv/Lib/site-packages/pydantic/v1.py", line 10, in wrap
        return fn(*args)
  File "C:/Python314/Lib/json/decoder.py", line 355, in raw_decode
        obj, end = self.scan_once(s, idx)
  File "C:/Users/proj/app/loader.py", line 10, in decode
        return json.loads(payload)
        local payload = 'noisy value wider than 200 chars ...' (truncated)
E       ValueError: invalid input value
"""


def test_pytest_short_sample_prunes_nonproject(tmp_path: Path) -> None:
    pruned = prune_output(PYTEST_SAMPLE, tmp_path, max_chars=2500)
    assert "site-packages/x.py" not in pruned and "_pytest/runner.py" not in pruned
    assert "/usr/lib/python3.12/json/decoder.py" not in pruned
    assert "FakeLib" not in pruned
    assert "project_loader.py:9" in pruned
    assert "E       ValueError: bad json" in pruned
    assert "payload" in pruned
    assert "FAILED tests/test_x.py::test_load" in pruned
    assert len(pruned) <= 2500


def test_std_traceback_sample_prunes_nonproject(tmp_path: Path) -> None:
    # sample paths are fake; use the sample's own root so the project
    # frame (loader.py) resolves under it
    pruned = prune_output(STD_SAMPLE, Path("C:/Users/proj"), max_chars=2500)
    assert "pydantic/v1.py" not in pruned
    assert "C:/Python314/Lib/json/decoder.py" not in pruned
    assert "C:/Users/proj/app/loader.py" in pruned
    assert "local payload" in pruned
    assert "ValueError: invalid input value" in pruned
    assert len(pruned) <= 2500


def test_all_dropped_fallback(tmp_path: Path) -> None:
    raw = "\n".join(f'  File "C:/Python314/Lib/x.py", line {i}, in f' for i in range(5))
    pruned = prune_output("Traceback (most recent call last):\n" + raw, tmp_path)
    assert "(no project frames found)" in pruned
    assert len(pruned) <= 1600


def test_windows_path_sample(tmp_path: Path) -> None:
    win = (
        ".venv\\Lib\\site-packages\\wrong.py:5: in helper\n"
        "    return boom()\n"
        "C:\\Users\\proj\\app\\loader.py:12: in decode\n"
        "    return json.loads(payload)\n"
        "E       ValueError: boom\n"
    )
    pruned = prune_output(win, Path("C:/Users/proj"), max_chars=2000)
    assert "wrong.py" not in pruned
    assert "C:\\Users\\proj\\app\\loader.py" in pruned or "loader.py:12" in pruned
    assert "boom" in pruned


def test_truncation_marker(tmp_path: Path) -> None:
    padding = "\n".join(f"project_pad_{i}.py:{i}: in pad\n    code = {i}" for i in range(600))
    raw = padding + "\nE   ValueError: the tail must survive\n"
    pruned = prune_output(raw, tmp_path, max_chars=2000)
    assert "truncated" in pruned
    assert "the tail must survive" in pruned
    assert len(pruned) <= 2000


def test_real_pytest_run(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_bad():\n    assert 1 == 2\n", encoding="utf-8")
    result = run_smart_debugger("pytest tests/test_x.py", tmp_path, None)
    assert result.raw_chars > result.pruned_chars > 0
    assert "test_bad" in result.text or "FAILED" in result.text


def test_real_failing_script_shows_locals(tmp_path: Path) -> None:
    script = tmp_path / "app.py"
    script.write_text(
        "payload = {'deep': 'value'}\n"
        "def detonate():\n"
        "    raise RuntimeError('kaboom-local')\n"
        "detonate()\n",
        encoding="utf-8",
    )
    result = run_smart_debugger(f"python {script}", tmp_path, {"allowed_commands": ["python"], "command_timeout_s": 60})
    assert "kaboom-local" in result.text
    assert "payload" in result.text


def test_non_allowlisted_rejected(tmp_path: Path) -> None:
    with __import__("pytest").raises(CommandNotAllowed):
        run_smart_debugger("curl http://evil/", tmp_path, {"allowed_commands": ["pytest"]})
