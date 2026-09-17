"""Recurring self-heal check -- HERMES_PLAN.md Phase 3.1.

Runs `sookastage_prod.py --all`, which is idempotent: streams already live are
untouched (every step short-circuits on "already"), only a stream whose
`streaming` state is false gets re-driven through the flow. Registered as a
scheduled task that fires every few minutes (see scripts/README.md for the
schtasks command) -- one state machine, no separate watchdog logic, per
HERMES_PLAN.md Phase 3's design note.

Run via pythonw.exe (no console). pythonw has no attached stdout/stderr, so
this redirects both to a file *before* importing sookastage_prod -- otherwise
its first `print()`/log() call raises and the task fails silently. The
detailed step-by-step log still also lands in sookastage_prod.py's own
LOG_PATH (~/sookastage_prod.log) via direct file I/O, unaffected by this
redirect.
"""
import sys

sys.path.insert(0, r"C:\Users\irfan\Desktop\sooka-stage")

LOG = r"C:\Users\irfan\sookastage_watchdog.log"

with open(LOG, "a", encoding="utf-8", errors="replace") as fh:
    sys.stdout = fh
    sys.stderr = fh
    import sookastage_prod
    rc = sookastage_prod.main(["--all"])

sys.exit(rc)
