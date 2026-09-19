
# -*- coding: utf-8 -*-
"""SookaStage Update Control — freeze or allow Discord self-updates.

WHY: a Discord auto-update mid-stream kills the running client (observed live
PTB 1.0.1220 -> 1.0.1221 on 2026-09-19: the client exits, the old app-* dir is
stripped, the CDP port dies, and the stream drops). The launcher already
resolves the newest build at runtime, so an *update is not fatal* on paper --
but it is fatal while a stream is LIVE.

Modes
-----
    python update_control.py status   # show block state (exit 0 = blocked)
    python update_control.py block    # freeze updates (hosts entries)
    python update_control.py unblock  # allow updates again

Implementation: append/strip marker lines to %WINDIR%\System32\drivers\hosts
blocking the Discord update endpoints. Requires an elevated shell (writes to
hosts); the Manager GUI runs elevated schtasks for exactly this reason.

Domains blocked (only these three are touched; nothing else):
    updates.discordapp.com
    discordapp.com/api/update        -> hosts blocks by hostname, so:
    discordapp.com                   (broad -- acceptable: only used by update CDN)
    squirrel.docker.io
"""
import os
import sys
import subprocess
from pathlib import Path

HOSTS = Path(os.getenv('WINDIR', r'C:\Windows')) / 'System32' / 'drivers' / 'etc' / 'hosts'
MARK_BEGIN = '# BEGIN SookaStage update-lock (do not edit)'
MARK_END = '# END SookaStage update-lock'
DOMAINS = [
    'updates.discordapp.com',
    'dl.discordapp.net',
    'squirrel.docker.io',
    'discord-updates.a.akamaihd.net',
]



def _read_hosts():
    if HOSTS.exists():
        return HOSTS.read_text(encoding='utf-8', errors='replace').splitlines()
    return []


def _write_hosts(lines):
    HOSTS.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def status():
    text = '\n'.join(_read_hosts())
    locked = MARK_BEGIN in text
    print('locked' if locked else 'unlocked')
    return 0 if locked else 1


def block():
    lines = _read_hosts()
    if MARK_BEGIN in '\n'.join(lines):
        _write_hosts(lines)          # idempotent: rewrite as-is
        print('already locked')
        return 0
    block_lines = [MARK_BEGIN]
    for dom in DOMAINS:
        block_lines.append('127.0.0.1 ' + dom)
    block_lines.append(MARK_END)
    _write_hosts(lines + block_lines)
    os.system('ipconfig /flushdns >nul 2>&1')
    print('locked')
    return 0


def unblock():
    lines = _read_hosts()
    kept = []
    inside = False
    for line in lines:
        if line.strip() == MARK_BEGIN:
            inside = True
            continue
        if line.strip() == MARK_END:
            inside = False
            continue
        if not inside:
            kept.append(line)
    _write_hosts(kept)
    print('unlocked')
    return 0


def is_elevated():
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if not is_elevated():
        print('REQUIRES_ELEVATION')
        return 5
    return {'status': status, 'block': block, 'unblock': unblock}.get(cmd, status)()


if __name__ == '__main__':
    sys.exit(main())
