
# -*- coding: utf-8 -*-
"""SookaStage Update Guard.

While ANY stage stream is LIVE, a Discord auto-update must never kill the
running client (observed live: Update.exe relaunches Discord without
--remote-debugging-port -> CDP port dies -> stream drops).

Guarded actions (idempotent, safe every 5-min watchdog cycle):
    guard   -- suspend updater if streams live, else no-op
    status  -- print JSON {updater_pids, port_live}
"""
import json
import subprocess
import sys

NO_WINDOW = 0x08000000
STAGE_PORTS = (9223, 9224, 9225)


def _any_stream_live():
    import urllib.request
    for port in STAGE_PORTS:
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list', timeout=2)
            return True
        except Exception:
            continue
    return False


def _updater_pids():
    out = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "Get-CimInstance Win32_Process -EA SilentlyContinue | "
         "Where-Object { $_.Name -eq 'Update.exe' -and "
         "$_.ExecutablePath -match 'AppData\\\\Local\\\\Discord' } | "
         "Select-Object -First 5 ProcessId | ForEach-Object { $_.ProcessId }"],
        capture_output=True, text=True, timeout=25,
        creationflags=NO_WINDOW)
    raw = (out.stdout or '').strip()
    return [int(x) for x in raw.split() if x.isdigit()]


def _suspend(pid):
    """Suspend a process, without killing it."""
    subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         '$p = Get-Process -Id ' + str(pid) + ' -EA SilentlyContinue; '
         'if ($p) { '
         '$src = @"'
         '{\n'
         'using System;\n'
         'using System.Runtime.InteropServices;\n'
         'public class S {\n'
         '[DllImport("ntdll.dll")] public static extern uint NtSuspendProcess(IntPtr h);\n'
         '}\n'
         '}"@; '
         'Add-Type -TypeDefinition $src -EA SilentlyContinue; '
         '$h = [Win32.S]::NtSuspendProcess($p.Handle) ; "done" }'],
        capture_output=True, text=True, timeout=20,
        creationflags=NO_WINDOW)


def guard():
    pids = _updater_pids()
    any_live = _any_stream_live()
    print(json.dumps({'updater_pids': pids, 'any_live': any_live}))
    if pids and any_live:
        for pid in pids:
            _suspend(pid)
        print(json.dumps({'action': 'suspended %d updater(s) while streams live' % len(pids)}))
        return 0
    print(json.dumps({'action': 'none'}))
    return 0


def status():
    return json.dumps({'updater_pids': _updater_pids(), 'any_live': _any_stream_live()})


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if cmd == 'guard':
        sys.exit(guard())
    print(status())
