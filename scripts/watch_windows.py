"""Keep the sooka.my watch-browser windows identifiable for the share picker.

Chrome Beta's own OS window title never says "Beta" on this machine -- only
the page title would, normally via Tampermonkey's "Set Browser Identity"
(not installed here). A page reload/navigation resets any title we set, so
this re-applies the tag every time it's called; both the one-click launcher
and the watchdog call it before every run.
"""
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
psapi = ctypes.windll.psapi
kernel32 = ctypes.windll.kernel32

TAG = "Chrome Beta"
CHROME_BETA_PATH_HINT = "\\Chrome Beta\\Application\\chrome.exe"
TITLE_PREFIX = "Watch online Live Sports"


def _get_window_text(hwnd):
    length = user32.GetWindowTextLengthW(hwnd)
    if not length:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _get_exe_path(pid):
    h = kernel32.OpenProcess(0x1000 | 0x0400, False, pid)  # QUERY_LIMITED_INFORMATION | QUERY_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        ok = kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
        return buf.value if ok else ""
    finally:
        kernel32.CloseHandle(h)


def find_watch_window(path_hint=None, title_prefix=TITLE_PREFIX):
    """Find the first visible window whose title starts with `title_prefix`
    and (if given) whose owning process's exe path contains `path_hint`
    (case-insensitive). Returns (hwnd, title) or (None, None).

    Used to find each browser's sooka.my tab by *install path*, not just
    process name -- "chrome.exe" alone can't tell plain Chrome from Chrome
    Beta, they share the same executable name in different folders.
    """
    found = {"hwnd": None, "title": None}

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = _get_window_text(hwnd)
        if not title.startswith(title_prefix):
            return True
        if path_hint:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            path = _get_exe_path(pid.value)
            if path_hint.lower() not in path.lower():
                return True
        found["hwnd"] = hwnd
        found["title"] = title
        return False  # stop enumeration, we found it

    user32.EnumWindows(_enum, 0)
    return found["hwnd"], found["title"]


def tag_chrome_beta_window():
    """Find the visible Chrome Beta window showing sooka.my and make sure its
    title carries "Chrome Beta". Returns (found: bool, tagged: bool)."""
    hwnd, title = find_watch_window(CHROME_BETA_PATH_HINT)
    if not hwnd:
        return False, False
    if TAG in title:
        return True, False
    user32.SetWindowTextW(hwnd, f"{title} - {TAG}")
    return True, True


if __name__ == "__main__":
    found, tagged = tag_chrome_beta_window()
    if not found:
        print("no sooka.my Chrome Beta window found")
    elif tagged:
        print("tagged Chrome Beta window")
    else:
        print("Chrome Beta window already tagged")
