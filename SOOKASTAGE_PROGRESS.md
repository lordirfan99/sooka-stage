# SookaStage — Stage Automation Progress & Known Issues
Last updated: 2026-09-17 (Malaysia timezone)

## Architecture
Automation flows are split per Discord client (3 streamers):
| Stream | Discord client | CDP port | sooka browser | Stage channel ID |
|---|---|---|---|---|
| 1 | Discord (stable) | 9223 | Brave | 1477692113738137600 |
| 2 | Canary | 9225 | Chrome Beta | 1481358977584599283 |
| 3 | PTB | 9224 | Google Chrome | 1481359453759475876 |

Flow per client: deep-link nav (channel-ID is source of truth, not name — names
are rewritten live by voice_renamer) → undeafen if needed → join stage (li → a
DOM click works without focus) → **Start Stage** (topic modal, prefill topic) →
**Share Your Screen** → tile select (match the target browser, refuse to guess)
→ **Go Live**. Every step verifies its own postcondition before the next runs.

## Working (verified live)
- Streamer2 (Canary/9225) & Streamer3 (PTB/9224) — full end-to-end automation
  success, screenshare sooka browser live (panel text
  `Watch online Live Sports, sooka - Brave 1440p 60FPS`).
- Join stage via DOM `li a.click()` — no window focus needed.
- Undeafen shortcut `Ctrl+Shift+D`.
- Main (9223) completed FULL flow once (screenshare live verified visually) but
  is not stable across reruns — see issues.

## Root causes identified
1. **Old main build (app-1.0.9258) DevTools wedging** — HTTP `/json` endpoint
   sticks after a few WebSocket sessions. PTB/Canary builds (app-1.0.117x)
   unaffected. Mitigated: `http_json()` retries, and the runner makes exactly
   one `/json` call then keeps a single persistent ws for the whole process.
   Deep-link relaunch `Discord.exe --remote-debugging-port=9223
   "discord://-/channels/GUILD_ID/CHANNEL_ID"` correctly restores stage view.
2. **"Server Deafened" permission modal blocks share flow** — every share click
   while deafened spawns the modal instead of the picker. Fixed:
   `ensure_undeafened()` clicks Undeafen (that button exists only while
   deafened), falls back to `Ctrl+Shift+D`, then verifies the state flipped.
3. **Stage must be STARTED before the Share button exists.** This was the ch1
   blocker — and the v1 runner made it permanent by clicking "Continue without
   starting", the one branch that guarantees the stage does not start. Fixed:
   `ensure_stage_started()` types the topic and clicks **Start Stage**.
4. **voice_renamer rewrites channel names live** — NEVER match a stage by name;
   channel ID only. Implemented; name hints are dead.
5. **Share picker tile selection** — all sooka windows share the page title
   ("Watch online Live Sports…"), differing only by browser suffix, and
   `"chrome" in label` matches both Chrome Beta and Google Chrome, which put two
   streams on one window. Fixed: `choose_tile()` resolves each tile to its
   longest known browser phrase and **refuses to click** when two tiles are
   indistinguishable.
6. **sooka PiP floating window covering clicks** — no longer relevant on the CDP
   path. `Input.dispatchMouseEvent` goes to the renderer, so overlay windows
   (PiP, the Codex ComputerUse overlay, the topmost watchdog) cannot intercept
   it. This only ever affected the `pyautogui` approach in `main40.py`.

## Runner defects found in the v1 draft (2026-09-17 review)
The v1 `sookastage_prod.py` could not have worked, for reasons independent of
Discord:

- **Every click was a silent no-op.** `ev()` parsed the JSON returned by
  `Runtime.evaluate`, then `clipped_click` parsed the resulting dict *again* →
  `TypeError` → swallowed by `except Exception` → `d = None` → `return None`.
- **Steps 3 and 4 aimed at the wrong element.** Their predicates never
  referenced the element under test, so `.find(x => …)` returned the first
  button on the page instead of the picker tile / Go Live button.
- **Wrong branch at step 1** — "Continue without starting" (root cause #3).
- WebSocket opcode ignored → one PING or fragmented frame killed the run.
- `[t for t in j …][0]` → `IndexError` when the client was on another view.
- `findstr ":9223"` matched `19223` and remote ports, and kept the last match.
- `get_win_rect_by_pid` could return `None`, unpacked into six names next line.
- No `try/except` in `main()`, and `log()` swallowed everything → scheduled-task
  failures were invisible.

Full table with effects: [`HERMES_GUIDE.md`](HERMES_GUIDE.md) §5.

## Current state as of this commit
- Runner rewritten as a verified state machine (`sookastage_prod.py`) on a
  hardened CDP client (`sooka_cdp.py`), plus a preflight triage tool
  (`sooka_diag.py`) and regression tests (`tests/test_sooka.py`, 24 passing).
- Clicks are now **hit-tested**: dispatch `mouseMoved`, confirm via
  `document.querySelectorAll(':hover')` (which only trusted input can set), and
  only then press. A click that cannot land is reported as failed with its
  reason (`covered-by:<what>` / `no-coordinate-hit`) instead of passing silently.
- Coordinate-space mismatch between `getBoundingClientRect()` and
  `Input.dispatchMouseEvent` (the likely cause of "rect click does not register
  on main build") is handled by a self-calibrating scale ladder; measure it with
  `sooka_diag.py --calibrate`.
- ch2 + ch3: LIVE via screenshare automation.
- ch1 (1477692113738137600): awaiting a run of the fixed flow on the box.
- **Not yet verified against live Discord:** the DOM selectors in `SELECTORS` and
  `STATE_JS`. Phase 0 of [`HERMES_PLAN.md`](HERMES_PLAN.md) confirms them;
  `sooka_diag.py --buttons` prints the live labels.
- Ghost cmd consoles + one-shot schtasks cleaned; only operational tasks remain
  (SookaBootFix, SookaRenamer, SookCDP, SookDLaunch, SookTopWatch).

## Next steps
Tracked as ordered phases with acceptance criteria in
[`HERMES_PLAN.md`](HERMES_PLAN.md):

0. Confirm the selectors against a live client (~15 min, do this first).
1. Get ch1 end-to-end on the fixed flow.
2. `--all` from a scheduled-task context; three distinct browser windows.
3. Stage watchdog + "STREAM ALL 3" button in the SookaStream Manager GUI.
4. Hardening — upgrade the main client off app-1.0.9258 to retire the `/json`
   wedge (untested against the saved session; back up first), retire `main40.py`.
