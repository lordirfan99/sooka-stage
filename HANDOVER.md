# SookaStage — Handover Brief

**Audience:** an incoming engineer or AI agent (e.g. Claude) taking over this project.
**Date:** 2026-09-18 (UTC+8).
**Prepared by:** the operating agent on the Linux VPS (2026-09-17 baseline), updated by
Claude Code running directly on the Windows PC (2026-09-18: share-picker flow fixed and
verified live end-to-end, watchdog added).

Read [`README.md`](README.md) first for architecture and procedure, then this brief
for the current state and the immediate next actions.

---

## 1. What this project does

Three live **sooka.live** match streams are screen-shared into three Discord **Stage
channels** at the same time. Each stream has its own:

- Discord client (stable / Canary / PTB) with its own CDP debugging port;
- stage channel (fixed by channel ID);
- sooka watch window (Brave / Chrome Beta / Chrome).

The automation runs from a Linux VPS and drives the owner's Windows PC over
Tailscale SSH. All channel identity is by **ID**, because a `voice_renamer` process
rewrites channel names to the live match titles continuously.

```powershell
python sookastage_prod.py --all --json     # target: one command, three live streams
```

---

## 2. Current state (be precise about what is proven)

### 2.1 Proven end-to-end

| Capability | Evidence |
|---|---|
| Stage instance **start** via REST | `POST /api/v9/stage-instances` → `200` on all three channel IDs (`1477692113738137600`, `1481358977584599283`, `1481359453759475876`) with topics `1)`, `2)`, `3)`. The Discord UI modal is bypassed entirely. |
| Stage instance **query** | `GET /stage-instances/<channel_id>` → `200` live / `404` not started; used to confirm ch3 was live and ch1/ch2 were not. |
| **User token capture** | CDP `Network.enable` + `Page.navigate`, reading the `Authorization` header from live traffic → `GET /users/@me` → `200`. `localStorage.token` was proven stale (401); webpack `getToken` scanning yields nothing on these builds. |
| **CDP transport** | Persistent WebSocket to a `channels/…` page target on 9223 / 9224 / 9225; `Runtime.evaluate` and `Page.captureScreenshot` confirmed working. Learned: PTB needs `suppress_origin=True`; one WS per script. |
| **Canary install repair** | Root cause found in `DiscordCanary_updater_rCURRENT.log`; reinstall with `/S` restored `modules\` (payload ≈ 442 MB) and the updater now reports *Already up to date*. |
| **PC subagent** | OpenCode CLI 1.18.31 installed (Node 24), default model `omen/omen-alpha` via a custom provider block that injects the `x-opencode-session` header. Smoke test returned `OMEN_PC_OK`. |
| **Hidden-execution pattern** | Screenshots and windowless runs on the PC via `schtasks /it` + `pythonw.exe`. |

### 2.2 Verified live end-to-end (2026-09-18)

- `sookastage_prod.py` state machine: channel → start_stage → join → undeafen →
  speaker → share picker → tile selection → go live. All three clients (stable/9223,
  Canary/9225, PTB/9224) reached `streaming: true`, confirmed by CDP screenshot
  (LIVE badge, "Sharing their screen"). Re-running `--all` against three already-live
  streams is a clean no-op (every step `already=True`, exit `0`, under a second).
  Verified identical from a hidden scheduled-task context. Self-heal verified: manually
  stopped one stream's share, re-ran `--all`, only that stream was re-driven.
  Five real bugs found and fixed doing this -- see `ISSUES.md` F8. A recurring
  `SookaStageWatchdog` task (every 5 min) now runs this automatically.

### 2.3 Known open problems

| # | Problem | Impact | Suggested next step |
|---|---|---|---|
| A | **Canary (`app-1.0.1177`) exits silently 2–7 minutes after launch.** Reproduced 5×: with flags, bare, `--disable-gpu`. No Crashpad report, no WER event, no `EventID 1000`. Last activity before exit is always the voice/RTC region-latency test; the only historical hard crash on this box was Canary `1.0.1165` faulting in `discord_media.node` (`0xc0000409`). 2026-09-18: ran 70+ min without recurring, but that is not proof it's gone -- still open. | Stream 2 has no reliable host client guarantee | Wait for the next Canary build, host Stream 2 on a different client, or wrap Canary's *process* in a restart watchdog (the new `SookaStageWatchdog` re-runs the *stream flow*, but does not relaunch Canary if it exits). |
| C | **Interaction with a headless SSH context** | Screen APIs fail from SSH (`The handle is invalid`); opencode run from SSH sees a black screen | Always execute screen-touching work through `schtasks /it` (interactive session) |
| D | **Real match content not wired up in this session's test** | The three browser tabs used to verify the share flow (2026-09-18) point at `sooka.live`, which does not resolve -- the real domain is `sooka.my` (`SookaStream-Windows-x64-v8.6\START-HERE.txt`). Opening real, signed-in, Tampermonkey-tagged sooka.my tabs is the separate SookaStream Manager's job, out of scope for this repo. | The mechanics (picker, tile match, go-live, idempotency) are proven; the content shown will be whatever's in those tabs |

---

## 3. Environment quick facts

| Item | Value |
|---|---|
| PC | `desktop-b40sn3o`, Tailscale `100.105.102.126`, user `irfan` |
| SSH from VPS | `ssh -i ~/.ssh/pc_irfan_key irfan@100.105.102.126` |
| Working dir on PC | `C:\Users\irfan\SookaStage` (the cloned repo lives at `C:\Users\irfan\Desktop\sooka-stage`) |
| Python on PC | 3.12 · `…\Programs\Python\Python312\python.exe` (use `pythonw.exe` for anything visible) |
| CDP ports | 9223 stable · 9224 PTB · 9225 Canary |
| Channel IDs | ch1 `1477692113738137600` · ch2 `1481358977584599283` · ch3 `1481359453759475876` |
| Guild ID | `1251553669644816518` |
| Token file | `C:\Users\irfan\SookaStage\.user_token.json` (never commit; refresh via CDP sniff) |
| Subagent (optional) | `opencode run` on the PC, model `omen/omen-alpha`, requires piped stdin: `cmd /c "echo. | opencode run \"<prompt>\" > oc_out.txt 2>&1"` |

---

## 4. First 30 minutes for the incoming engineer

1. **Read** `README.md`, then `HERMES_GUIDE.md` (failure catalogue), then this file.
2. **Reach the PC.** If Tailscale reports the PC offline, ask the owner to wake it —
   do not burn cycles retrying.
3. **Run the tests** (no Discord needed):
   ```bash
   python -m unittest discover -s tests
   ```
4. **Read-only triage** on the PC:
   ```powershell
   python C:\Users\irfan\SookaStage\cdp_status.py
   python sooka_diag.py
   ```
   Expect `9223/9224/9225 UP` with a `channels/…` page target each, and a per-client
   verdict naming any active blocker.
5. **Refresh the token** if `/users/@me` is not `200` (procedure in README §4.2).
6. **Start all three stages** via the REST calls in README §4.3 and confirm `200`.
7. **Only then** attempt the share flow, following `HERMES_PLAN.md` Phase 0 → 1.

---

## 5. Definition of done (project level)

1. `python sookastage_prod.py --all` exits `0` when run from a **scheduled task**
   (not an interactive shell) — this is where the foreground lock used to bite.
2. Three channels live simultaneously, each showing its **own** browser window.
3. A stream that drops recovers within one watchdog interval.
4. Any failure names its failing **step** and **reason** in `run.json`, so nobody has
   to reproduce it interactively.

---

## 6. Working agreements (do not break these)

1. Channel identity by **ID** — names mutate live.
2. Kill processes **by PID**, never `taskkill /IM`.
3. No console windows on the owner's desktop — `pythonw.exe`, `-WindowStyle Hidden`,
   `schtasks /it`, and delete one-shot tasks after use.
4. Never print, log, or screenshot the Discord user token or any API key.
5. One `/json` call and one persistent CDP WebSocket per run.
6. Version-control discipline: small commits, clear messages, no force-push to `main`.

---

## 7. Where to ask / what to record

- Behavioural questions → run `sooka_diag.py --buttons` on a client that is **already
  in a started stage** (ch2/ch3 have been live before) and compare real labels against
  `SELECTORS` in `sookastage_prod.py`.
- Every investigation should end with a line added to `ISSUES.md` or
  `SOOKASTAGE_PROGRESS.md` — timestamps, exact commands, exact outputs. The project's
  main historical cost has been re-learning the same root causes.
