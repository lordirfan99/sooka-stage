# SookaStage — Issue Register

Updated: 2026-09-17 (UTC+8). Each entry: symptom → root cause → resolution → evidence.

---

## FIXED / PROVEN

### F1 — Stage start no longer requires the Discord UI modal
**Symptom.** Programmatic clicks on the "Start the Stage" modal (topic field + button)
never registered, from CDP `Input.dispatchMouseEvent` or from a scheduled task running
`pyautogui`.
**Root cause.** Two compounding factors: (a) Windows foreground lock — a process in a
scheduled-task/service context cannot take foreground, so synthesised mouse input does
not route to the intended HWND; (b) the topic input is a controlled React field whose
submit button only enables after a real `input` event, with re-renders between frames.
**Resolution.** Skip the UI entirely — use the REST endpoint:

```http
POST /api/v9/stage-instances
{"channel_id":"1477692113738137600","topic":"1)","privacy_level":2,"send_start_notification":false}
```

**Evidence.** `200` for all three channel IDs (`1477692113738137600` topic `1)`,
`1481358977584599283` topic `2)`, `1481359453759475876` topic `3)`). Query endpoint
returns `200` (live) / `404` (not started) as expected.

### F2 — User token extraction
**Symptom.** `GET /api/v9/users/@me` returned `401` with the token read from
`localStorage.token`, and webpack scanning for `getToken` returned nothing.
**Root cause.** `localStorage.token` is stale on Discord desktop 1.0.9258 / 1.0.1220 /
1.0.1177; the accounts' live session tokens are held in memory, not in that key.
**Resolution.** Capture the `Authorization` header from real client traffic: attach one
persistent CDP WebSocket, `Network.enable`, `Page.navigate` to the channel URL, read the
first `Authorization` header. Implemented in `scripts/sniff_token.py`.
**Evidence.** After capture, `/users/@me` → `200`; `/stage-instances` POST → `200`.
**Handling.** Token file `C:\Users\irfan\SookaStage\.user_token.json` is PC-local and
never printed, logged, or committed. Refresh after any client restart.

### F3 — Canary `1.0.1177` installer/updater corruption
**Symptom.** Canary stuck on the splash screen showing `checking-for-updates`, then
exiting.
**Root cause chain** (from `%APPDATA%\discordcanary\logs\DiscordCanary_updater_rCURRENT.log`):
1. The install used `installer.exe /s` (lowercase). The NSIS silent switch is `/S`
   (uppercase); the lowercase form unpacked only the bootstrap, so
   `app-1.0.1177\modules\` was missing.
2. The updater therefore recorded `hosts_req_modules_installed: false` and demanded a
   full reinstall of `1.0.1177`.
3. That reinstall cannot validate while the same version is running:
   `InconsistentInstallerState(Attempt to install host that is currently running …)` →
   the app exits.
**Resolution.** Kill all Canary processes, delete `%LOCALAPPDATA%\DiscordCanary\installer.db`
and `packages\`, reinstall with `/S`.
**Evidence.** `app-1.0.1177\modules\` now present, payload ≈ 442 MB; updater logs
`Already up to date. Nothing to do.`

### F4 — Console window appearing on the PC at every logon
**Symptom.** After a reboot an unprompted Python console window appears, printing
`voice_renamer running. streams= {…}` and periodic `renamed -> …` lines. A second task
also launches the Manager GUI.
**Root cause.** Two Task Scheduler entries with *at logon* triggers, one of them running
`python.exe` (which creates a console) rather than `pythonw.exe`:

| Task | Action |
|---|---|
| `SookaRenamer` | `python.exe -u "…\Restored-Desktop\SookaStream-Windows-x64-v8.6\voice_renamer.py"` |
| `SookaBootFix` | `…\SookaStream-v8.16.exe` |

**Resolution.** Both tasks disabled (`schtasks /change /tn <name> /disable`) and the live
console terminated. If the renamer is reinstated, re-create the task with `pythonw.exe`
and no output redirect.

### F5 — Desktop appeared frozen (clicks did nothing)
**Symptom.** Owner reported the desktop was unclickable; a large empty console window sat
over it. Discord was running but its window was behind.
**Root cause.** A leftover console window from an automation run held foreground —
including one spawned by a scheduled task that used `python.exe` and a `> file` redirect.
**Resolution.** Killed the stray console processes by PID and by an in-session
`taskkill`, deleted the throwaway scheduled tasks, and adopted the windowless execution
pattern (`pythonw.exe` + `-WindowStyle Hidden` + `schtasks /it` + delete after run).
**Evidence.** Successive desktop screenshots captured via the hidden-task pattern showed
the blank console gone.

### F6 — CDP handshake refused on PTB
**Symptom.** Connecting to PTB's DevTools WebSocket failed.
**Root cause.** PTB answers the HTTP handshake with `403` when an `Origin` header is
present and the client was not launched with `--remote-allow-origins`.
**Resolution.** `websocket.create_connection(..., suppress_origin=True)`. Committed as
`a50b02e`.

### F7 — Stable client `/json` endpoint wedging
**Symptom.** `http://127.0.0.1:9223/json/list` hangs or refuses connections after a few
WebSocket sessions.
**Root cause.** Electron serialises the DevTools HTTP endpoint; interleaved short-lived
sessions leave half-open state.
**Resolution.** One `/json` call and one persistent WebSocket per run, closed explicitly.

---

## OPEN

### O1 — Canary `1.0.1177` exits silently 2–7 minutes after launch
**Symptom.** The client starts, renders, loads channels, then exits with no error.
**Reproduced** 5×: with automation flags, bare, and with `--disable-gpu`; before and
after the installer repair (F3). No Crashpad report, no Windows Error Reporting entry, no
`EventID 1000`.
**Observations.** Last recorded activity before each exit is the voice/RTC region-latency
test (`logs\discord-last-webrtc_0`). The only hard crash on this machine in the event log
is Canary `1.0.1165` faulting inside `discord_media.node` (`0xc0000409`).
**Assessment.** A defect in this Canary build on this machine, not an install problem.
**Options.** (a) wait for the next Canary build; (b) host Stream 2 on a different client
build; (c) wrap Canary in a restart watchdog that relaunches it and re-runs the stream
start.
**Impact.** Stream 2 has no reliable host client today.

### O2 — Share-picker flow not verified end-to-end
**State.** `sookastage_prod.py` implements channel → undeafen → join → start_stage →
share picker → tile → go live. Stage start is proven via REST; the picker/tile/Go-Live
selectors have not been matched against a live client on every build.
**Next step.** `HERMES_PLAN.md` Phase 0: run `python sooka_diag.py --buttons` on a client
that is already in a started stage and reconcile real labels with `SELECTORS`.

### O3 — Screen-touching work needs the interactive session
**Symptom.** From a plain SSH session, screen capture fails with *"The handle is
invalid"*; `CopyFromScreen` returns blank/black; opencode run sees no windows.
**Resolution pattern.** `schtasks /create … /it` + `pythonw.exe`, then delete the task.
Documented in `scripts/README.md` and README §4.5.

### O4 — Scheduled-task hygiene
**State.** ~73 `Sook*` tasks accumulated on the PC, many one-shot leftovers. Several had
*at logon* triggers (F4).
**Next step.** Audit and delete everything obsolete; keep only tasks that are part of the
final design, and ensure every one-shot task deletes itself after running.

### O5 — `voice_renamer` still drives channel names
**State.** The renamer rewrites stage channel names to the live match titles, which is
why every part of this project keys on channel ID.
**Next step.** When the renamer is reinstated as a service (windowless), confirm it
resolves channels by ID only, and that nothing in the automation ever matches on a name.

---

## Channel IDs — immutable source of truth

| Stream | Channel ID | Client / port | Topic |
|---|---|---|---|
| 1 | `1477692113738137600` | Discord stable / 9223 | `1)` |
| 2 | `1481358977584599283` | Discord Canary / 9225 | `2)` |
| 3 | `1481359453759475876` | Discord PTB / 9224 | `3)` |

Guild: `1251553669644816518`.
