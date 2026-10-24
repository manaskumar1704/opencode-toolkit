name: windows-shell-discipline
description: Rules for running commands in the OpenCode harness on Windows, where the shell is Git Bash and PowerShell syntax breaks it. Load before running multi-step shell commands, chained one-liners, uv/bun invocations, or anything with quotes and pipes.
---

# Windows shell discipline (OpenCode harness)

The harness runs commands with Git Bash (`/usr/bin/bash`), never PowerShell.
The catastrophic failures of Oct 2026 all came from forgetting this.

## Rules

1. **Never PowerShell syntax.** `& $b -lc '...'`, `$var = ...`, `foreach (...) {}`,
   `ConvertFrom-Json` — all of it either crashes (`syntax error near unexpected
   token '&'`) or works once and fails the next time the harness re-resolves its
   shell. If you catch yourself writing `& $`, stop and rewrite in bash.
2. **One line per shell call.** Multi-line pipelines (`line1
\nline2`) have
   produced `command not found` for tools that worked when the same content was
   chained with `;` on a single line. Prefer `;`-joined single lines.
3. **No inline quoting for interpreters.** A `python -c "multi-line with nested
   quotes"` string WILL break on the second layer of quoting. Write the snippet
   to a temp file (temp dir is pre-approved) and run `uv run python /c/.../file.py`.
4. **Git Bash's `usr/bin` can vanish from `PATH` mid-session.** Symptom:
   `tail`, `head`, `grep`, `ls` suddenly all report `command not found`, while
   `curl.exe`, `bun`, `node` still work. Repair at the start of the call:

   ```bash
   export PATH="/c/Program Files/Git/usr/bin:$PATH"
   ```

5. **Git Bash path-mangles arguments that start with `/`.** A `--regex
   "/pattern/i"` argument is rewritten into `C:\Program Files\Git\pattern` as a
   literal. Match strings for tools must not lead with a slash; use plain text
   search (`find "Sent"`) or grep the printed snapshot files instead.
6. **`-match`/`regex` checks must be case-sensitive when strings differ only by
   case.** A PowerShell-style `-match` is case-insensitive by default and
   produced a false-positive "route deleted" check against
   `"detail":"Not found."` vs `"detail":"Not Found"` on Oct 22. Use exact
   string comparison or `-ceq`.
7. **Compare what the tool ACTUALLY emitted, not a sampled transformation.**
   Filtering a stream with `grep -oE` before looking at the raw output hid an
   error event twice. Dump raw first, filter second.
8. **`uv run` context.** From the repo root, `uv run --project apps/api python
   script.py` works; running a script that imports `app.main` needs
   `PYTHONPATH=.` or `cd apps/api` first.
9. **Prefer dedicated tools** (read/grep/glob/edit) over shell commands whenever
   they exist; shell is the fallback, not the default.
