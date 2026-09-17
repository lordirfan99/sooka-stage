# SookaStage — Discord Stage Screenshare Automation

Automation that mirrors three live **sooka.live** match streams into three Discord
**Stage channels** in parallel, one stream per Discord client, driven from a Linux
VPS against the owner's Windows PC over Tailscale.

**Status:** Core automation done. The stage *lifecycle* (start / edit / stop, topic,
state queries) and the *screenshare picker* flow (open picker → select the sooka
browser tile → Go Live) are both automated and verified end-to-end on all three
clients as of 2026-09-18, including idempotent re-runs and self-healing via a
5-minute watchdog (`SookaStageWatchdog`). Open items are Canary's intermittent
silent exit (O1) and Manager GUI integration (Phase 3.2+). See
[`ISSUES.md`](ISSUES.md) for the open list.

---

## 0. Reading order

| Doc | What it is |
|---|---|
| **README.md** (this file) | System architecture, environments, operating procedure, conventions |
| **[HANDOVER.md](HANDOVER.md)** | Handover brief: current state, what is proven, what is next, how to verify |
| [HERMES_GUIDE.md](HERMES_GUIDE.md) | Operator guide: how the automation works, failure catalogue, hard rules |
| [HERMES_PLAN.md](HERMES_PLAN.md) | Ordered phase plan with acceptance criteria |
| [ISSUES.md](ISSUES.md) | Fixed / open issue register |
| [SOOKASTAGE_PROGRESS.md](SOOKASTAGE_PROGRESS.md) | Chronological status log |

---

## 1. System overview

### 1.1 Topology

```
┌───────────────────────────────┐        ┌──────────────────────────────────────────┐
│ Linux VPS — control host      │  SSH   │ Windows PC  "desktop-b40sn3o"            │
│ ubuntu@hermes-linux           │ ─────► │ Tailscale 100.105.102.126 · user irfan   │
│ key: ~/.ssh/pc_irfan_key      │  :22   │                                          │
│                               │        │  Discord stable  app-1.0.9258  :9223     │
│ orchestration · API calls     │  CDP   │  Discord PTB     app-1.0.1220  :9224     │
│ token refresh · reporting     │ ─────► │  Discord Canary  app-1.0.1177  :9225     │
│                               │ :9223- │                                          │
│                               │ :9225  │  sooka watch windows (Brave / Chrome /   │
│                               │        │  Chrome Beta) — the capture sources      │
└───────────────────────────────┘        └──────────────────────────────────────────┘
                                                        │
                                                        │ HTTPS · Discord API v9
                                                        ▼
                                        ┌──────────────────────────────────────────┐
                                        │ POST/PATCH/GET/DELETE /stage-instances   │
                                        │ (start · edit topic · query · end)       │
                                        └──────────────────────────────────────────┘
```

Two independent control channels are used, deliberately:

- **CDP (loopback, per client)** — inspect DOM state, find element rectangles, and
  dispatch *trusted* mouse input into the renderer.
- **Discord REST API v9** — perform the stage-instance operations (start / edit /
  end) that would otherwise require clicking Discord's modal UI. This path is what
  removed the single largest blocker in the project.

### 1.2 Stream mapping

The mapping is fixed by **channel ID**. Names are never used as keys — a separate
`voice_renamer` process rewrites channel names to the live match titles every few
seconds.

| Stream | Discord client | CDP | Stage channel ID | sooka watch window | Topic |
|---|---|---|---|---|---|
| 1 | Discord stable | 9223 | `1477692113738137600` | Brave | `1)` |
| 2 | Discord Canary | 9225 | `1481358977584599283` | Chrome Beta | `2)` |
| 3 | Discord PTB | 9224 | `1481359453759475876` | Google Chrome | `3)` |

Guild: `1251553669644816518` (SportManiaMY).

### 1.3 Per-stream flow

1. **Launch** the client with `--remote-debugging-port=<port>` and a
   `discord://-/channels/<guild>/<channel>` deep link, so it opens on the stage view.
2. **Start the stage instance** with `POST /api/v9/stage-instances` (topic `N)`).
   No UI modal is ever shown or clicked.
3. **Join the stage** in the client (voice connection).
4. **Share Screen** — open the share picker via CDP and select the sooka browser
   window tile.
5. **Go Live** — confirm; the stage shows the live speaker with a screen thumbnail.

All five steps are automated and verified end-to-end on all three clients
(see [`ISSUES.md`](ISSUES.md) F8 for the fixes that got steps 4-5 working).

---

## 2. Repository layout

```
sooka-stage/
├── README.md                 this document
├── HANDOVER.md               handover brief for a new engineer/agent
├── HERMES_GUIDE.md           operator guide + failure catalogue
├── HERMES_PLAN.md            ordered plan with acceptance criteria
├── ISSUES.md                 issue register (fixed / open)
├── SOOKASTAGE_PROGRESS.md    chronological log
├── sookastage_prod.py        main runner: config, state machine, CLI
├── sooka_cdp.py              CDP transport + verified-click engine + Win helpers
├── sooka_diag.py             preflight triage (read-only)
├── api_stage.py              stage-instance REST wrapper
├── cdp_lib.py                standalone CDP probe helpers
├── probe_panel.py            accessibility/DOM panel probe
├── cdp_status.py             quick port/target status for 9223/9224/9225
├── port_check.py             target listing helper
├── win_enum.ps1              enumerate visible top-level windows (diagnostics)
├── main40.py                 DEPRECATED — hardcoded pixel coordinates, kept as record
├── scripts/                  PC-side helpers (token refresh, hidden screenshot, schtask,
│                              watchdog.py -- Phase 3.1 self-heal, run via SookaStageWatchdog)
└── tests/                    regression tests — run anywhere, Discord not required
```

### 2.1 Quick reference

```powershell
python -m unittest discover -s tests           # regression tests (no Discord needed)
python sooka_diag.py                           # triage all three clients, read-only
python sooka_diag.py --stream 1 --calibrate --buttons
python sookastage_prod.py --stream 1 --diagnose  # state only, clicks nothing
python sookastage_prod.py --stream 1 --json
python sookastage_prod.py --all --json
```

Exit code `0` means every requested stream reached the streaming state.

---

## 3. Environments

### 3.1 Windows PC (execution host)

| Item | Value |
|---|---|
| Host | `desktop-b40sn3o` · Tailscale `100.105.102.126` · user `irfan` |
| SSH key (from VPS) | `~/.ssh/pc_irfan_key` |
| Working directory | `C:\Users\irfan\SookaStage` |
| Python | 3.12 · `C:\Users\irfan\AppData\Local\Programs\Python\Python312\python.exe` |
| Discord stable | `%LOCALAPPDATA%\Discord\app-1.0.9258\Discord.exe` |
| Discord PTB | `%LOCALAPPDATA%\DiscordPTB\app-1.0.1220\DiscordPTB.exe` |
| Discord Canary | `%LOCALAPPDATA%\DiscordCanary\app-1.0.1177\DiscordCanary.exe` |
| Optional subagent | OpenCode CLI 1.18.31 (Node 24) · model `omen/omen-alpha` |

### 3.2 Launch command (flags must be present at launch)

`--remote-debugging-port` is only honoured at process start. Adding it to an
already-running instance does nothing.

```powershell
Start-Process 'C:\Users\irfan\AppData\Local\Discord\app-1.0.9258\Discord.exe' -ArgumentList `
  '--force-renderer-accessibility','--remote-debugging-port=9223', `
  'discord://-/channels/1251553669644816518/1477692113738137600'
```

The same pattern applies to PTB (`9224`, channel `1481359453759475876`) and Canary
(`9225`, channel `1481358977584599283`).

### 3.3 Secrets

| Secret | Location | Handling |
|---|---|---|
| Discord **user token** | `C:\Users\irfan\SookaStage\.user_token.json` | PC-local, never committed, never echoed, never screenshotted. Refresh per session (see §4.2). |
| OpenCode API key | PC user environment (`OPENCODE_API_KEY`) | Set with `setx`; never printed. |

Rotate the Discord user token immediately if it ever appears in a terminal capture,
a chat message, or a screenshot.

---

## 4. Operating procedure

### 4.1 Preflight

```bash
# from the VPS
tailscale status | grep desktop-b40sn3o        # expect: active; relay
ssh -i ~/.ssh/pc_irfan_key irfan@100.105.102.126 "echo ok"
```

Then, on the PC:

```powershell
python C:\Users\irfan\SookaStage\cdp_status.py    # expect 9223/9224/9225 UP with a channels/ target
```

If a port is `DOWN`, that client is not running with the flag — relaunch it (§3.2).

### 4.2 Refreshing the Discord user token

`localStorage.token` is **stale** on these builds and returns HTTP 401. Module
scanning for `getToken` returns nothing usable. Only the **live request header** is
authoritative:

1. Open one persistent CDP WebSocket to a page target on the desired client.
2. `Network.enable`.
3. `Page.navigate` to the same channel URL (forces the app to issue authorised
   requests).
4. Read the `Authorization` header from any outgoing request.
5. Write it to `.user_token.json` as `{"discord_user_token": "..."}`.
6. Verify: `GET /api/v9/users/@me` → `200`.

`scripts/get_token_store.py` and `scripts/sniff_token.py` implement this.

### 4.3 Stage instance operations

```python
import json, requests

tok = json.load(open(r"C:\Users\irfan\SookaStage\.user_token.json"))["discord_user_token"]
H = {"Authorization": tok, "User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
CH = "1477692113738137600"   # Stream 1; 1481358977584599283 = 2; 1481359453759475876 = 3

requests.post("https://discord.com/api/v9/stage-instances", headers=H, json={
    "channel_id": CH, "topic": "1)", "privacy_level": 2, "send_start_notification": False,
})                                            # 200 = started

requests.get(f"https://discord.com/api/v9/stage-instances/{CH}", headers=H)   # 200 live / 404 not started

requests.patch(f"https://discord.com/api/v9/stage-instances/{CH}",
               headers=H, json={"topic": "1) New topic"})

requests.delete(f"https://discord.com/api/v9/stage-instances/{CH}", headers=H)  # end
```

### 4.4 CDP interaction pattern

```python
import json, urllib.request, websocket

t = json.load(urllib.request.urlopen("http://127.0.0.1:9224/json/list"))
tgt = [x for x in t if x.get("type") == "page"][0]
ws = websocket.create_connection(tgt["webSocketDebuggerUrl"], timeout=15, suppress_origin=True)

def cmd(i, method, params):
    ws.send(json.dumps({"id": i, "method": method, "params": params}))
    while True:
        r = json.loads(ws.recv())
        if r.get("id") == i:
            return r

ws.close()      # always close; one WebSocket per script
```

Transport gotchas:

- **PTB rejects the handshake with HTTP 403** when an `Origin` header is present and
  the client was not started with `--remote-allow-origins`. Pass
  `suppress_origin=True`.
- **One WebSocket at a time per client.** Interleaved short-lived sessions leave the
  DevTools socket wedged (worst on stable `app-1.0.9258`).

### 4.5 Screenshots / screen-state capture on the PC

Screen capture only works from a process inside the **interactive desktop session**.
A plain SSH session fails with *"The handle is invalid"*. Use a single-shot
scheduled task with the `/it` flag and a windowless interpreter:

```powershell
$tr = 'C:\Users\irfan\AppData\Local\Programs\Python\Python312\pythonw.exe C:\Users\irfan\SookaStage\scripts\final_shot.py'
schtasks /create /tn SookLastShot /tr $tr /sc once /st 22:30 /it /f
schtasks /run /tn SookLastShot
schtasks /delete /tn SookLastShot /f      # always clean up
```

See `scripts/README.md`. Known failure results: `1` (script/env problem) and
`-2147024894` (`0x80070002` — executable not on the scheduler's PATH; use an
absolute path).

---

## 5. Hard rules

1. **Channel identity is the ID.** `voice_renamer` mutates names continuously.
2. **The stage must be STARTED before the Share button exists.** Never take the
   "Continue without starting" branch — it guarantees the stage never starts.
3. **Only trusted input triggers capture.** `Input.dispatchMouseEvent` works;
   `element.click()` / synthetic `MouseEvent` do not (no user activation).
4. **`Ctrl+Shift+D` toggles deafen.** A "Server Deafened" modal blocks the share
   flow until undeafened.
5. **One `/json` call, one persistent WebSocket per run.** See §4.4.
6. **Never `taskkill /IM` by image name.** Kill by PID. A global
   `taskkill /F /IM python.exe` has already killed a live helper process.
7. **No console windows on the owner's desktop.** Use `pythonw.exe`,
   `-WindowStyle Hidden`, and scheduled tasks with `/it`. A stray console window
   takes foreground and makes the whole desktop appear unclickable.
8. **Delete one-shot scheduled tasks after use.** The machine once accumulated ~73
   `Sook*` tasks; several had at-logon triggers that spawned visible windows on every
   reboot (now disabled — see [`ISSUES.md`](ISSUES.md)).
9. **Never commit or print secrets.**

---

## 6. Root-cause catalogue

Detailed write-ups live in [`ISSUES.md`](ISSUES.md). Summary:

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | "Start the Stage" modal never accepted a programmatic click | Windows foreground lock (scheduled-task context cannot take foreground) + React controlled input re-render | Skip the UI: `POST /stage-instances` |
| 2 | Stable client DevTools wedged after a few sessions | Electron serialises the `/json` endpoint; half-open WS sessions | One `/json` call, one persistent WS, explicit close |
| 3 | Canary self-exits 2–7 min after launch; splash stuck on *checking-for-updates* | Installer run with `/s` (lowercase) unpacked only the bootstrap → `modules\` missing → updater demanded a full reinstall of the running version → `InconsistentInstallerState` → exit | Clear `installer.db` + `packages\`, reinstall with `/S` (uppercase) |
| 4 | Stored token returns 401 | `localStorage.token` is stale; module `getToken` yields nothing on these builds | Capture the `Authorization` header from live traffic via CDP `Network` |
| 5 | Python console window appears on every reboot | `SookaRenamer` (and `SookaBootFix`) scheduled task with an *at logon* trigger running `python.exe` | Tasks disabled; re-create with `pythonw.exe` if needed |
| 6 | Desktop shows a hung blank console; clicks do nothing | Leftover console window from an automation run holding foreground | Windowless execution (§4.5 rules) + kill by PID |

---

## 7. Change log

| Date (UTC+8) | Change |
|---|---|
| 2026-09-16 | CDP research: bot API cannot screenshare, self-bot rejected (ToS), UIA limited to PTB → pivot to CDP on 9223/9224/9225. First successful end-to-end share on the stable client. |
| 2026-09-17 | Stage start moved to REST (modal bypass proven on all three channels). Token extraction via CDP network sniff. Canary installer/updater corruption diagnosed and fixed. OpenCode CLI installed on the PC (model `omen/omen-alpha`). At-logon console tasks disabled. Full documentation set written for handover. |
| 2026-09-18 | Share-picker flow fixed and verified end-to-end on all three clients (speaker-render race, `picker_open` detection, Chrome-Beta-vs-Chrome tile misclassification, off-screen tile clicks, re-run idempotency -- see `ISSUES.md` F8). Verified identical from a hidden scheduled-task context. Self-heal verified by manually dropping a stream and re-running `--all`. Registered `SookaStageWatchdog` (every 5 min) for Phase 3.1. Deleted 67 stale one-shot scheduled tasks, kept 6 (F9). |
