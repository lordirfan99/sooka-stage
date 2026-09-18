# CLAUDE.md — start here

You are picking up **SookaStage**, an automation that mirrors three live sooka.live
match streams into three Discord Stage channels on this Windows PC, driven over SSH
from a Linux VPS.

## Read in this order

1. `HANDOVER.md` — current state: what is proven, what is broken, what is next.
2. `README.md` — architecture, environments, operating procedure, hard rules.
3. `HERMES_GUIDE.md` — failure catalogue and the rules that explain "the click did
   nothing" situations.
4. `HERMES_PLAN.md` — the ordered phase plan with acceptance criteria. **Phases 0-3.1 are
   done as of 2026-09-18** (all three streams live end-to-end, verified self-healing,
   watchdog registered); Phase 3.2+ (Manager GUI integration) is next.
5. `ISSUES.md` — the issue register (9 fixed, 3 open).

## The 60-second model

- Three Discord clients, each launched with `--remote-debugging-port`:
  stable `9223` → Stream 1 (ch1), PTB `9224` → Stream 3 (ch3), Canary `9225` → Stream 2 (ch2).
- Stage channels are addressed **by ID only** (a renamer process mutates names live):
  ch1 `1477692113738137600`, ch2 `1481358977584599283`, ch3 `1481359453759475876`,
  guild `1251553669644816518`.
- **Starting the stage is done over the REST API, never by clicking the modal:**
  `POST https://discord.com/api/v9/stage-instances` with
  `{channel_id, topic:"N)", privacy_level:2, send_start_notification:false}`, authorized
  with the user token at `.user_token.json`.
- The **screenshare picker** flow inside the client (share picker → select the sooka
  browser tile → Go Live), driven over CDP with *trusted* input
  (`Input.dispatchMouseEvent`), is verified working end-to-end on all three clients as
  of 2026-09-18 (see `ISSUES.md` F8). A `SookaStageWatchdog` scheduled task re-runs
  `--all` every 5 minutes so a dropped stream self-heals.
- Chrome Beta's own OS window title never says "Beta" on this machine -- only the page
  title (normally set by Tampermonkey's "Set Browser Identity", which is **not
  installed** here) distinguishes it from plain Chrome, and `browser_identity()` must
  check specific names before the generic `"google chrome"` fallback or it
  misclassifies every Chrome Beta tile as Chrome. In place of Tampermonkey,
  `scripts/watch_windows.py` tags that window's OS title via `SetWindowText`. The tag
  is a window title, so **any page reload reverts it** — `select_tile()` re-applies it
  immediately before reading tiles. Without a tag, Chrome and Chrome Beta produce
  byte-identical picker labels and `choose_tile()` correctly refuses to guess (a
  stalled stream, never a wrong one).

## Commands

```powershell
python -m unittest discover -s tests          # regression tests, no Discord needed
python sooka_diag.py                          # triage all three clients, read-only
python sooka_diag.py --stream 2 --buttons     # dump live button labels
python sooka_diag.py --stream 1 --calibrate   # verify click coordinate space
python sookastage_prod.py --stream 1 --diagnose
python sookastage_prod.py --all --json
python scripts\sniff_token.py 9224            # refresh the Discord user token
python scripts\verify_token.py                # check it
```

Exit code `0` means every requested stream reached the streaming state.

## Order of the flow (getting this wrong looks like a click bug)

`channel → join → undeafen → start_stage → speaker → picker → tile → go_live`.

Starting the stage **before** joining creates an instance with zero speakers, and
Discord auto-ends an empty stage within seconds: the POST returns 200, the instance is
404 a moment later, the client shows "Start Stage" again, the account sits in
**Audience**, and "Share Your Screen" never exists. Joining first also means the REST
call is made as a connected moderator, which is what puts the account on stage as a
speaker.

Only one run at a time: `sookastage_prod.main()` takes a PID lock
(`C:\Users\irfan\sookastage.lock`), so the 5-minute watchdog and a hand-run `--all`
cannot drive the same clients at once. The loser exits 0.

## One-click entry point

`Desktop\Start SookaStage.bat` → `scripts/start_sookastage.ps1`: brings up the Manager
dashboard (port 8080, the safe `.py` server — **never** the frozen
`SookaStream-v8.16.exe`, which carries a live Discord gateway bot), the channel
renamer, the three sooka.my watch windows, the three Discord clients, then `--all`.
`scripts/preflight.py` is the same checks in Python, used by the watchdog.

## Non-negotiable rules

1. **Never click the "Continue without starting" branch** — it guarantees the stage
   never starts and the Share button never appears.
2. **Trusted input only.** `element.click()` / synthetic `MouseEvent` do not grant user
   activation; use `Input.dispatchMouseEvent`.
3. **One `/json` call and one persistent CDP WebSocket per run**, closed explicitly.
   Pass `suppress_origin=True` — PTB rejects the handshake otherwise.
4. **No visible console windows on this desktop.** Use `pythonw.exe`,
   `-WindowStyle Hidden`, `schtasks /it`, and delete one-shot tasks after they run. A
   stray console steals foreground and makes the desktop look frozen.
5. **Kill processes by PID**, never `taskkill /IM`. A global
   `taskkill /F /IM python.exe` has already killed a live helper.
6. **Never print, log, or commit the Discord user token or any API key.**
7. `Ctrl+Shift+D` toggles deafen; the "Server Deafened" modal blocks the share flow.
8. `main40.py` is deprecated — hardcoded pixel coordinates, kept only as history.

## Known blocker you will hit

Clients **auto-update**, and both failure modes it causes are now handled by
`scripts/schtask_launch_client.ps1` — don't re-hardcode either:

- The `app-*` directory changes (Canary went 1.0.1177 → 1.0.1181 mid-session). The
  launcher resolves the newest `app-<version>` that still *contains* the exe at run
  time; an update leaves the old directory behind but strips its exe.
- After updating, Discord relaunches **itself** without `--remote-debugging-port`. It
  is single-instance, so launching again just hands off to that live instance and
  silently drops the flags. The launcher detects "process running but port not
  listening" and stops those PIDs first.

A client can also **wedge**: port listening, `/json` never answering, UI thread hung
(seen on PTB). `focus_client`'s `AttachThreadInput` blocks forever against a hung GUI
thread, which is why every stream now runs under `SOOKASTAGE_STREAM_TIMEOUT`
(default 180s). Recovery is to kill that client by PID and relaunch.
