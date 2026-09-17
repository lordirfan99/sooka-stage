# PC-side helper scripts

These run **on the Windows PC** (`C:\Users\irfan\SookaStage`), not on the VPS.
They exist because two classes of work are only possible inside the PC's session:

1. anything that reads the **Discord client** over CDP,
2. anything that touches the **desktop / screen**, which requires the interactive
   session (`schtasks /it`) and a windowless interpreter (`pythonw.exe`).

Copy them into `C:\Users\irfan\SookaStage\scripts\` (or run them from the cloned repo).

---

## `sniff_token.py`

Captures a **fresh Discord user token** from live client traffic and writes
`C:\Users\irfan\SookaStage\.user_token.json`.

Why not just read `localStorage.token`: that value is stale on current builds and
returns HTTP 401. Why not scan webpack for `getToken`: it yields nothing usable on
Discord 1.0.9258 / 1.0.1220 / 1.0.1177. The only authoritative source is the
`Authorization` header of a request the app itself makes.

```powershell
python scripts\sniff_token.py 9224        # PTB;  use 9223 stable, 9225 Canary
```

It attaches one persistent CDP WebSocket, calls `Network.enable`, navigates to the
same channel URL to force app traffic, and stores the first `Authorization` header it
sees. The token is **never printed**.

Verify afterwards:

```powershell
python scripts\verify_token.py            # GET /users/@me -> prints username or HTTP code
```

---

## `cdp_status.py`

Prints the page targets for 9223 / 9224 / 9225. Read-only; the fastest way to tell
whether a client is running with its debugging flag.

```powershell
python scripts\cdp_status.py
```

Expected healthy output:

```
9223 UP ['https://discord.com/channels/1251553669644816518/1477692113738…']
9224 UP ['https://ptb.discord.com/channels/1251553669644816518/1481359453…']
9225 UP ['https://canary.discord.com/channels/1251553669644816518/148135897…']
```

`DOWN` means that client was not started with `--remote-debugging-port`, or it has
exited (Canary `1.0.1177` is known to exit silently — see `ISSUES.md`).

---

## `final_shot.py`

Saves a full-screen PNG to `C:\Users\irfan\SookaStage\desktop_final.png`.
**Must** be invoked through a scheduled task with `/it` and with `pythonw.exe`:

```powershell
schtasks /create /tn SookLastShot /tr "C:\Users\irfan\AppData\Local\Programs\Python\Python312\pythonw.exe C:\Users\irfan\SookaStage\scripts\final_shot.py" /sc once /st 22:30 /it /f
schtasks /run /tn SookLastShot
schtasks /delete /tn SookLastShot /f
```

Notes:

- From a plain SSH session `CopyFromScreen` fails with *"The handle is invalid"*.
- Using `python.exe` (or `-WindowStyle`-less PowerShell, or a `> file` redirect)
  creates a **visible console window** on the owner's desktop that can steal
  foreground and make the desktop appear frozen. Always `pythonw.exe`, no redirect.
- Scheduler failure codes seen: `1` (script/env problem), `-2147024894`
  (`0x80070002` — use an absolute path to `pythonw.exe`).

---

## `schtask_launch_client.ps1`

Launches one Discord client with the automation flags and the correct deep link.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\schtask_launch_client.ps1 -Stream 1
```

Replace the executable path if Discord auto-updates to a new `app-*` directory —
`--remote-debugging-port` is only honoured at launch time.

---

## Rules

1. One CDP WebSocket per script, closed explicitly. The stable client's `/json`
   endpoint wedges under interleaved sessions.
2. Pass `suppress_origin=True` in `websocket.create_connection` — PTB rejects the
   handshake with 403 when an `Origin` header is present.
3. Never print a token, never write it anywhere except `.user_token.json`.
4. Delete one-shot scheduled tasks immediately after they run.
