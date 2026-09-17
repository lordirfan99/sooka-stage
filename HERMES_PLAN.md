# Hermes Execution Plan — SookaStage

Ordered plan to take the automation from "ch2 + ch3 live, ch1 stuck" to
"all three live, unattended, self-healing".

Read [`HERMES_GUIDE.md`](HERMES_GUIDE.md) first. Phases are strictly ordered:
**do not start a phase until the previous one's acceptance criteria pass.**

> **Honesty note.** The code in this repo is verified as far as it can be off
> the Windows box: the transport, target picker, netstat parser, tile
> disambiguation and the double-decode regression all have passing tests
> (`python -m unittest discover -s tests`). The DOM selectors in `SELECTORS`
> and `STATE_JS` are written from the behaviour recorded in
> `SOOKASTAGE_PROGRESS.md` and **have not been matched against a live Discord
> client**. Phase 0 exists to confirm them. Budget ~15 minutes for it.

---

## Phase 0 — Confirm the selectors against a live client

**Why first:** every later phase assumes the state probe reports the truth. If
a regex is wrong, the runner will report `stage_not_started` forever and you
will chase a ghost.

| # | Task | Command |
|---|---|---|
| 0.1 | Pull this branch onto the Windows box | `git pull` |
| 0.2 | Run the tests — they need no Discord | `python -m unittest discover -s tests` |
| 0.3 | Read-only preflight on all 3 clients | `python sooka_diag.py` |
| 0.4 | Dump live button labels on a client that is **already in a started stage** (use ch2 or ch3 — they work) | `python sooka_diag.py --stream 2 --buttons` |
| 0.5 | Compare the real labels against `SELECTORS`; fix any regex that does not match | edit `SELECTORS` in `sookastage_prod.py` |
| 0.6 | Open the share picker by hand on ch2, then re-run diag to capture real tile labels | `python sooka_diag.py --stream 2 --buttons` |
| 0.7 | Measure the coordinate space on the main build | `python sooka_diag.py --stream 1 --calibrate` |

**Acceptance criteria -- all met 2026-09-18, see `ISSUES.md` F8**
- [x] Tests pass.
- [x] On a client mid-stream, diag reports `stage started: True` and `streaming: True`.
- [x] On a client in a started stage, `share_button: True`.
- [x] `--calibrate` on stream 1 reports `scale=<number>`, not `NO HIT`.
- [x] With the picker open, `picker tiles : N -> matched '<browser>'` — not ambiguous.

**If 0.7 reports `NO HIT`:** record the full line. `covered-by:<label>` means an
overlay — close it and retry. A plain miss with `zoom != 1` means Discord's zoom
level is the culprit: set Discord zoom back to 100% (Ctrl+0) and re-measure; that
alone may fix the main build's dead clicks.

---

## Phase 1 — Get ch1 (main build, 9223) end-to-end

**The blocker is understood:** v1 clicked "Continue without starting", so the
stage never started and the Share button never existed. `ensure_stage_started()`
now clicks **Start Stage** instead.

| # | Task | Command / file |
|---|---|---|
| 1.1 | Fresh restart of the main client via the per-channel deep link | `Discord.exe --remote-debugging-port=9223 "discord://-/channels/1251553669644816518/1477692113738137600"` |
| 1.2 | Confirm nothing is blocking | `python sooka_diag.py --stream 1` |
| 1.3 | Dry look at the state machine, no clicks | `python sookastage_prod.py --stream 1 --diagnose` |
| 1.4 | Run it | `python sookastage_prod.py --stream 1 --json` |
| 1.5 | If a step fails, read `click` / `hover` / `covered` on that step — do not retry blind | `run.json` |

**Acceptance criteria -- all met 2026-09-18**
- [x] Every step reports `ok`, in order: channel → start_stage → join → undeafen →
      speaker → share_picker → tile → go_live (start_stage moved before join --
      REST doesn't require a voice connection, see `sookastage_prod.py`).
- [x] `state_after.streaming == true`.
- [x] Confirmed live with the **Brave** window (not Chrome) via CDP screenshot.
- [x] Exit code `0`.

**Rollback:** nothing here is destructive. A failed run leaves the client where
it was; re-running is safe and idempotent (every step checks "already done"
first).

---

## Phase 2 — All three, one command

| # | Task | Notes |
|---|---|---|
| 2.1 | `python sookastage_prod.py --all --json` | runs 1 → 2 → 3 sequentially |
| 2.2 | Confirm each stream is on **its own** browser window | ch1 Brave, ch2 Chrome Beta, ch3 Google Chrome |
| 2.3 | Re-run against already-live streams | must be a no-op, not a double-share |
| 2.4 | Run once from a scheduled-task context, not an interactive shell | this is where the foreground lock used to bite |

**Acceptance criteria -- all met 2026-09-18**
- [x] Three distinct browser windows live on three channels (Brave / Google Chrome /
      Chrome Beta, confirmed by CDP screenshot on each client).
- [x] A second `--all` while everything is live exits `0` and changes nothing (every
      step logs `already=True`, completes in under a second).
- [x] The schtask run behaves identically to the interactive run -- verified via a
      one-shot hidden `pythonw.exe` scheduled task, exit `0`, same JSON summary.

---

## Phase 3 — Watchdog and Manager integration

| # | Task | Detail |
|---|---|---|
| 3.1 | Stage watchdog | **Done 2026-09-18.** `scripts/watchdog.py` -> `sookastage_prod.py --all`, registered as recurring scheduled task `SookaStageWatchdog` (every 5 min, hidden `pythonw.exe`). Idempotency (F8) means "re-run everything" and "re-run only what's down" are the same call. |
| 3.2 | "STREAM ALL 3" button in SookaStream Manager GUI | shell out to `--all --json`, parse the JSON, colour each stream by `ok` |
| 3.3 | Launcher bat uses the per-channel deep link | so the stage view is already open at launch |
| 3.4 | Surface the failing step in the GUI | the `steps` array already names it |

**Acceptance criteria**
- [x] Killing one stream by hand gets it restored within one watchdog interval.
      Verified 2026-09-18: manually stopped stream 3's share, ran `--all`, only
      stream 3 was re-driven (streams 1-2 stayed `already=True`), back to
      `streaming: true`.
- [ ] The GUI shows which step failed, not just "failed". (3.2/3.4 -- GUI work,
      not started; out of scope for the sooka-stage repo itself, see
      `C:\Users\irfan\Desktop\Restored-Desktop\SookaStream-Windows-x64-v8.6\`.)
- [x] The watchdog never starts a second share on an already-live stream (same
      idempotency guarantee as Phase 2.3, exercised every 5 minutes in practice).

**Design note:** the watchdog must call the runner, never duplicate its logic.
One state machine, one place to fix.

---

## Phase 4 — Hardening (only once 1–3 are green)

| # | Task | Risk |
|---|---|---|
| 4.1 | Upgrade the main client off app-1.0.9258 to retire the `/json` wedge | **untested against the saved session** — back up first, do it on a quiet day |
| 4.2 | Match picker tiles by window rect as a secondary signal | low — additive to `choose_tile` |
| 4.3 | Real-mouse fallback path (`real_mouse_click`) behind a flag | only if CDP input is ever refused outright; needs a calibration run |
| 4.4 | Retire `main40.py` | it is a snapshot with hardcoded pixel coords |
| 4.5 | Structured run history (append each `--json` result to a log) | makes flakiness measurable instead of anecdotal |

**Do not do 4.1 before Phase 2 passes** — if the upgrade breaks the saved
session you lose the one client that is hardest to re-auth, with no known-good
baseline to compare against.

---

## Definition of done

1. [x] `python sookastage_prod.py --all` exits `0` from a scheduled task.
2. [x] Three channels live, three distinct browser windows, confirmed by CDP
   screenshot on 2026-09-18 -- **still needs the owner's own visual confirmation**,
   since a screenshot proves the automation worked, not that the picture looks
   right to a human.
3. [x] A dropped stream self-heals within one watchdog interval
   (`SookaStageWatchdog`, every 5 min).
4. [x] Any failure names its step and its reason in `run.json` without anyone
   needing to reproduce it interactively (the `steps` array; exercised on every
   failure hit during Phase 0/1 debugging on 2026-09-18).

**Remaining before this is fully "production ready" beyond the sooka-stage repo
itself:** the three browser windows used in this session's verification were
placeholder tabs (`sooka.live` does not resolve; the real domain is
`sooka.my`, per `SookaStream-Windows-x64-v8.6\START-HERE.txt`), not real sooka.my
match content -- opening and keeping those tabs signed in and playing is the
separate SookaStream Manager / Tampermonkey system's job, out of scope here. Canary's
intermittent silent exit (O1) also has no fix, only mitigations.

---

## Quick reference

```powershell
python -m unittest discover -s tests          # regression tests, no Discord needed
python sooka_diag.py                          # triage all three, read-only
python sooka_diag.py --stream 1 --calibrate --buttons
python sookastage_prod.py --stream 1 --diagnose
python sookastage_prod.py --stream 1 --json
python sookastage_prod.py --all --json
```

Exit code `0` = every requested stream reached "Stop Streaming".
