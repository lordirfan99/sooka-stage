"""Preflight / triage for the SookaStage automation.

Run this BEFORE debugging anything else. It answers, per Discord client:

  * is the DevTools port alive, or has /json wedged (root cause #1)?
  * which channel is the client actually on?
  * is it deafened (root cause #2)?
  * has the stage been started -- i.e. does "Share Your Screen" exist at all
    (root cause #3)?
  * which browser tiles does the share picker offer, and are they ambiguous
    (root cause #5)?
  * does a CDP coordinate click actually land on the button we aim at, and at
    which coordinate scale?

Usage:
  python sooka_diag.py                 # all three clients, read-only
  python sooka_diag.py --stream 1      # one client
  python sooka_diag.py --buttons       # plus every button label
  python sooka_diag.py --calibrate     # hit-test the coordinate space
  python sooka_diag.py --json          # machine-readable

--calibrate moves the mouse pointer inside the Discord window but never
presses a button, so it is safe to run mid-stream.
"""
from __future__ import annotations

import argparse
import json
import sys

from sooka_cdp import CDP, CDPError, http_json
from sookastage_prod import (
    GUILD_ID,
    SELECTORS,
    STATE_JS,
    STREAMS,
    TILE_JS,
    by_label,
    choose_tile,
)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

VERDICTS = [
    ("port_dead", "No usable DevTools session. Either the client is not running with\n             --remote-debugging-port, or /json has wedged -- the message above says which."),
    ("wrong_channel", "Client is not on its stage channel. The runner will deep-link nav."),
    ("deafened", "Client is DEAFENED. Every share click will open the 'Server Deafened' modal."),
    ("stage_not_started", "Stage is NOT started, so 'Share Your Screen' does not exist yet."),
    ("tiles_ambiguous", "Share picker tiles cannot be told apart -- do not let it guess."),
    ("click_blind", "CDP coordinate clicks do not land on their target."),
]


def calibrate(cdp: CDP, state):
    """Find which coordinate scale makes a CDP mouseMoved land on its target.

    getBoundingClientRect() and Input.dispatchMouseEvent agree on modern
    Chromium. On the older main build they can disagree once Discord's zoom
    level is not 100%, which makes every rect click miss silently. ':hover'
    only responds to trusted input, so this is a real measurement.
    """
    for name, pattern in (("share", SELECTORS["share"]),
                          ("start stage", SELECTORS["start_stage"]),
                          ("stop streaming", SELECTORS["stop"])):
        found = cdp.find(by_label(pattern, max_len=40))
        if not found.get("count"):
            continue
        # hit-test only: we move the pointer, we never press a button
        outcome = {"anchor": name, "label": found.get("label"), "zoom": found.get("zoom"),
                   "dpr": (found.get("viewport") or {}).get("dpr"),
                   "covered": found.get("covered"), "cover_label": found.get("cover_label"),
                   "scale": None, "hover": None}
        for scale in cdp.scale_ladder(found):
            cdp.dispatch_mouse("mouseMoved", found["rect"]["cx"] * scale, found["rect"]["cy"] * scale)
            hover = cdp.evaluate("(() => { const a=document.querySelectorAll(':hover');"
                                 "const h=a.length?a[a.length-1]:null; const t=window.__sookaTarget;"
                                 "if(!t) return 'no-target'; if(!h) return 'none';"
                                 "return (h===t||t.contains(h)||h.contains(t))?'hit':'miss'; })()")
            outcome["hover"] = hover
            if hover == "hit":
                outcome["scale"] = scale
                break
        return outcome
    return {"anchor": None, "note": "no anchor button on screen to calibrate against"}


def check_stream(stream_id: int, args) -> dict:
    cfg = STREAMS[stream_id]
    out = {"stream": stream_id, "flags": [], **cfg}
    print(f"\n=== stream{stream_id}  {cfg['client']}  port {cfg['port']}  -> {cfg['browser']} ===")

    try:
        targets = http_json(cfg["port"], "/json", tries=2)
        out["targets"] = len(targets)
        print(f"  /json        : OK ({len(targets)} targets)")
    except CDPError as exc:
        out["flags"].append("port_dead")
        out["error"] = str(exc)
        print(f"  /json        : DEAD -- {exc}")
        return out

    try:
        cdp = CDP.connect(cfg["port"], GUILD_ID, cfg["channel"])
    except CDPError as exc:
        out["flags"].append("port_dead")
        out["error"] = str(exc)
        print(f"  websocket    : FAILED -- {exc}")
        return out

    try:
        st = cdp.evaluate_json(STATE_JS)
        if not isinstance(st, dict):
            out["error"] = f"state probe returned {st!r}"
            print("  state        : UNREADABLE")
            return out
        out["state"] = st

        on_channel = st.get("channel") == cfg["channel"]
        print(f"  channel      : {st.get('channel')} {'(correct)' if on_channel else '(WRONG -- expected ' + cfg['channel'] + ')'}")
        if not on_channel:
            out["flags"].append("wrong_channel")

        print(f"  deafened     : {st.get('deafened')}   server-deaf modal: {st.get('deaf_modal')}")
        if st.get("deafened") or st.get("deaf_modal"):
            out["flags"].append("deafened")

        started = bool(st.get("share_button") or st.get("streaming"))
        print(f"  stage started: {started}  (share button: {st.get('share_button')}, streaming: {st.get('streaming')})")
        if not started:
            out["flags"].append("stage_not_started")
        print(f"  sooka panel  : {st.get('sooka_panel')}")
        if st.get("dialog"):
            print(f"  open dialog  : {st['dialog'][:120]}")

        if st.get("picker_open"):
            tiles = (cdp.evaluate_json(TILE_JS) or {}).get("tiles", [])
            index, reason = choose_tile(tiles, cfg["browser"])
            out["tiles"] = tiles
            out["tile_choice"] = {"index": index, "reason": reason}
            print(f"  picker tiles : {len(tiles)} -> {reason}")
            if index is None:
                out["flags"].append("tiles_ambiguous")

        if args.buttons:
            print("  buttons:")
            for b in st.get("buttons", []):
                print(f"    - {b}")

        if args.calibrate:
            cal = calibrate(cdp, st)
            out["calibration"] = cal
            if cal.get("anchor"):
                verdict = f"scale={cal['scale']}" if cal.get("scale") else f"NO HIT ({cal.get('hover')})"
                print(f"  click test   : anchor '{cal['anchor']}' zoom={cal.get('zoom')} "
                      f"dpr={cal.get('dpr')} covered={cal.get('covered')} -> {verdict}")
                if not cal.get("scale"):
                    out["flags"].append("click_blind")
            else:
                print(f"  click test   : {cal.get('note')}")
    except CDPError as exc:
        out["error"] = str(exc)
        print(f"  ERROR        : {exc}")
    finally:
        cdp.close()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="SookaStage preflight diagnostics")
    ap.add_argument("--stream", type=int, choices=sorted(STREAMS), action="append")
    ap.add_argument("--buttons", action="store_true", help="dump every button label")
    ap.add_argument("--calibrate", action="store_true", help="hit-test the coordinate space")
    ap.add_argument("--json", dest="as_json", action="store_true")
    args = ap.parse_args(argv)

    streams = args.stream or sorted(STREAMS)
    results = [check_stream(n, args) for n in streams]

    print("\n=== VERDICT ===")
    clean = True
    for r in results:
        if not r["flags"]:
            print(f"  stream{r['stream']}: nothing blocking")
            continue
        clean = False
        for flag in r["flags"]:
            explain = dict(VERDICTS).get(flag, flag)
            print(f"  stream{r['stream']}: {flag} -- {explain}")
    if args.as_json:
        print(json.dumps(results, indent=2, default=str))
    return 0 if clean else 1


if __name__ == "__main__":
    sys.exit(main())
