# SookaStream/SookaStage — FULL HANDOVER (2026-09-19, post-consolidation)

**Audience:** incoming engineer or AI agent (Claude) taking over on the owner's
Windows PC (`desktop-b40sn3o`, Tailscale `100.105.102.126`, user `irfan`).
**Prepared by:** SportMania (Hermes agent on the Linux VPS), 2026-09-19.
**Supersedes:** HANDOVER.md's 2026-09-18 state (the system changed a lot on 09-19).

---

## 1. The one-paragraph model (2026-09-19 reality)

Three live sooka.live match streams are screen-shared into three Discord Stage
channels (one Brave, one Chrome, one Chrome Beta watch window; stable/Canary/PTB
Discord clients). All control now happens on the PC through **ONE
consolidated CLI** (`C:\Users\irfan\sooka_agent.py`, 9 subcommands) and **ONE
GUI** (SookaStream Manager v3.3, which now includes a KILLSWITCH panel).
Renaming uses the **SPORTMANIA BOT token** (not the Discord user token). The
renamer runs **on the PC** (not the VPS). The VPS only does remote-access,
hermes, and monitoring crons.

### Canonical artifacts (single sources of truth)

| Artifact | Path | Purpose |
|---|---|---|
| Consolidated CLI | `C:\Users\irfan\sooka_agent.py` | status / launch / stream N-all / watch / rename / dashboard / cleanup / check / install (+ --json) |
| Manager GUI v3.3 | `C:\Users\irfan\SookaStreamManager\SookaStreamManager.exe` (+ `sooka_manager_app.py`) | all-in-one dashboard + KILLSWITCH (START/PAUSE/KILL ALL + autostart checkbox) |
| Dashboard (separate, on purpose) | `C:\Users\irfan\Desktop\Restored-Desktop\SookaStream-Windows-x64-v8.6\SookaStream-Windows-x64-v8.6\sooka_server.py` + `run_headless.py` | port 8080 EPG web dashboard, ngrok-tunnelled by `ngrok.exe` at `C:\Users\irfan\AppData\Local\ngrok\ngrok.exe` |
| EPG generator (v1 look) | same dir, `sooka_epg_new.py` | renders the classic "Sooka 3-Stream EPG" page, auto-refreshed by handle_dashboard (TTL 120s) |
| Bot renamer (PC) | `C:\Users\irfan\SookaStage\bot_renamer_pc.py` | stage topic = "Stream N — match", channel name locked = "Stage 1/2/3" |
| Bot token | `C:\Users\irfan\SookaStage\.bot_token` | SPORTMANIA BOT, **never print/commit** |
| Stage flow engine | `C:\Users\irfan\Desktop\sooka-stage\sookastage_prod.py` | CDP flow: channel→join→undeafen→start_stage→speaker→picker→tile→go_live |
| Client launcher | `C:\Users\irfan\Desktop\sooka-stage\scripts\schtask_launch_client.ps1` | handles Discord auto-update path changes + flag-stripping relaunch |
| VPS-side copy | `/home/ubuntu/sooka-stage` (git) & `/home/ubuntu/sooka-manager` (git) | repos: github.com/lordirfan99/sooka-stage & sooka-manager |

### Key IDs (immutable)

- guild `1251553669644816518`
- Stage 1 = `1477692113738137600`, Stage 2 = `1481358977584599283`, Stage 3 = `1481359453759475876`
- CDP ports: stable `9223` → ch1, Canary `9225` → ch2, PTB `9224` → ch3
- **Address channels by ID, never by name.** Names are now LOCKED to
  "Stage 1/2/3" (owner decision, 09-19 — match info goes in the topIC instead).

---

## 2. Everything that changed on 2026-09-19 (the big day)

Chronological. Each item is verified — evidence noted.

1. **v3.2 Manager** (PR #8–#12 merged): SookaStage status panel, red-cross
   `proc_alive` fix (#10), ACTIVITY pane (#11), update freeze + CHECK SYSTEM (#12).
   Title bump commit `7270bfe`.
2. **Dynamic EPG auto-include** (fix for "Astro Premier League 3/4/5 missing"):
   `sooka_server.py` fallback rule: `ch_name = SPORTS_CHANNELS.get(cid) or
   (ch_title if ch_title.startswith('Astro ') else '')`. Nothing hardcoded; new
   sooka channels appear automatically.
3. **Bot topics+rename via SPORTMANIA BOT** (replaces per-user token code):
   `GET/PATCH /stage-instances`, `PATCH /channels/<id>` all proven 200. Requires
   `User-Agent` header — Discord returns **error 1010** (403) without a UA.
4. **Rate-limit hardening in renamer**: 2.5 s pacing between calls, 3-attempt
   retry with backoff on 429, "(L)" dedupe. Commit `eaefc02`.
5. **Manual channel picker restored on the dashboard**: the old
   `sooka_launcher.upgrade_dashboard()` logic was ported directly into
   `sooka_server.py` (`_manual_upgrade_dashboard`): the /dashboard render
   injects a manual-panel (3 dropdowns + Apply), POST /manual-picks with an
   HMAC token, and handle_task override so a manual pick actually redirects a
   stream. Verified end-to-end through the ngrok public URL.
6. **THEN owner demanded the CLASSIC v1 dashboard back**: `/dashboard` now
   serves `sooka-dashboard.html` regenerated live by `sooka_epg_new.py`
   (its stale hardcoded `API_KEY = "dfcafc649f46"` was replaced with
   `from sooka_server import API_KEY`). Verified: v1 title, manual panel,
   2207 events / 25 live. **sooka_server.py was rebuilt from
   `sooka_server.py.pre-manualpicks.bak`** and re-patched in this order:
   auto-include → manual-picks payload → v1 runtime block (all inserted
   BEFORE `def main():`). Learn this order — a bad order killed the server
   twice (an accidental `sys.exit(0)` guard, then a cut `def main()`).
7. **Renamer localized to PC** (owner: "I want to localize all script to pc
   only"): `bot_renamer_pc.py` reads `http://127.0.0.1:8080` locally, token
   from `.bot_token` file, bot-author header REQUIRED (error 1010 otherwise).
   Registered as `SookaRenamer` schtask (onlogon, /it, pythonw).
   **VPS `sooka-renamer.service` + `renamer-webhook.service` are disabled
   permanently.** Do not re-enable them.
8. **Names locked**: topic carries the match ("Stream N — (L) title"),
   channel name is always "Stage N". Owner explicitly set Stage 1/2/3.
9. **Consolidation (owner choice 2)**: OpenCode on the PC built
   `sooka_agent.py` (537 lines, 9 subcommands, stdlib only) and later the
   Manager v3.3 merge. OpenCode usage notes:
   - the PC key hit "Go usage limit exceeded"; owner said to reuse the
     hermes `OPENCODE_GO_API_KEY` — set as User env `OPENCODE_API_KEY`
     (config `apiKey: "{env:OPENCODE_API_KEY}"`).
   - opencode MUST run with workdir `C:\Users\irfan` for files outside
     `SookaStage` (else "auto-rejecting external_directory").
   - prompt goes BEFORE `--file`; `< nul` instead of `echo. |`.
   - long runs must go through `schtasks /it`, and opencode dies when the
     SSH session that spawned it exits.
10. **Manager v3.3** (PR #14, commit `7169fe1`, build SHA256
    `21A23468…`, backup `SookaStreamManager.v32.bak`): the sooka_gui
    killswitch is now a KILLSWITCH section inside the Manager —
    START (= `sooka_agent.py launch` + `stream all`), PAUSE (= rename stop +
    `schtasks /change /tn SookaStageWatchdog /disable`), KILL ALL (= cleanup,
    confirm dialog), Autostart-on-login checkbox (deletes/re-registers
    `SookaStageWatchdog` + `SookaRenamer` tasks via
    `python sooka_agent.py install`, state persisted in
    `killswitch_autostart`).
11. **Dashboard + ngrok are CLOSED tonight** (owner manual mode): dashboard
    server and `ngrok.exe` were killed on purpose. Bring them back with
    `python sooka_agent.py dashboard start`.
12. **Popup-cmd complaint fixed**: the blank PowerShell/cmd popups were MY
    one-shot helper scripts run via `schtasks /it` WITHOUT
    `-WindowStyle Hidden`. All killed (pids 9736, 7588, …). Rule below.

---

## 3. Non-negotiable rules (updated for 2026-09-19)

These extend the originals in CLAUDE.md/README.md.

1. **Every schtask helper script must carry `-WindowStyle Hidden`.** A
   `schtasks /it` one-shot without it opens a blank fullscreen console on
   the owner's desktop (happened 2026-09-19 ~22:30–23:50). Delete the task
   right after use.
2. **All `subprocess` calls in GUI code need `creationflags=CREATE_NO_WINDOW`
   (0x08000000).** Manager v3.3 has this on all 12 sites — keep it that way.
3. **Never spawn PowerShell/cmd consoles from an SSH session without
   hiding them.** `Start-Process … -WindowStyle Hidden` only.
4. **Discord REST needs a bot UA** with the SPORTMANIA BOT token —
   `User-Agent: …DiscordBot…`, else error 1010 (403).
5. **sooka_server.py re-patch order** matters (auto-include →
   manual-picks → v1 runtime, all before `def main():`). Restore from
   `.pre-manualpicks.bak` if lost.
6. VPS-side sooka services (`sooka-renamer`, `renamer-webhook`) are
   retired. Do not re-enable them; everything runs on the PC now.
7. `sooka_agent.py` subcommand list is the control plane. Its source of
   truth pairing: renamer→`bot_renamer_pc.py`, streams→
   `Desktop\sooka-stage\sookastage_prod.py` (imported), dashboard→
   Restored-Desktop `run_headless.py`.

---

## 4. Current live state at handover (2026-09-19 ~23:59)

| Component | State |
|---|---|
| Manager v3.3 | built, SHA256 `21A23468…`, 2 pids running (close one if duplicated) |
| Dashboard + ngrok | STOPPED on purpose (owner's manual night) |
| Renamer | task `SookaRenamer` DISABLED (owner manual night); re-enable = `schtasks /change /tn SookaRenamer /enable` then `/run` |
| Watchdog task `SookaStageWatchdog` | DISABLED |
| VPS services | `sooka-renamer` + `renamer-webhook` stopped AND disabled |
| Browsers + 3 Discord clients | running (owner manual mode) |
| Discord stages | names "Stage 1/2/3", topics carry match titles |
| Repo sooka-manager | main @ `7169fe1` (v3.3), all PRs #8–#14 merged |
| Repo sooka-stage | main @ `eaefc02` |

---

## 5. Verification you can run immediately (no side effects)

```powershell
python C:\Users\irfan\sooka_agent.py status     # true machine state
python C:\Users\irfan\sooka_agent.py check      # 3 core scripts PASS, token check
python C:\Users\irfan\sooka_agent.py --help     # 9 subcommands
python -c "import ast; ast.parse(open(r'C:\Users\irfan\SookaStreamManager\sooka_manager_app.py').read()); print('OK')"
```

---

## 6. Known open issues & next steps

1. **Archive the 115 loose files** in `C:\Users\irfan\SookaStage` (65 py,
   21 ps1, 14 bat — mostly one-off probes: shot_9223, check2_9225, modscan,
   netsniff, push, login, launch_beta1–4, run_*.bat). Move to `_archive/`
   after owner confirms v3.3 works for him. Do NOT delete anything.
2. **opencode brief** for any future consolidation is at
   `C:\Users\irfan\SookaStage\opencode_task.md` (phase 3 of the
   consolidation plan).
3. **Dashboard "v2 look"** was reverted on purpose; if asked again, the v1
   generator is `sooka_epg_new.py` (keep the API_KEY import fix!).
4. **Watchdog** re-enable: `schedtasks /change /tn SookaStageWatchdog /enable`.
5. **Chrome Beta tile tagging** still relies on `watch_windows.py` (see
   CLAUDE.md) — any stream restart re-tags it.
6. **PTB/Canary clients can wedge** — recovery is kill-by-PID + relaunch via
   `scripts/schtask_launch_client.ps1` (never re-hardcode app paths).

---

## 7. Where things live (quick paths)

| Thing | Path |
|---|---|
| sooka_agent.py | `C:\Users\irfan\sooka_agent.py` |
| sooka_gui killswitch (standalone) | `C:\Users\irfan\sooka_gui.py` |
| Manager source (PC build copy) | `C:\Users\irfan\SookaStreamManager\sooka_manager_app.py` |
| Manager v3.3 exe | `C:\Users\irfan\SookaStreamManager\SookaStreamManager.exe` |
| Manager repo (VPS git clone) | `/home/ubuntu/sooka-manager` |
| sooka-stage repo (VPS git clone) | `/home/ubuntu/sooka-stage` |
| Dashboard server dir | `C:\Users\irfan\Desktop\Restored-Desktop\SookaStream-Windows-x64-v8.6\SookaStream-Windows-x64-v8.6\` |
| Renamer script | `C:\Users\irfan\SookaStage\bot_renamer_pc.py` (+ `.bot_token`) |
| Renamer log | `C:\Users\irfan\bot_renamer_pc.log` |
| Watchdog script | `C:\Users\irfan\Desktop\sooka-stage\scripts\watchdog.py` |
| Client launcher | `C:\Users\irfan\Desktop\sooka-stage\scripts\schtask_launch_client.ps1` |
| opencode binary | `C:\Users\irfan\AppData\Roaming\npm\node_modules\opencode-ai\bin\opencode.exe` (model: omen/omen-alpha, key via User env) |

---

## 8. How to handover ops mid-incident

1. Run `python C:\Users\irfan\sooka_agent.py status` and fix only what the
   status section marks.
2. If GUI shows FAIL for client processes, first open task manager and check
   CDP ports: `netstat -ano | findstr "9223 9224 9225"`.
3. If streams die: `python C:\Users\irfan\sooka_agent.py stream all` — the
   flow re-enters cleanly (PID lock, timeout 180s).
4. If Discord auto-updated again: use schtask_launch_client.ps1 (resolves
   app dirs+strips flags), do not hardcode `app-1.0.xxxx` paths.
5. If the dashboard json shows wrong matches: check EPG refresh +
   `python C:\Users\irfan\Desktop\Restored-Desktop\...\sooka_epg_new.py`
   error log (its API key now imports from sooka_server).
