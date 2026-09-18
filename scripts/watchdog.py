"""Recurring self-heal check -- HERMES_PLAN.md Phase 3.1.

Runs the full preflight (watch-browser windows, Chrome Beta tagging, Discord
clients) then `sookastage_prod.py --all` -- see scripts/preflight.py. This is
the layer that was missing before 2026-09-18: re-driving the *share flow*
does nothing if a Discord client's *process* is gone entirely (port not
listening), which is exactly what happened live -- streams 1 and 3 silently
stayed down for 20+ minutes because the old watchdog only ever re-ran the
picker/tile/go-live steps, never checked whether the client was still running
at all. preflight.ensure_discord_clients() closes that gap.

Registered as a scheduled task that fires every few minutes (see
scripts/README.md for the schtasks command).

Run via pythonw.exe (no console). pythonw has no attached stdout/stderr, so
this redirects both to a file *before* importing anything that logs --
otherwise the first print()/log() call raises and the task fails silently.
The detailed step-by-step log still also lands in sookastage_prod.py's own
LOG_PATH (~/sookastage_prod.log) via direct file I/O, unaffected by this
redirect.
"""
import sys

sys.path.insert(0, r"C:\Users\irfan\Desktop\sooka-stage\scripts")
sys.path.insert(0, r"C:\Users\irfan\Desktop\sooka-stage")

LOG = r"C:\Users\irfan\sookastage_watchdog.log"

with open(LOG, "a", encoding="utf-8", errors="replace", buffering=1) as fh:
    sys.stdout = fh
    sys.stderr = fh
    import preflight
    rc = preflight.run(["--all"])

sys.exit(rc)
