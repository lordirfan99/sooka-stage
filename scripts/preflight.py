"""Shared "make sure everything that must be running actually is" checks.

Used by both the one-click launcher and the recurring watchdog so they can't
drift apart into two different ideas of "up". Two layers, run in order:

1. Watch-browser windows (Brave/Chrome/Chrome Beta showing sooka.my) --
   without these the share picker has nothing valid to pick.
2. Discord clients with their debug ports -- without these sookastage_prod.py
   can't connect at all (this is the gap that let the watchdog quietly stop
   healing streams 1 and 3 once their *processes*, not just their share
   state, disappeared).

Safe to call repeatedly: every check is "is it already up?" first.
"""
import os
import subprocess
import sys
import time

REPO = r"C:\Users\irfan\Desktop\sooka-stage"

WATCH_BROWSERS = [
    # Every entry needs a path_hint. Brave used to have None, which means "any
    # window whose title starts with the sooka page title" -- so with Chrome's
    # sooka window open it reported "Brave : already open" while no Brave
    # window existed at all, and the run then failed further along with
    # "no tile for 'brave'". A hint per browser is what makes the check real.
    {"name": "Brave", "exe": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
     "proc": "brave", "path_hint": "brave.exe"},
    {"name": "Chrome", "exe": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
     "proc": "chrome", "path_hint": "\\Chrome\\Application\\"},
    {"name": "Chrome Beta", "exe": r"C:\Program Files\Google\Chrome Beta\Application\chrome.exe",
     "proc": "chrome", "path_hint": "Chrome Beta"},
]

# stream -> CDP port, must match STREAMS in sookastage_prod.py
STREAM_PORTS = {1: 9223, 2: 9225, 3: 9224}


def _no_window():
    """CREATE_NO_WINDOW for console children -- see sooka_cdp.no_window_kwargs.
    Defined locally so preflight stays runnable without importing the CDP
    stack (it runs before anything touches Discord)."""
    return {"creationflags": 0x08000000} if os.name == "nt" else {}


def _port_listening(port, timeout=1.0):
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def _log(msg):
    print(msg, flush=True)


def ensure_watch_windows():
    """Open any missing sooka.my watch window; tag Chrome Beta's title so the
    picker can tell it apart from plain Chrome (see watch_windows.py)."""
    from watch_windows import find_watch_window, tag_chrome_beta_window

    for w in WATCH_BROWSERS:
        hwnd, _title = find_watch_window(w["path_hint"])
        if hwnd:
            _log(f"  {w['name']} : already open")
            continue
        _log(f"  {w['name']} : no sooka.my window found, opening one...")
        subprocess.Popen([w["exe"], "--new-window", "https://sooka.my/"])
        time.sleep(6)

    found, tagged = tag_chrome_beta_window()
    _log(f"  Chrome Beta tag: found={found} tagged={tagged}")


MANAGER_DIR = (r"C:\Users\irfan\Desktop\Restored-Desktop\SookaStream-Windows-x64-v8.6"
               r"\SookaStream-Windows-x64-v8.6")
PYTHONW = r"C:\Users\irfan\AppData\Local\Programs\Python\Python312\pythonw.exe"


def ensure_renamer():
    """Keep the channel renamer alive.

    Only the one-click launcher used to start it, so once it died -- and it
    does die -- nothing brought it back and channel names silently froze until
    someone noticed. Same gap that used to exist for the Discord clients
    themselves: the watchdog maintained the share state but not the processes
    the system is made of. Starting it here means every watchdog pass repairs
    it within 5 minutes.
    """
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | "
         "Where-Object {$_.CommandLine -like '*run_renamer*'} | Measure-Object).Count"],
        capture_output=True, text=True, timeout=30, **_no_window())
    try:
        running = int((r.stdout or "0").strip())
    except ValueError:
        running = 0
    if running >= 1:
        _log(f"  renamer : already running ({running})")
        return
    _log("  renamer : not running, starting...")
    subprocess.Popen([PYTHONW, os.path.join(MANAGER_DIR, "run_renamer_headless.py")],
                     cwd=MANAGER_DIR, **_no_window())
    time.sleep(2)


def ensure_discord_clients():
    """Launch any Discord client whose CDP port isn't listening -- i.e. the
    process itself is gone, not just its share dropped."""
    for stream, port in STREAM_PORTS.items():
        if _port_listening(port):
            _log(f"  stream {stream} (port {port}) : already up")
            continue
        # Launch, then VERIFY the port arrived. Discord can finish an update
        # right after we start it correctly and relaunch ITSELF without the
        # debug port -- observed live when PTB went 1.0.1220 -> 1.0.1221
        # mid-run, leaving the client running and the port dead. We cannot
        # stop Discord updating itself, but we can notice the port never came
        # up and try once more, which is usually enough once the update has
        # settled. Still failing after that is left to the next watchdog pass
        # rather than looped on here.
        for attempt in (1, 2):
            _log(f"  stream {stream} (port {port}) : not listening, launching"
                 f"{' (retry)' if attempt == 2 else ''}...")
            # -WindowStyle Hidden covers the PowerShell host's own window;
            # CREATE_NO_WINDOW stops the console being allocated in the first
            # place (the watchdog runs under pythonw, so the child would
            # otherwise create its own console and flash it on the desktop).
            subprocess.run(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden",
                 "-ExecutionPolicy", "Bypass", "-File",
                 f"{REPO}\\scripts\\schtask_launch_client.ps1", "-Stream", str(stream)],
                capture_output=True, text=True, timeout=60, **_no_window(),
            )
            for _ in range(15):          # ~15s for the port to appear
                if _port_listening(port):
                    break
                time.sleep(1)
            if _port_listening(port):
                _log(f"  stream {stream} (port {port}) : up")
                break
            _log(f"  stream {stream} (port {port}) : still not listening"
                 f"{' -- leaving it for the next pass' if attempt == 2 else ''}")


def run(argv):
    # Update guard: while a stream is LIVE, freeze any running Discord
    # updater (NT suspend; resumes naturally when streams drop).
    try:
        subprocess.run([PYTHONW, os.path.join(REPO, "update_guard.py"), "guard"],
                       capture_output=True, timeout=60, **_no_window())
    except Exception as _e:
        _log(f"  update_guard: {_e}")
    """Full preflight, then hand off to sookastage_prod.main(argv)."""
    sys.path.insert(0, REPO)
    _log("Checking channel renamer...")
    ensure_renamer()
    _log("Checking watch-browser windows...")
    ensure_watch_windows()
    _log("Checking Discord clients...")
    ensure_discord_clients()
    _log("Running sookastage_prod...")
    import sookastage_prod
    return sookastage_prod.main(argv)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:] or ["--all"]))

