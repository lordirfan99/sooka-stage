# CLAUDE.md — start here

You are picking up **SookaStage**, an automation that mirrors three live sooka.live
match streams into three Discord Stage channels on this Windows PC, driven over SSH
from a Linux VPS.

## Read in this order

1. `HANDOVER.md` — current state: what is proven, what is broken, what is next.
2. `README.md` — architecture, environments, operating procedure, hard rules.
3. `HERMES_GUIDE.md` — failure catalogue and the rules that explain "the click did
   nothing" situations.
4. `HERMES_PLAN.md` — the ordered phase plan with acceptance criteria. **Phase 0 is the
   next actionable work.**
5. `ISSUES.md` — the issue register (7 fixed, 5 open).

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
- The remaining work is the **screenshare picker** flow inside the client
  (share picker → select the sooka browser tile → Go Live), driven over CDP with
  *trusted* input (`Input.dispatchMouseEvent`).

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

Canary `app-1.0.1177` exits silently 2–7 minutes after launch on this machine (no crash
dump, no WER event; last activity is the voice/RTC latency test). The install itself is
now healthy — reinstall with `/S` fixed an updater-state corruption. Options are: wait
for the next Canary build, host Stream 2 elsewhere, or wrap Canary in a restart
watchdog. Do not re-diagnose the installer; that part is done (see `ISSUES.md` F3/O1).
