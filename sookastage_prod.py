"""SookaStage production runner -- stage + screenshare automation per streamer.

    python sookastage_prod.py --stream 1
    python sookastage_prod.py --all
    python sookastage_prod.py --stream 1 --diagnose      # look, never click
    python sookastage_prod.py --stream 1 --dump-buttons  # print every button label

What changed vs the v1 draft (details in HERMES_GUIDE.md):

1. v1's `clipped_click` parsed the evaluate result twice, hit TypeError, caught
   it and returned None -- so EVERY click was a silent no-op. The runner
   connected, logged, and did nothing.
2. v1's steps 3 and 4 passed a predicate that never referenced the element being
   tested, so `.find()` matched the first button on the page instead of the
   picker tile / Go Live button.
3. v1 clicked "Continue without starting", which is precisely the branch that
   leaves the stage NOT started -- and "Share Your Screen" only exists on a
   started stage. That is the ch1 symptom in SOOKASTAGE_PROGRESS.md.
4. Fixed sleeps replaced with state polling, and every step is verified against
   a state snapshot before the next one runs.

Every regex the flow depends on lives in SELECTORS below. If Discord renames a
button, fix it there and nowhere else -- `--dump-buttons` shows the live labels.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from sooka_cdp import (
    CDP,
    CDPError,
    MOD_CTRL,
    MOD_SHIFT,
    find_window_by_pid,
    force_foreground,
    parse_netstat_pid,
)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

GUILD_ID = "1251553669644816518"

STREAMS = {
    1: {"port": 9223, "client": "Discord (stable)", "browser": "Brave",
        "channel": "1477692113738137600"},
    2: {"port": 9225, "client": "Canary", "browser": "Chrome Beta",
        "channel": "1481358977584599283"},
    3: {"port": 9224, "client": "PTB", "browser": "Google Chrome",
        "channel": "1481359453759475876"},
}

# Every label the flow matches on, in one place.
SELECTORS = {
    "deafen_on": r"^\s*undeafen",          # this button exists only WHILE deafened
    "start_stage": r"start stage|start the stage",
    "continue_without": r"continue without starting",
    "share": r"share your screen",
    "golive": r"go live",
    "stop": r"stop streaming",
    "join_stage": r"join stage|join channel",
}

# Known browser identities for picker-tile disambiguation. Longest match wins,
# so "Google Chrome" never collides with "Chrome Beta".
KNOWN_BROWSERS = ["brave", "chrome beta", "google chrome", "chromium",
                  "microsoft edge", "firefox", "opera"]

LOG_PATH = os.environ.get("SOOKASTAGE_LOG") or (
    r"C:\Users\irfan\sookastage_prod.log" if os.name == "nt"
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "sookastage_prod.log")
)


def log(message):
    import datetime
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {message}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8", errors="replace") as fh:
            fh.write(line + "\n")
    except OSError:
        pass  # a missing log dir must never take the stream down


# --------------------------------------------------------------------------
# JS predicates
# --------------------------------------------------------------------------
LABEL_JS = r"(((el.getAttribute&&el.getAttribute('aria-label'))||'')+' '+(el.textContent||'')).replace(/\s+/g,' ').trim()"


def by_label(pattern: str, in_dialog: bool = False, max_len: int | None = None) -> str:
    """JS predicate: element label matches `pattern` (case-insensitive)."""
    parts = [f"/{pattern}/i.test({LABEL_JS})"]
    if in_dialog:
        parts.append("!!el.closest('[role=dialog]')")
    if max_len:
        parts.append(f"{LABEL_JS}.length <= {max_len}")
    return " && ".join(parts)


def by_href(channel_id: str) -> str:
    return (
        "el.tagName === 'A' && (el.getAttribute('href')||'').replace(/\\/$/,'')"
        f".endsWith('/{channel_id}')"
    )


STATE_JS = r"""
(() => {
  const txt = (document.body.innerText || '');
  const nodes = Array.prototype.slice.call(document.querySelectorAll('button,[role=button],[role=switch]'));
  const lab = (e) => (((e.getAttribute && e.getAttribute('aria-label')) || '') + ' ' + (e.textContent || '')).replace(/\s+/g, ' ').trim();
  const labels = nodes.map(lab).filter(Boolean);
  const any = (re) => labels.some(l => re.test(l));
  const dlg = document.querySelector('[role=dialog]');
  const dlgText = dlg ? (dlg.innerText || '').replace(/\s+/g, ' ').trim() : null;
  return JSON.stringify({
    url: location.href,
    channel: (location.pathname.split('/').filter(Boolean).pop() || null),
    ready: !!document.querySelector('[class*=panels]'),
    dialog: dlgText ? dlgText.slice(0, 240) : null,
    topic_modal: !!(dlgText && /start the stage|stage topic|topic/i.test(dlgText)) && any(/start stage/i),
    deaf_modal: /server deafened|you are deafened|undeafen to speak/i.test(txt),
    deafened: any(/^\s*undeafen/i),
    muted: any(/^\s*unmute/i),
    can_start_stage: any(/start stage|start the stage/i),
    continue_without: any(/continue without starting/i),
    join_stage: any(/join stage/i),
    share_button: any(/share your screen/i),
    golive: any(/go live/i),
    picker_open: !!(dlgText && /screen|application|window/i.test(dlgText)) && any(/go live/i),
    streaming: any(/stop streaming/i) || /stop streaming/i.test(txt),
    sooka_panel: /watch online live sports/i.test(txt),
    buttons: labels.slice(0, 70)
  });
})()
"""

TILE_JS = r"""
(() => {
  const dlg = document.querySelector('[role=dialog]');
  if (!dlg) return JSON.stringify({dialog: false, tiles: []});
  const nodes = Array.prototype.slice.call(dlg.querySelectorAll('button,[role=button],[role=listitem],[role=option]'));
  const lab = (e) => (((e.getAttribute && e.getAttribute('aria-label')) || '') + ' ' + (e.textContent || '')).replace(/\s+/g, ' ').trim();
  const tiles = [];
  for (const el of nodes) {
    const r = el.getBoundingClientRect();
    if (r.width < 60 || r.height < 40) continue;      // buttons, not tiles
    const l = lab(el);
    if (!l) continue;
    if (/^(go live|cancel|close|back|screens?|applications?)$/i.test(l)) continue;
    tiles.push(l);
  }
  return JSON.stringify({dialog: true, tiles: tiles});
})()
"""


# --------------------------------------------------------------------------
# Tile disambiguation (pure, unit-tested)
# --------------------------------------------------------------------------
def browser_identity(label: str):
    """Longest known browser phrase contained in `label`, or None.

    All sooka windows share the page title "Watch online Live Sports, sooka",
    so the browser suffix is the only discriminator -- and a naive
    `'chrome' in label` matches both Chrome Beta and Google Chrome, which is
    how two streams ended up sharing one window.
    """
    low = (label or "").lower()
    hits = [b for b in KNOWN_BROWSERS if b in low]
    return max(hits, key=len) if hits else None


def choose_tile(tiles, browser: str):
    """Return (index, reason). index is None when we must NOT guess."""
    want = browser_identity(browser)
    if not want:
        return None, (
            f"'{browser}' is not an unambiguous browser name; "
            f"use one of: {', '.join(KNOWN_BROWSERS)}"
        )
    matches = [i for i, t in enumerate(tiles) if browser_identity(t) == want]
    if not matches:
        seen = sorted({browser_identity(t) or "?" for t in tiles})
        return None, f"no tile for '{want}' (picker shows: {', '.join(seen) or 'nothing'})"
    if len(matches) > 1:
        sooka = [i for i in matches if "watch online live sports" in tiles[i].lower()]
        if len(sooka) == 1:
            return sooka[0], f"matched '{want}' + sooka page title"
        return None, f"{len(matches)} tiles match '{want}' -- refusing to guess: {[tiles[i] for i in matches]}"
    return matches[0], f"matched '{want}'"


# --------------------------------------------------------------------------
# Flow
# --------------------------------------------------------------------------
class StepResult(dict):
    @property
    def ok(self):
        return bool(self.get("ok"))


class StageFlow:
    def __init__(self, cdp: CDP, cfg, topic="1", verbose=False):
        self.cdp = cdp
        self.cfg = cfg
        self.topic = topic
        self.verbose = verbose
        self.steps = []

    def state(self):
        st = self.cdp.evaluate_json(STATE_JS)
        if not isinstance(st, dict):
            raise CDPError(f"state probe returned {st!r}")
        return st

    def record(self, name, ok, **extra):
        step = StepResult(step=name, ok=bool(ok), **extra)
        self.steps.append(step)
        detail = " ".join(f"{k}={v!r}" for k, v in extra.items() if k != "buttons")
        log(f"  [{'ok ' if ok else 'FAIL'}] {name} {detail}")
        return step

    def wait_state(self, key, timeout=20.0, want=True, desc=None):
        got = self.cdp.wait_for(
            lambda: (self.state().get(key) == want) or None,
            timeout=timeout,
            desc=desc or key,
        )
        return bool(got)

    # -- steps ------------------------------------------------------------
    def ensure_channel(self):
        st = self.state()
        if st.get("channel") == self.cfg["channel"]:
            return self.record("channel", True, channel=st.get("channel"))
        url = f"https://discord.com/channels/{GUILD_ID}/{self.cfg['channel']}"
        self.cdp.navigate(url)
        ok = self.cdp.wait_for(
            lambda: (self.state().get("channel") == self.cfg["channel"]) or None,
            timeout=30, desc="channel nav",
        )
        return self.record("channel", bool(ok), channel=self.state().get("channel"))

    def ensure_undeafened(self):
        """Root cause #2: while deafened, every share click opens the
        'Server Deafened' modal instead of the picker."""
        st = self.state()
        if not st.get("deafened") and not st.get("deaf_modal"):
            return self.record("undeafen", True, needed=False)
        res = self.cdp.click(by_label(SELECTORS["deafen_on"], max_len=40), trusted_only=False)
        if not res["ok"]:
            # keyboard fallback: Ctrl+Shift+D toggles deafen
            self.cdp.key("D", "KeyD", 0x44, modifiers=MOD_CTRL | MOD_SHIFT)
        ok = self.wait_state("deafened", timeout=8, want=False)
        return self.record("undeafen", ok, needed=True, click=res.get("reason"))

    def ensure_in_stage(self):
        st = self.state()
        if st.get("share_button") or st.get("streaming") or st.get("topic_modal") or st.get("can_start_stage"):
            return self.record("join", True, already=True)
        # Joining is not activation-gated, so a synthetic click is fine here
        # (this is the `li -> a.click()` path already proven to work).
        res = self.cdp.js_click(by_href(self.cfg["channel"]))
        if not res["ok"]:
            res = self.cdp.click(by_label(SELECTORS["join_stage"]), trusted_only=False)
        ok = self.cdp.wait_for(
            lambda: (lambda s: s.get("can_start_stage") or s.get("topic_modal")
                     or s.get("share_button") or s.get("streaming") or None)(self.state()),
            timeout=25, desc="join stage",
        )
        return self.record("join", bool(ok), via=res.get("reason"))

    def ensure_stage_started(self):
        """Root cause #3 -- and the v1 logic bug.

        'Share Your Screen' does not exist until the stage is STARTED. v1
        clicked 'Continue without starting', which is the one branch that
        guarantees it never appears. We click 'Start Stage' instead.
        """
        st = self.state()
        if st.get("share_button") or st.get("streaming"):
            return self.record("start_stage", True, already=True)

        if st.get("topic_modal") and self.topic:
            try:
                field = self.cdp.find("true", selector="[role=dialog] input,[role=dialog] textarea")
                if field.get("count"):
                    self.cdp.click("true", selector="[role=dialog] input,[role=dialog] textarea",
                                   trusted_only=False, found=field)
                    self.cdp.insert_text(self.topic)
            except CDPError as exc:
                log(f"    topic field skipped: {exc}")

        res = self.cdp.click(by_label(SELECTORS["start_stage"], max_len=80))
        ok = self.wait_state("share_button", timeout=25)
        if not ok:
            st = self.state()
            return self.record("start_stage", False, click=res.get("reason"),
                               hover=res.get("hover"), covered=res.get("covered"),
                               dialog=st.get("dialog"))
        return self.record("start_stage", True, click=res.get("reason"), scale=res.get("scale"))

    def open_picker(self):
        res = self.cdp.click(by_label(SELECTORS["share"]))  # activation-gated: trusted only
        ok = self.wait_state("picker_open", timeout=20)
        return self.record("share_picker", ok, click=res.get("reason"),
                           hover=res.get("hover"), covered=res.get("covered"),
                           cover=res.get("cover_label"))

    def select_tile(self):
        """Root cause #5: tiles differ only by browser suffix."""
        probe = self.cdp.wait_for(
            lambda: (lambda d: d if isinstance(d, dict) and d.get("tiles") else None)(
                self.cdp.evaluate_json(TILE_JS)),
            timeout=15, desc="picker tiles",
        )
        tiles = (probe or {}).get("tiles", [])
        index, reason = choose_tile(tiles, self.cfg["browser"])
        if index is None:
            return self.record("tile", False, reason=reason, tiles=tiles)
        target = tiles[index]
        pred = (
            f"{LABEL_JS} === {json.dumps(target)} && !!el.closest('[role=dialog]') "
            "&& el.getBoundingClientRect().width >= 60"
        )
        res = self.cdp.click(pred, selector="[role=dialog] button,[role=dialog] [role=button],"
                                            "[role=dialog] [role=listitem],[role=dialog] [role=option]")
        return self.record("tile", res["ok"], tile=target, reason=reason, click=res.get("reason"))

    def go_live(self):
        res = self.cdp.click(by_label(SELECTORS["golive"], in_dialog=True, max_len=40))
        if not res["ok"]:
            res = self.cdp.click(by_label(SELECTORS["golive"], max_len=40))
        ok = self.wait_state("streaming", timeout=25)
        return self.record("go_live", ok, click=res.get("reason"), hover=res.get("hover"),
                           covered=res.get("covered"))

    def run(self):
        for step in (self.ensure_channel, self.ensure_undeafened, self.ensure_in_stage,
                     self.ensure_stage_started, self.open_picker, self.select_tile, self.go_live):
            if not step().ok:
                return False
        return True


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------
def focus_client(port: int) -> dict:
    """Best-effort foreground. CDP input does not need focus, so a failure here
    is logged and ignored -- it only matters for the real-mouse fallback."""
    info = {"attempted": False}
    if os.name != "nt":
        return dict(info, skipped="not windows")
    import subprocess
    try:
        out = subprocess.check_output("netstat -ano", shell=True).decode("utf-8", "replace")
    except subprocess.SubprocessError as exc:
        return dict(info, error=repr(exc))
    pid = parse_netstat_pid(out, port)
    info["pid"] = pid
    if not pid:
        return dict(info, error=f"nothing LISTENING on 127.0.0.1:{port}")
    win = find_window_by_pid(pid)
    if not win:
        return dict(info, error=f"pid {pid} has no visible window")
    hwnd, left, top, title, width, iconic = win
    info.update(attempted=True, title=title, rect=(left, top, width), iconic=iconic)
    info["foreground"] = force_foreground(hwnd)
    return info


def run_one(stream_id: int, args) -> dict:
    cfg = STREAMS[stream_id]
    label = f"stream{stream_id} ({cfg['client']} :{cfg['port']} -> {cfg['browser']})"
    log(f"=== {label} ===")
    out = {"stream": stream_id, "ok": False, **cfg}

    focus = focus_client(cfg["port"])
    out["focus"] = focus
    if focus.get("error"):
        log(f"  focus: {focus['error']} (ignored -- CDP input does not need focus)")

    try:
        cdp = CDP.connect(cfg["port"], GUILD_ID, cfg["channel"], logger=log)
    except CDPError as exc:
        log(f"  CONNECT FAILED: {exc}")
        out["error"] = str(exc)
        return out

    try:
        flow = StageFlow(cdp, cfg, topic=args.topic, verbose=args.verbose)
        st = flow.state()
        log(f"  page: {st.get('url')}")
        log("  state: " + json.dumps({k: v for k, v in st.items()
                                      if k not in ("buttons", "url", "dialog")}))
        out["state_before"] = st

        if args.dump_buttons:
            log("  buttons:")
            for b in st.get("buttons", []):
                log(f"    - {b}")
        if args.diagnose:
            out["ok"] = True
            out["diagnose"] = True
            return out

        out["ok"] = flow.run()
        out["steps"] = flow.steps
        out["state_after"] = flow.state()
    except CDPError as exc:
        log(f"  CDP ERROR: {exc}")
        out["error"] = str(exc)
    finally:
        cdp.close()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="SookaStage stage + screenshare runner")
    ap.add_argument("--stream", type=int, choices=sorted(STREAMS), action="append",
                    help="stream number; repeatable")
    ap.add_argument("--all", action="store_true", help="run every configured stream")
    ap.add_argument("--topic", default="1", help="stage topic to type (default: 1)")
    ap.add_argument("--diagnose", action="store_true", help="report state, click nothing")
    ap.add_argument("--dump-buttons", action="store_true", help="print every button label")
    ap.add_argument("--json", dest="as_json", action="store_true", help="machine-readable summary")
    ap.add_argument("--verbose", action="store_true")
    # legacy positional form: sookastage_prod.py 9223 Brave
    ap.add_argument("legacy", nargs="*", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    streams = list(args.stream or [])
    if args.all:
        streams = sorted(STREAMS)
    if not streams and len(args.legacy) >= 1:
        port = int(args.legacy[0])
        streams = [n for n, c in STREAMS.items() if c["port"] == port]
        if not streams:
            print(f"no stream configured for port {port}", file=sys.stderr)
            return 2
        log(f"legacy invocation mapped port {port} -> stream {streams[0]}")
    if not streams:
        ap.print_help()
        return 2

    results = [run_one(n, args) for n in streams]
    ok = all(r.get("ok") for r in results)
    if args.as_json:
        print(json.dumps(results, indent=2, default=str))
    log("SUMMARY: " + ", ".join(
        f"stream{r['stream']}={'OK' if r.get('ok') else 'FAIL'}" for r in results))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
