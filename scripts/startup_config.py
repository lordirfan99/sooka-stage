"""Read and change what actually starts with Windows. No UI state, no lies.

Two independent switches, because they are genuinely different things:

  sookastage  -- whether SookaStage itself launches at logon (a per-user
                 Scheduled Task running the one-click launcher windowless).
                 Default OFF. Nothing here ever enables it implicitly.

  discord     -- whether Discord/Canary/PTB launch themselves at logon via
                 their own HKCU Run entries.

Why the second one exists: Discord's own Run entries are the reason clients
appear after a reboot without anyone clicking anything, and -- more
importantly -- they start Discord WITHOUT --remote-debugging-port. Discord is
single-instance, so that portless copy then blocks SookaStage from ever
attaching; the launcher has to kill it and start over on every run. Turning
Discord's autostart off makes the boot state clean and lets SookaStage own
client startup.

Disabling Discord autostart does NOT delete anything: each value is moved to
a `SookaStage.Backup.<name>` value in the same key and moved back on enable,
so it is fully reversible and survives someone forgetting what it was.

    python scripts/startup_config.py status
    python scripts/startup_config.py sookastage on|off
    python scripts/startup_config.py discord on|off
"""
import os
import subprocess
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
BACKUP_PREFIX = "SookaStage.Backup."
# Only entries this project has a legitimate reason to manage.
DISCORD_VALUES = ("Discord", "DiscordCanary", "DiscordPTB")

RUN_VALUE = "SookaStage"
LAUNCHER = r"C:\Users\irfan\Desktop\sooka-stage\scripts\start_sookastage.ps1"

NO_WINDOW = {"creationflags": 0x08000000} if os.name == "nt" else {}


def _winreg():
    import winreg
    return winreg


# ── Discord autostart ────────────────────────────────────────────────────────
def discord_status():
    """-> {name: 'on'|'off'} for each Discord Run entry we know about."""
    winreg = _winreg()
    out = {}
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        present, backed_up = set(), set()
        i = 0
        while True:
            try:
                name, _val, _type = winreg.EnumValue(key, i)
            except OSError:
                break
            i += 1
            if name.startswith(BACKUP_PREFIX):
                backed_up.add(name[len(BACKUP_PREFIX):])
            else:
                present.add(name)
    for name in DISCORD_VALUES:
        if name in present:
            out[name] = "on"
        elif name in backed_up:
            out[name] = "off"
    return out


def discord_set(enable: bool):
    """Move Discord Run entries out of the way (or put them back)."""
    winreg = _winreg()
    changed = []
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                        winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
        for name in DISCORD_VALUES:
            backup = BACKUP_PREFIX + name
            src, dst = (backup, name) if enable else (name, backup)
            try:
                value, vtype = winreg.QueryValueEx(key, src)
            except FileNotFoundError:
                continue  # nothing to move in that direction
            winreg.SetValueEx(key, dst, 0, vtype, value)
            winreg.DeleteValue(key, src)
            changed.append(name)
    return changed


# ── SookaStage autostart ─────────────────────────────────────────────────────
def sookastage_status():
    """-> 'on' | 'off'. Reads the registry, not a saved preference."""
    winreg = _winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, RUN_VALUE)
        return "on"
    except FileNotFoundError:
        return "off"


def sookastage_set(enable: bool):
    """An HKCU Run entry, deliberately not a Scheduled Task.

    Task Scheduler writes need elevation on this machine (UAC token
    filtering), so a task-based switch would fail with "Access is denied" for
    the normal user who is meant to flip it. HKCU Run needs no elevation, is
    the same mechanism Discord itself uses, and is what the `discord` switch
    already manipulates -- one concept, not two.

    -NonInteractive matters: at logon nobody can answer the launcher's
    "press any key", and without it the process would wait forever unseen.
    """
    winreg = _winreg()
    cmd = ('powershell.exe -NoProfile -WindowStyle Hidden '
           f'-ExecutionPolicy Bypass -File "{LAUNCHER}" -NonInteractive')
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            if enable:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE)
                except FileNotFoundError:
                    return True, "already off"
        return True, ""
    except OSError as exc:
        return False, str(exc)


def print_status():
    print("SookaStage starts with Windows :", sookastage_status().upper())
    print("Discord clients start themselves:")
    ds = discord_status()
    if not ds:
        print("    (no Discord Run entries found)")
    for name, state in sorted(ds.items()):
        print(f"    {name:<14} {state.upper()}")


def main(argv):
    if os.name != "nt":
        print("windows only", file=sys.stderr)
        return 2
    if not argv or argv[0] == "status":
        print_status()
        return 0

    target = argv[0]
    if len(argv) < 2 or argv[1] not in ("on", "off"):
        print(f"usage: startup_config.py {target} on|off", file=sys.stderr)
        return 2
    enable = argv[1] == "on"

    try:
        if target == "sookastage":
            ok, detail = sookastage_set(enable)
            if not ok:
                print(f"could not change startup: {detail}", file=sys.stderr)
                return 1
        elif target == "discord":
            changed = discord_set(enable)
            if not changed:
                print("nothing to change (already in that state)")
        else:
            print(f"unknown target {target!r} (sookastage|discord|status)", file=sys.stderr)
            return 2
    except PermissionError as exc:
        print(f"Windows refused the change: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"could not change startup: {exc}", file=sys.stderr)
        return 1

    print()
    print_status()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
