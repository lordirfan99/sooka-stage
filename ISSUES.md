# SookaStage — Issue Register

Updated: 2026-09-18 (UTC+8). Each entry: symptom → root cause → resolution → evidence.

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

### F8 — Share-picker flow verified end-to-end on all three clients
**Symptom.** `open_picker()`/`select_tile()`/`go_live()` were written from recorded
behaviour and had never been matched against a live client (O2, below).
**Root causes found running Phase 0 live** (all in `sookastage_prod.py`):
1. `ensure_speaker()` read `speak_on_stage`/`share_button` with zero delay right after
   the join click. Discord's audience panel takes a moment to render, and
   `share_button`/`streaming` can themselves flicker `true` for a single frame before
   settling back to audience -- trusting either same-frame read skipped the "Speak on
   Stage" click entirely, leaving the account in the audience with no Share button.
2. `STATE_JS.picker_open` required a `[role=dialog]` **and** an existing "Go Live"
   button. On this build the share picker's own dialog never gets a `[role=dialog]`
   Go-Live button until *after* a tile is picked, so `picker_open` was always false and
   every run timed out waiting for it.
3. `browser_identity()` picked the **longest** matching browser phrase. Chrome Beta's
   own OS window title suffix on this machine is `"<title> - Google Chrome"` (no
   "Beta") -- only the page title carries the identity marker (normally injected by
   Tampermonkey's "Set Browser Identity") -- so a real Chrome Beta tile's label
   contains *both* `"chrome beta"` and `"google chrome"`, and the longer string
   (`"google chrome"`) silently won, reclassifying every Chrome Beta tile as plain
   Chrome.
4. `find()`'s visibility check (`sooka_cdp.py`) requires the element to intersect the
   current viewport. The tile grid scrolls, and the matched tile is frequently below
   the fold -- reported as `click='not-found'` even though `TILE_JS` (which has no
   viewport check) listed the tile correctly.
5. `open_picker()` / `select_tile()` / `go_live()` had no "already streaming" guard, so
   re-running against an already-live stream failed at the picker step instead of being
   a no-op (HERMES_PLAN.md Phase 2.3).
**Resolution.** Poll for `speak_on_stage` before deciding it doesn't exist and act on it
first when present; loosened `picker_open` to the picker's own tab-bar text instead of
requiring Go Live; made `browser_identity()` check specific names before the generic
`"google chrome"` fallback (see `tests/test_sooka.py::test_chrome_beta_wins_when_label_also_contains_google_chrome`);
`scrollIntoView()` the matched tile before clicking it; added an "already streaming"
short-circuit to all three trailing steps.
**Evidence.** 2026-09-18: all three streams (`Discord stable/9223`, `Canary/9225`,
`PTB/9224`) reached `streaming: true` end-to-end, confirmed by screenshot (LIVE badge,
"Sharing their screen"). `--all` re-run against three already-live streams: every step
`already=True`, exit `0`, in under a second. Verified identical from a hidden
`pythonw.exe` scheduled-task context (Phase 2.4). Self-heal verified: manually stopped
stream 3's share, re-ran `--all`, only stream 3 was re-driven (streams 1–2 untouched),
back to `streaming: true`.

### F9 — Scheduled-task hygiene
**State.** ~73 `Sook*` tasks had accumulated on the PC (one-shot debugging iterations,
several duplicating each other).
**Resolution.** Audited every task's command line against what's actually current
(`schtask_launch_client.ps1`, `sookastage_prod.py`); deleted 67, kept 6:
`SookaStageProd`, `SookStage9223`/`9224`/`9225` (canonical per-client launchers),
`SookaBootFix`/`SookaRenamer` (already `Disabled`, legitimate utilities). Deletion
needed an elevated (but still silent -- `ConsentPromptBehaviorAdmin=0` on this machine)
`Unregister-ScheduledTask`, since a plain non-elevated session gets `Access is denied`
even for tasks it owns.
**Follow-up.** Added `SookaStageWatchdog` (recurring, every 5 min, `pythonw.exe`,
`/it`) running `scripts/watchdog.py` -> `sookastage_prod.py --all` for Phase 3.1
self-healing. Not one-shot -- intentionally left registered.

---

### F10 — Every stream stuck in Audience with no Share button (flow ordering)
**Symptom.** `start_stage` logged `http 200`, but `GET /stage-instances/<ch>` returned
`404` for all three channels moments later; the client kept showing "Start Stage", the
account sat in **Audience**, and `share_picker` failed ~20s later — sometimes with a
missed click, sometimes with a landed click (`hover='hit'`) that opened nothing.
**Root cause.** The stage was created *before* joining the voice channel, so it had zero
speakers and Discord auto-ended it within seconds. The 200 was real; the instance just
did not survive.
**Resolution.** Order is now `channel → join → undeafen → start_stage → speaker → …`.
Joining first also means the REST call is made as a connected moderator, which is what
puts the account on stage as a speaker rather than in the audience.
**Evidence.** All eight steps clean in ~6s; `GET /stage-instances` returns LIVE
afterwards for all three channels with topics `1`/`2`/`3`.

### F11 — `join` could never work: the channel anchor has no href
**Symptom.** `[FAIL] join via='not-found'` on every client, after a 25s timeout.
**Root cause.** `by_href()` required an `<a>` whose `href` ends in the channel ID, but
Discord renders the row as `<a role=… data-list-item-id="channels___<id>">` with
`href=null`, so the predicate never matched anything.
**Resolution.** Accept either form, still strictly by ID (never by name — the renamer
rewrites those live). Two regression tests cover it.
**Also.** `ensure_in_stage()` used to infer "already joined" from the *absence* of a
Join Stage button — but when the stage is not started there is no such button at all,
so that inference silently skipped the join and every later step then worked against a
channel we were not connected to. It now checks a real `voice_connected` signal.

### F12 — Channel row below the fold fails as `not-found`
**Symptom.** Join worked on stable but failed on Canary with the same predicate.
**Root cause.** `find()` requires the element to intersect the viewport. Measured live:
the row sat at y=680 in a 519px-tall Canary window (y=409 on stable). Same trap as the
picker tiles.
**Resolution.** `scrollIntoView({block:'center'})` before the click.

### F13 — Discord auto-updates broke the launcher two ways
**Symptom.** Canary updated 1.0.1177 → 1.0.1181; launcher reported `EXE NOT FOUND` and
stream 2 stayed down with the watchdog unable to heal it.
**Root cause.** (a) the exe path was hard-coded per build, and an update leaves the old
`app-*` directory behind but strips its exe; (b) after updating, Discord relaunches
*itself* without `--remote-debugging-port`, and since it is single-instance, launching
again just hands off to that live instance and silently drops the flags.
**Resolution.** Resolve the newest `app-<version>` that actually contains the exe
(compared as `[version]`, so `app-1.0.999` cannot outrank `app-1.0.1000`), and stop a
running-but-portless instance by PID before launching.

### F14 — A wedged client stalled the whole system indefinitely
**Symptom.** A run sat on stream 3 for 15+ minutes holding the single-run lock, so every
watchdog pass behind it was skipped.
**Root cause.** PTB was listening on 9224 while `/json` never answered and its UI thread
was hung; `focus_client`'s `AttachThreadInput` blocks forever attaching to a hung GUI
thread. `netstat` was also unbounded.
**Resolution.** Each stream runs in a daemon thread bounded by
`SOOKASTAGE_STREAM_TIMEOUT` (default 180s) and `netstat` got a timeout. A hang in the
self-healing path silently disables self-healing, which is worse than one stream down.

### F15 — Watchdog healed share state but never a dead client
**Symptom.** Streams 1 and 3 stayed down 20+ minutes while the watchdog reported healthy.
**Root cause.** It only re-ran `sookastage_prod.py --all`, which re-drives the *share
flow*; if a client's *process* is gone (port not listening at all) there is nothing to
drive. Same class of gap: preflight's Brave check used `path_hint=None`, so it matched
*any* browser's sooka window and reported "Brave : already open" when no Brave window
existed.
**Resolution.** `scripts/preflight.py` ensures the watch windows and the Discord clients
themselves are up before handing off to the runner; every browser matches on its own
executable path.
**Evidence.** Killed Discord stable (6 procs) plus the Brave watch window; one watchdog
pass relaunched the client, reopened the window, and returned all three to
`streaming:true`.

### F16 — Concurrent runs drove the same clients at once
**Symptom.** Flaky `no-coordinate-hit` / "clicked but nothing opened" failures.
**Root cause.** The 5-minute watchdog task fired while a hand-run `--all` was mid-flight:
two CDP sessions per client and clicks landing in the other run's half-open picker.
**Resolution.** A PID lock (`sookastage.lock`) in `main()`; the loser exits 0. Stale
locks (holder PID gone) are taken over, or a crashed run would disable healing forever.

### F17 — Renamer was never actually running
**Symptom.** Channel names/topics never changed.
**Root cause.** The `SookaRenamer` task was disabled (correctly — it ran `python.exe`
and spawned a console window every logon, F4) and nothing replaced it.
**Resolution.** `run_renamer_headless.py` (pythonw + line-buffered log), started by the
one-click launcher when not already running.
**Note.** A `—` rendering as `?` in terminal output here is a console display artifact,
not data corruption: the stored Discord topic was verified byte-for-byte as U+2014.

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
**2026-09-18 update.** Launched via `schtask_launch_client.ps1 -Stream 2` at 00:28, still
running and streaming live past 01:40 (70+ minutes) -- well beyond the documented 2–7
minute window. Not closing this issue: it is intermittent and 70 minutes of one session
is not proof it cannot recur, but it did not reproduce during this session's extended
live run.
**2026-09-18 (later) update.** Canary auto-updated to **`app-1.0.1181`**, so this issue's
title version is no longer the build in use; the silent-exit behaviour did not recur on
1.0.1181 during this session. The update itself caused two *different* failures, now
fixed — see F13. Stream 2 has since run clean through repeated full passes.
**Assessment.** A defect in that Canary build on this machine, not an install problem.
**Options.** (a) wait for the next Canary build; (b) host Stream 2 on a different client
build; (c) wrap Canary in a restart watchdog that relaunches it and re-runs the stream
start -- partially covered now by `SookaStageWatchdog` (F9), which re-runs the *stream*
flow every 5 min but does not relaunch the *client process* if Canary itself exits.
**Impact.** Stream 2 has no reliable host client today.

### O3 — Screen-touching work needs the interactive session
**Symptom.** From a plain SSH session, screen capture fails with *"The handle is
invalid"*; `CopyFromScreen` returns blank/black; opencode run sees no windows.
**Resolution pattern.** `schtasks /create … /it` + `pythonw.exe`, then delete the task.
Documented in `scripts/README.md` and README §4.5.

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
