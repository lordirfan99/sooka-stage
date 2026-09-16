"""Hardened CDP transport + verified click engine for the SookaStage automation.

This module replaces the hand-rolled WebSocket/evaluate code that was copy-pasted
into `cdp_lib.py`, `probe_panel.py`, `api_stage.py` and `sookastage_prod.py`.
See HERMES_GUIDE.md for the full reasoning; the short version:

* The old frame readers ignored the WebSocket opcode, so one PING or one
  fragmented frame from the DevTools server killed the run with a JSON error.
* `ev()` parsed the JSON string returned by Runtime.evaluate, then the caller
  parsed it *again* -> TypeError -> swallowed -> every click became a no-op.
* Clicks were fired blind. No visibility check, no "is something covering this
  element" check, and no proof that the coordinate we dispatched at actually
  landed on the button we meant.

The click engine here fixes the last point by hit-testing: it dispatches a real
`mouseMoved`, then asks the page which element is `:hover`. `:hover` only reacts
to trusted input, so a hit proves the coordinate space is right before we commit
to pressing the button.

Windows-only helpers are imported lazily, so this module imports cleanly (and is
unit-testable) on Linux/macOS.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import struct
import sys
import time
import urllib.error
import urllib.request
from collections import deque

IS_WINDOWS = os.name == "nt"

OP_CONT, OP_TEXT, OP_BIN, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA

# CDP modifier bitmask: Alt=1, Ctrl=2, Meta=4, Shift=8
MOD_ALT, MOD_CTRL, MOD_META, MOD_SHIFT = 1, 2, 4, 8


class CDPError(RuntimeError):
    """Any CDP-level failure (bad handshake, evaluate threw, target gone)."""


class CDPTimeout(CDPError):
    """A request was sent but no matching response arrived in time."""


# --------------------------------------------------------------------------
# WebSocket framing
# --------------------------------------------------------------------------
def encode_frame(payload: bytes, opcode: int = OP_TEXT) -> bytes:
    """Client -> server frame. Client frames MUST be masked (RFC 6455)."""
    n = len(payload)
    if n < 126:
        head = struct.pack("!BB", 0x80 | opcode, 0x80 | n)
    elif n < 65536:
        head = struct.pack("!BBH", 0x80 | opcode, 0x80 | 126, n)
    else:
        head = struct.pack("!BBQ", 0x80 | opcode, 0x80 | 127, n)
    key = os.urandom(4)
    return head + key + bytes(b ^ key[i % 4] for i, b in enumerate(payload))


def _read_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise CDPError("websocket closed by peer (DevTools target died?)")
        buf += chunk
    return buf


def read_frame(sock: socket.socket):
    """Return (fin, opcode, payload). Handles server masking even though
    servers never mask -- cheap insurance against odd proxies."""
    b = _read_exact(sock, 2)
    fin = bool(b[0] & 0x80)
    opcode = b[0] & 0x0F
    masked = bool(b[1] & 0x80)
    n = b[1] & 0x7F
    if n == 126:
        n = struct.unpack("!H", _read_exact(sock, 2))[0]
    elif n == 127:
        n = struct.unpack("!Q", _read_exact(sock, 8))[0]
    key = _read_exact(sock, 4) if masked else b""
    data = _read_exact(sock, n) if n else b""
    if masked and data:
        data = bytes(c ^ key[i % 4] for i, c in enumerate(data))
    return fin, opcode, data


# --------------------------------------------------------------------------
# Target discovery
# --------------------------------------------------------------------------
def http_json(port: int, path: str = "/json", timeout: float = 8.0, tries: int = 3):
    """GET the DevTools HTTP endpoint with retries.

    On the old main build (app-1.0.9258) this endpoint wedges after a handful of
    WebSocket sessions. Retrying is cheap; the real mitigation is to call this
    ONCE per process and then keep a single persistent ws (see CDP.connect).
    """
    url = f"http://127.0.0.1:{port}{path}"
    last = None
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as exc:  # noqa: BLE001 - we genuinely want any failure
            last = exc
            time.sleep(0.6 * (attempt + 1))
    refused = isinstance(last, urllib.error.URLError) and isinstance(
        getattr(last, "reason", None), ConnectionRefusedError
    )
    if refused:
        hint = ("nothing is listening -- this Discord client is not running, or it was "
                f"started without --remote-debugging-port={port}")
    else:
        hint = ("the port is open but /json did not answer -- this is the known DevTools "
                "wedge on the old main build; restart that Discord client")
    raise CDPError(f"{url}: {hint} ({last!r})")


def pick_page(targets, guild_id: str | None = None, channel_id: str | None = None):
    """Choose the Discord app page from a /json listing.

    Preference order: exact channel URL > same guild > any discord.com page >
    any page at all. The old code did `[t for t in j if ...][0]` which raised
    IndexError whenever the client happened to be on another view.
    """
    pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    if not pages:
        return None

    def score(t):
        url = t.get("url", "") or ""
        if channel_id and url.rstrip("/").endswith("/" + str(channel_id)):
            return 4
        if guild_id and f"/channels/{guild_id}" in url:
            return 3
        if "discord.com/channels" in url:
            return 2
        if "discord.com" in url:
            return 1
        return 0

    best = max(pages, key=score)
    return best if score(best) > 0 or len(pages) == 1 else best


def parse_netstat_pid(netstat_output: str, port: int):
    """Pull the LISTENING pid for an exact local port out of `netstat -ano`.

    The old `findstr ":9223"` matched 19223, remote ports and TIME_WAIT rows,
    and then kept the LAST match. This anchors on the local address.
    """
    want = f":{port}"
    for line in netstat_output.splitlines():
        parts = line.split()
        if len(parts) < 5 or "LISTENING" not in line:
            continue
        local = parts[1]
        if not local.endswith(want):
            continue
        try:
            return int(parts[-1])
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------
# JS payloads
# --------------------------------------------------------------------------
FIND_JS = r"""
(() => {
  const SELECTOR = __SELECTOR__;
  const match = (el) => (__PRED__);
  const out = {count: 0, rect: null, label: null, covered: null, cover_label: null,
               zoom: 1, viewport: null, candidates: [], error: null};
  let els = [];
  try { els = Array.prototype.slice.call(document.querySelectorAll(SELECTOR)); }
  catch (e) { out.error = 'selector: ' + e; return JSON.stringify(out); }
  const label = (el) => (((el.getAttribute && el.getAttribute('aria-label')) || '') + ' ' +
                         (el.textContent || '')).replace(/\s+/g, ' ').trim().slice(0, 120);
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 3 || r.height < 3) return false;
    if (r.bottom < 0 || r.right < 0 || r.top > window.innerHeight || r.left > window.innerWidth) return false;
    const s = getComputedStyle(el);
    return s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity || '1') > 0.05;
  };
  const hits = [];
  for (const el of els) {
    let ok = false;
    try { ok = !!match(el); } catch (e) { ok = false; }
    if (ok && visible(el)) hits.push(el);
  }
  out.count = hits.length;
  out.candidates = hits.slice(0, 8).map(label);
  if (!hits.length) return JSON.stringify(out);
  const el = hits[0];
  window.__sookaTarget = el;
  const r = el.getBoundingClientRect();
  let zoom = 1;
  for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
    const z = parseFloat(getComputedStyle(n).zoom || '1');
    if (z && z !== 1) zoom *= z;
  }
  out.zoom = zoom;
  out.label = label(el);
  out.rect = {x: r.x, y: r.y, w: r.width, h: r.height, cx: r.x + r.width / 2, cy: r.y + r.height / 2};
  out.viewport = {w: window.innerWidth, h: window.innerHeight, dpr: window.devicePixelRatio,
                  sx: window.screenX, sy: window.screenY, ow: window.outerWidth, oh: window.outerHeight};
  try {
    const top = document.elementFromPoint(out.rect.cx, out.rect.cy);
    out.covered = !(top && (top === el || el.contains(top) || top.contains(el)));
    out.cover_label = (out.covered && top) ? label(top) : null;
  } catch (e) { out.covered = null; }
  return JSON.stringify(out);
})()
"""

# ':hover' is only set by TRUSTED pointer input, so this is real proof that the
# coordinate we dispatched at reached the element we aimed for.
HOVER_JS = r"""
(() => {
  const t = window.__sookaTarget;
  if (!t) return 'no-target';
  const all = document.querySelectorAll(':hover');
  const h = all.length ? all[all.length - 1] : null;
  if (!h) return 'none';
  if (h === t || t.contains(h) || h.contains(t)) return 'hit';
  const lab = ((h.getAttribute && h.getAttribute('aria-label')) || h.textContent || '')
                .replace(/\s+/g, ' ').trim().slice(0, 60);
  return 'miss:' + (h.tagName || '?') + ':' + lab;
})()
"""

JS_CLICK_JS = r"""
(() => {
  const t = window.__sookaTarget;
  if (!t) return 'no-target';
  const r = t.getBoundingClientRect();
  const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
  const opts = {bubbles: true, cancelable: true, view: window, clientX: cx, clientY: cy, button: 0, buttons: 1};
  try {
    t.dispatchEvent(new PointerEvent('pointerdown', Object.assign({pointerId: 1, isPrimary: true, pointerType: 'mouse'}, opts)));
    t.dispatchEvent(new MouseEvent('mousedown', opts));
    t.dispatchEvent(new PointerEvent('pointerup', Object.assign({pointerId: 1, isPrimary: true, pointerType: 'mouse'}, opts, {buttons: 0})));
    t.dispatchEvent(new MouseEvent('mouseup', Object.assign({}, opts, {buttons: 0})));
    t.dispatchEvent(new MouseEvent('click', Object.assign({}, opts, {buttons: 0})));
    if (typeof t.click === 'function') { t.click(); }
    return 'ok';
  } catch (e) { return 'error:' + e; }
})()
"""

DEFAULT_SELECTOR = "button,[role=button],a,li,[role=menuitem],[role=treeitem]"


# --------------------------------------------------------------------------
# The client
# --------------------------------------------------------------------------
class CDP:
    """One persistent DevTools WebSocket session.

    Deliberately ONE ws per process: reconnecting is what wedges the /json
    endpoint on the old main build.
    """

    def __init__(self, sock: socket.socket, port: int, page_url: str = "", logger=None):
        self.sock = sock
        self.port = port
        self.page_url = page_url
        self._id = 0
        self._events = deque(maxlen=400)
        self._log = logger or (lambda *_a, **_k: None)
        # Coordinate scale discovered by hit-testing; None until calibrated.
        self.scale = None

    # ---- lifecycle -------------------------------------------------------
    @classmethod
    def connect(cls, port: int, guild_id=None, channel_id=None, timeout: float = 10.0, logger=None):
        targets = http_json(port, "/json", timeout=timeout)
        page = pick_page(targets, guild_id, channel_id)
        if not page:
            raise CDPError(
                f"port {port}: DevTools answered but exposed no page target. "
                "Is this Discord client actually running with --remote-debugging-port?"
            )
        ws_url = page["webSocketDebuggerUrl"]
        host, _, rest = ws_url.split("/", 3)[2].partition(":")
        ws_port = int(rest)
        path = ws_url.split(f":{ws_port}", 1)[1]
        sock = socket.create_connection((host, ws_port), timeout=timeout)
        sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall(
            (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host}:{ws_port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).encode()
        )
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = sock.recv(4096)
            if not chunk:
                raise CDPError("DevTools closed the connection during the WebSocket handshake")
            resp += chunk
        status = resp.split(b"\r\n", 1)[0].decode("latin-1")
        if "101" not in status:
            raise CDPError(f"WebSocket handshake refused: {status}")
        return cls(sock, port, page.get("url", ""), logger=logger)

    def close(self):
        try:
            self.sock.sendall(encode_frame(b"", OP_CLOSE))
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
        return False

    # ---- transport -------------------------------------------------------
    def _recv_message(self, deadline: float):
        """Read one complete CDP message, answering PINGs and reassembling
        fragmented frames along the way."""
        chunks, op = b"", None
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise CDPTimeout("timed out waiting for a DevTools frame")
            self.sock.settimeout(max(0.2, remaining))
            fin, opcode, data = read_frame(self.sock)
            if opcode == OP_PING:
                self.sock.sendall(encode_frame(data, OP_PONG))
                continue
            if opcode == OP_PONG:
                continue
            if opcode == OP_CLOSE:
                raise CDPError("DevTools sent a close frame (target navigated away or died)")
            if opcode in (OP_TEXT, OP_BIN):
                chunks, op = data, opcode
            elif opcode == OP_CONT:
                chunks += data
            if fin and op is not None:
                try:
                    return json.loads(chunks.decode("utf-8", "replace"))
                except ValueError:
                    chunks, op = b"", None
                    continue

    def call(self, method: str, params=None, timeout: float = 20.0):
        self._id += 1
        mid = self._id
        payload = json.dumps({"id": mid, "method": method, "params": params or {}}).encode()
        self.sock.sendall(encode_frame(payload))
        deadline = time.time() + timeout
        while True:
            msg = self._recv_message(deadline)
            if msg.get("id") == mid:
                if "error" in msg:
                    raise CDPError(f"{method}: {msg['error']}")
                return msg.get("result", {})
            self._events.append(msg)

    def drain_events(self):
        out = list(self._events)
        self._events.clear()
        return out

    # ---- evaluate --------------------------------------------------------
    def evaluate(self, expr: str, await_promise: bool = False, timeout: float = 20.0):
        """Return the raw JS value. Raises if the expression threw.

        NOTE: this returns the value EXACTLY as JS produced it. If your JS ends
        in JSON.stringify(), use evaluate_json() -- do not parse twice. Parsing
        twice is the bug that silently disabled every click in the old runner.
        """
        res = self.call(
            "Runtime.evaluate",
            {"expression": expr, "returnByValue": True, "awaitPromise": await_promise},
            timeout=timeout,
        )
        exc = res.get("exceptionDetails")
        if exc:
            text = (exc.get("exception") or {}).get("description") or exc.get("text") or str(exc)
            raise CDPError("JS threw: " + str(text)[:300])
        return (res.get("result") or {}).get("value")

    def evaluate_json(self, expr: str, await_promise: bool = False, timeout: float = 20.0):
        value = self.evaluate(expr, await_promise=await_promise, timeout=timeout)
        if isinstance(value, (dict, list)) or value is None:
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except ValueError:
                return value
        return value

    # ---- element lookup --------------------------------------------------
    def find(self, pred: str, selector: str = DEFAULT_SELECTOR):
        """Find the first visible element where `pred` (JS over `el`) is true.

        Returns the FIND_JS dict: count, rect, label, covered, cover_label,
        zoom, viewport, candidates. Also stashes the node on window.__sookaTarget
        so the hit-test and the JS-click fallback can reuse it.
        """
        expr = FIND_JS.replace("__SELECTOR__", json.dumps(selector)).replace("__PRED__", pred)
        out = self.evaluate_json(expr)
        if not isinstance(out, dict):
            raise CDPError(f"find() returned {out!r} instead of a dict -- check the predicate")
        return out

    def wait_for(self, check, timeout: float = 15.0, interval: float = 0.6, desc: str = ""):
        """Poll `check()` until it returns something truthy. Returns the value or
        None. Replaces the old fixed time.sleep(8/12/7) guesswork."""
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            try:
                last = check()
            except CDPError as exc:
                self._log(f"wait_for({desc}) transient: {exc}")
                last = None
            if last:
                return last
            time.sleep(interval)
        self._log(f"wait_for({desc}) timed out after {timeout}s")
        return None

    def wait_find(self, pred: str, selector: str = DEFAULT_SELECTOR, timeout: float = 15.0, desc: str = ""):
        return self.wait_for(
            lambda: (lambda f: f if f.get("count") else None)(self.find(pred, selector)),
            timeout=timeout,
            desc=desc or pred[:40],
        )

    # ---- input -----------------------------------------------------------
    def dispatch_mouse(self, kind: str, x: float, y: float, buttons: int = 0, click_count: int = 0):
        self.call(
            "Input.dispatchMouseEvent",
            {
                "type": kind,
                "x": float(x),
                "y": float(y),
                "button": "left" if kind != "mouseMoved" else "none",
                "buttons": buttons,
                "clickCount": click_count,
                "pointerType": "mouse",
            },
        )

    def scale_ladder(self, found):
        """Coordinate spaces worth trying, best guess first.

        getBoundingClientRect() and Input.dispatchMouseEvent agree on modern
        Chromium, but older Electron (the app-1.0.9258 main build) reports rects
        in the UNZOOMED space while Input wants viewport pixels. Rather than
        guess the build, we try and hit-test.
        """
        zoom = found.get("zoom") or 1
        dpr = ((found.get("viewport") or {}).get("dpr")) or 1
        ladder, seen = [], set()
        for s in (self.scale, 1.0, zoom, 1.0 / zoom if zoom else None, dpr, 1.0 / dpr if dpr else None):
            if not s or s <= 0:
                continue
            k = round(float(s), 4)
            if k in seen:
                continue
            seen.add(k)
            ladder.append(float(s))
        return ladder

    def click(self, pred: str, selector: str = DEFAULT_SELECTOR, trusted_only: bool = True,
              settle: float = 0.15, found=None):
        """Click an element and REPORT WHETHER IT ACTUALLY LANDED.

        `trusted_only=True` means we never fall back to a synthetic JS click.
        Use it for anything gated on user activation -- Share Your Screen and
        Go Live both are, which is why JS clicks silently do nothing there.
        Non-gated things (navigation, joining a stage, dismissing a modal) can
        set trusted_only=False.

        Returns a dict: {ok, reason, label, scale, hover, covered, candidates}.
        """
        f = found if found is not None else self.find(pred, selector)
        result = {
            "ok": False,
            "reason": "",
            "label": f.get("label"),
            "count": f.get("count"),
            "candidates": f.get("candidates"),
            "covered": f.get("covered"),
            "cover_label": f.get("cover_label"),
            "scale": None,
            "hover": None,
            "method": None,
        }
        if not f.get("count"):
            result["reason"] = "not-found"
            return result

        hover = None
        for scale in self.scale_ladder(f):
            cx = f["rect"]["cx"] * scale
            cy = f["rect"]["cy"] * scale
            self.dispatch_mouse("mouseMoved", cx, cy)
            time.sleep(0.12)
            hover = self.evaluate(HOVER_JS)
            if hover == "hit":
                self.scale = scale
                result["scale"] = scale
                result["hover"] = hover
                self.dispatch_mouse("mousePressed", cx, cy, buttons=1, click_count=1)
                time.sleep(0.09)
                self.dispatch_mouse("mouseReleased", cx, cy, buttons=0, click_count=1)
                time.sleep(settle)
                result["ok"] = True
                result["method"] = "cdp-input"
                result["reason"] = "clicked"
                return result

        result["hover"] = hover
        if f.get("covered"):
            result["reason"] = f"covered-by:{f.get('cover_label')}"
        else:
            result["reason"] = f"no-coordinate-hit ({hover})"

        if trusted_only:
            return result

        js = self.evaluate(JS_CLICK_JS)
        result["method"] = "js-synthetic"
        result["ok"] = js == "ok"
        result["reason"] = f"js-fallback:{js}"
        time.sleep(settle)
        return result

    def js_click(self, pred: str, selector: str = DEFAULT_SELECTOR):
        """Synthetic click, no coordinates involved. Fine for navigation and for
        joining a stage; NOT fine for activation-gated buttons."""
        f = self.find(pred, selector)
        if not f.get("count"):
            return {"ok": False, "reason": "not-found", "candidates": f.get("candidates")}
        js = self.evaluate(JS_CLICK_JS)
        return {"ok": js == "ok", "reason": js, "label": f.get("label"), "method": "js-synthetic"}

    def key(self, key_name: str, code: str, vk: int, modifiers: int = 0, text: str | None = None):
        base = {"modifiers": modifiers, "key": key_name, "code": code,
                "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk}
        down = dict(base, type="keyDown" if text else "rawKeyDown")
        if text:
            down["text"] = text
        self.call("Input.dispatchKeyEvent", down)
        time.sleep(0.05)
        self.call("Input.dispatchKeyEvent", dict(base, type="keyUp"))

    def insert_text(self, text: str):
        self.call("Input.insertText", {"text": text})

    def navigate(self, url: str):
        self.call("Page.navigate", {"url": url})

    def bring_to_front(self):
        try:
            self.call("Page.bringToFront")
            return True
        except CDPError:
            return False


# --------------------------------------------------------------------------
# Windows helpers (lazy, so this file imports fine on Linux)
# --------------------------------------------------------------------------
def _user32():
    if not IS_WINDOWS:
        raise RuntimeError("Windows-only helper called on " + sys.platform)
    import ctypes
    return ctypes.windll.user32


def find_window_by_pid(pid: int, name_hint: str = "Discord", min_w: int = 400):
    """Return (hwnd, left, top, title, width, iconic) or None.

    The old version could return None and then immediately unpack it into six
    names, which raised TypeError with no context at all.
    """
    import ctypes
    import ctypes.wintypes as wt

    u = _user32()
    found = []

    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    def cb(hwnd, _lparam):
        rect = wt.RECT()
        u.GetWindowRect(hwnd, ctypes.byref(rect))
        owner = wt.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and u.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            u.GetWindowTextW(hwnd, buf, 256)
            found.append((hwnd, rect.left, rect.top, buf.value,
                          rect.right - rect.left, bool(u.IsIconic(hwnd))))
        return True

    u.EnumWindows(CB(cb), 0)
    if not found:
        return None
    named = [w for w in found if name_hint.lower() in (w[3] or "").lower() and w[4] >= min_w]
    if named:
        return named[0]
    found.sort(key=lambda w: -w[4])
    return found[0]


def force_foreground(hwnd) -> bool:
    """SetForegroundWindow that survives the Windows foreground lock.

    A bare SetForegroundWindow from a scheduled-task context returns "success"
    and does nothing, because the task's thread does not own the foreground.
    AttachThreadInput borrows the current foreground thread's input queue for
    long enough that the call is honoured. This is next-step #2 from
    SOOKASTAGE_PROGRESS.md.
    """
    import ctypes

    u = _user32()
    kernel32 = ctypes.windll.kernel32
    SW_RESTORE = 9
    if u.IsIconic(hwnd):
        u.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.4)
    fg = u.GetForegroundWindow()
    if fg == hwnd:
        return True
    target_thread = u.GetWindowThreadProcessId(hwnd, None)
    fg_thread = u.GetWindowThreadProcessId(fg, None) if fg else 0
    this_thread = kernel32.GetCurrentThreadId()
    attached = []
    for other in {fg_thread, target_thread}:
        if other and other != this_thread and u.AttachThreadInput(this_thread, other, True):
            attached.append(other)
    try:
        u.BringWindowToTop(hwnd)
        u.ShowWindow(hwnd, SW_RESTORE)
        ok = bool(u.SetForegroundWindow(hwnd))
    finally:
        for other in attached:
            u.AttachThreadInput(this_thread, other, False)
    time.sleep(0.3)
    return ok or u.GetForegroundWindow() == hwnd


def real_mouse_click(screen_x: int, screen_y: int, settle: float = 0.25):
    """Last-resort physical click via SendInput (absolute coordinates).

    Only needed if CDP input is refused outright. Coordinates are PHYSICAL
    pixels -- run `python sooka_diag.py --calibrate <port>` first.
    """
    import ctypes

    u = _user32()
    sw = u.GetSystemMetrics(0)
    sh = u.GetSystemMetrics(1)
    u.SetCursorPos(int(screen_x), int(screen_y))
    time.sleep(0.12)
    MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
    u.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.06)
    u.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(settle)
    return {"screen": (int(screen_x), int(screen_y)), "desktop": (sw, sh)}
