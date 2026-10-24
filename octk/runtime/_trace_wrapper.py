"""Run a script under runpy and print project-local frames with locals."""

from __future__ import annotations

import os
import runpy
import sys
import traceback
from pathlib import Path

EXCLUDED = {".venv", "venv", "site-packages", "node_modules", "__pycache__"}


def _is_project_file(path_str: str, root: Path) -> bool:
    try:
        resolved = Path(path_str).resolve()
        resolved.relative_to(root.resolve())
    except (ValueError, OSError):
        return False
    parts = {p.lower() for p in resolved.parts}
    return not (parts & EXCLUDED)


def _print_frames(tb, root: Path, max_locals_repr: int = 200) -> None:
    for frame, line_no in traceback.walk_tb(tb):
        tfile = frame.f_code.co_filename
        if not _is_project_file(str(tfile), root):
            continue
        func = frame.f_code.co_name
        print(f'  File "{Path(tfile).as_posix()}", line {line_no}, in {func}')
        try:
            with open(tfile, encoding="utf-8", errors="replace") as handle:
                source = (handle.read().splitlines() or [""])[line_no - 1]
            print(f"    {source.strip()}")
        except OSError:
            pass
        for name, value in frame.f_locals.items():
            rep = repr(value)
            if len(rep) > max_locals_repr:
                rep = rep[:max_locals_repr] + " (truncated)"
            print(f"    local {name} = {rep}")


def main() -> int:
    """Entrypoint: python -m octk.runtime._trace_wrapper script.py [args]."""
    if len(sys.argv) < 2:
        print("usage: python -m octk.runtime._trace_wrapper script.py [args]", file=sys.stderr)
        return 2
    script = sys.argv[1]
    root = Path(os.environ.get("OCTK_ROOT") or Path.cwd()).resolve()
    sys.argv = [script, *sys.argv[2:]]
    try:
        runpy.run_path(script, run_name="__main__")
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001 - this wrapper reports and re-exits
        exc = traceback.TracebackException.from_exception(sys.exc_info()[1])
        print(f"Uncaught exception: {exc.exc_type.__name__}: {exc}", flush=True)
        print("Traceback (most recent call last) [octk: project frames only]:", flush=True)
        _print_frames(sys.exc_info()[2], root)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
