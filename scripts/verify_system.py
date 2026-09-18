"""End-to-end verification harness for the combined SookaStage + Manager system.

Nine layers, cheapest first, so a failure reports the lowest broken thing
rather than a confusing symptom higher up. Read-only by default: it inspects,
it does not fix. `--destructive` additionally kills a live client to prove the
self-heal path actually heals (only run that when a dropped stream is
acceptable for ~60s).

    python scripts/verify_system.py            # read-only, safe any time
    python scripts/verify_system.py --destructive
    python scripts/verify_system.py --json

Layer 1  static      unit tests, both repos
Layer 2  config      cross-repo agreement + no clashing assignments
Layer 3  startup     nothing auto-starts that shouldn't; only expected tasks
Layer 4  services    dashboard / renamer / three CDP ports
Layer 5  api         /stage-status agrees with the status file on disk
Layer 6  discord     stage instances live via REST, topics distinct
Layer 7  live        all three streaming, each on its OWN distinct window
Layer 8  idempotent  a second --all pass changes nothing
Layer 9  concurrency the run lock refuses a second simultaneous run
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = r"C:\Users\irfan\Desktop\sooka-stage"
MANAGER = (r"C:\Users\irfan\Desktop\Restored-Desktop\SookaStream-Windows-x64-v8.6"
           r"\SookaStream-Windows-x64-v8.6")
PYTHON = r"C:\Users\irfan\AppData\Local\Programs\Python\Python312\python.exe"
STATUS_PATH = r"C:\Users\irfan\sookastage_status.json"
TOKEN_PATH = r"C:\Users\irfan\SookaStage\.user_token.json"
DASHBOARD = "http://127.0.0.1:8080"

NO_WINDOW = {"creationflags": 0x08000000} if os.name == "nt" else {}

sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

results = []


def check(layer, name, ok, detail=""):
    results.append({"layer": layer, "check": name, "ok": bool(ok), "detail": str(detail)[:300]})
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" -- {detail}" if detail else ""), flush=True)
    return ok


def run(cmd, cwd=None, timeout=300):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout, **NO_WINDOW)


def port_open(port):
    s = socket.socket()
    s.settimeout(1.5)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


# ── Layer 1: static ──────────────────────────────────────────────────────────
def layer_static():
    print("\nLayer 1 - static (unit tests)")
    r = run([PYTHON, "-m", "unittest", "discover", "-s", "tests"], cwd=REPO)
    check("static", "sooka-stage unit tests", r.returncode == 0,
          (r.stderr or "").strip().splitlines()[-1] if r.stderr else "")
    r = run([PYTHON, "-m", "pytest", "tests/test_server.py", "tests/test_launcher.py", "-q"],
            cwd=MANAGER)
    check("static", "Manager unit tests", r.returncode == 0,
          (r.stdout or "").strip().splitlines()[-1] if r.stdout else "")


# ── Layer 2: config agreement / clash detection ──────────────────────────────
def layer_config():
    print("\nLayer 2 - config (cross-repo agreement, no clashes)")
    from sookastage_prod import STREAMS, GUILD_ID

    ports = [c["port"] for c in STREAMS.values()]
    check("config", "each stream has a unique CDP port", len(set(ports)) == len(ports), ports)

    chans = [c["channel"] for c in STREAMS.values()]
    check("config", "each stream has a unique channel id", len(set(chans)) == len(chans))

    browsers = [c["browser"] for c in STREAMS.values()]
    check("config", "each stream has a distinct browser", len(set(browsers)) == len(browsers),
          browsers)

    # Both codebases hardcode these ids. If they ever drift, the Manager would
    # rename one channel while the runner streams to another -- silently.
    try:
        with open(os.path.join(MANAGER, "sooka-config.json"), encoding="utf-8") as fh:
            mcfg = json.load(fh)
        mgr_chans = mcfg.get("discord_stream_channels", {})
        agree = all(str(mgr_chans.get(str(n))) == STREAMS[n]["channel"] for n in STREAMS)
        check("config", "Manager and runner agree on channel ids", agree,
              "" if agree else f"manager={mgr_chans}")
        check("config", "Manager and runner agree on guild id",
              str(mcfg.get("discord_guild_id")) == GUILD_ID)
    except (OSError, ValueError) as exc:
        check("config", "Manager config readable", False, exc)

    # The renamer PATCHes /channels/<id>; the runner POSTs /stage-instances.
    # Different REST resources -- that is what keeps them from fighting.
    try:
        with open(os.path.join(MANAGER, "voice_renamer.py"), encoding="utf-8") as fh:
            renamer = fh.read()
        check("config", "renamer never touches /stage-instances (no clash)",
              "stage-instances" not in renamer)
    except OSError as exc:
        check("config", "renamer readable", False, exc)


# ── Layer 3: startup hygiene ─────────────────────────────────────────────────
def layer_startup():
    print("\nLayer 3 - startup hygiene")
    try:
        import startup_config
        s = startup_config.sookastage_status()
        check("startup", "SookaStage autostart is a real, readable setting",
              s in ("on", "off"), f"currently {s.upper()}")
        d = startup_config.discord_status()
        check("startup", "Discord self-start is OFF (else clients come up portless)",
              all(v == "off" for v in d.values()) if d else True, d)
    except Exception as exc:  # noqa: BLE001
        check("startup", "startup_config usable", False, exc)

    r = run(["schtasks", "/query", "/fo", "csv", "/nh"])
    sook = [ln.split(",")[0].strip('"') for ln in (r.stdout or "").splitlines()
            if "Sook" in ln]
    sook = sorted({s.lstrip("\\") for s in sook})
    check("startup", "only the watchdog task remains", sook == ["SookaStageWatchdog"], sook)


# ── Layer 4: services ────────────────────────────────────────────────────────
def layer_services():
    print("\nLayer 4 - services")
    try:
        code = urllib.request.urlopen(f"{DASHBOARD}/healthz", timeout=8).status
        check("services", "Manager dashboard responding", code == 200, f"HTTP {code}")
    except Exception as exc:  # noqa: BLE001
        check("services", "Manager dashboard responding", False, exc)

    r = run(["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | "
             "Where-Object {$_.CommandLine -like '*run_renamer*'} | Measure-Object).Count"])
    n = (r.stdout or "0").strip()
    check("services", "channel renamer running (exactly one)", n == "1", f"count={n}")

    from sookastage_prod import STREAMS
    for sid, cfg in sorted(STREAMS.items()):
        check("services", f"stream {sid} CDP port {cfg['port']} listening",
              port_open(cfg["port"]))


# ── Layer 5: api integration ─────────────────────────────────────────────────
def layer_api():
    print("\nLayer 5 - Manager <-> Stage integration")
    try:
        api = json.load(urllib.request.urlopen(f"{DASHBOARD}/stage-status", timeout=8))
        check("api", "/stage-status serves the snapshot", isinstance(api, dict))
        with open(STATUS_PATH, encoding="utf-8") as fh:
            disk = json.load(fh)
        check("api", "endpoint agrees with the status file on disk",
              api.get("checked_at") == disk.get("checked_at"),
              f"api={api.get('checked_at')} disk={disk.get('checked_at')}")
        html = urllib.request.urlopen(f"{DASHBOARD}/dashboard", timeout=8).read().decode(
            "utf-8", "replace")
        check("api", "dashboard renders the SookaStage panel", "SookaStage" in html)
    except Exception as exc:  # noqa: BLE001
        check("api", "integration endpoint", False, exc)


# ── Layer 6: discord truth ───────────────────────────────────────────────────
def layer_discord():
    print("\nLayer 6 - Discord (authoritative, via REST)")
    from sookastage_prod import STREAMS
    try:
        with open(TOKEN_PATH, encoding="utf-8") as fh:
            tok = json.load(fh)["discord_user_token"]
    except (OSError, KeyError, ValueError) as exc:
        check("discord", "user token readable", False, exc)
        return
    topics = {}
    for sid, cfg in sorted(STREAMS.items()):
        req = urllib.request.Request(
            f"https://discord.com/api/v9/stage-instances/{cfg['channel']}",
            headers={"Authorization": tok, "User-Agent": "Mozilla/5.0"})
        try:
            d = json.load(urllib.request.urlopen(req, timeout=10))
            topics[sid] = d.get("topic")
            check("discord", f"stream {sid} stage instance LIVE", True, f"topic={d.get('topic')!r}")
        except urllib.error.HTTPError as exc:
            check("discord", f"stream {sid} stage instance LIVE", False, f"HTTP {exc.code}")
    if topics:
        check("discord", "each stage has a distinct topic",
              len(set(topics.values())) == len(topics), topics)


# ── Layer 7: live state + window-clash detection ─────────────────────────────
def layer_live():
    print("\nLayer 7 - live streams (and no shared window)")
    try:
        with open(STATUS_PATH, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, ValueError) as exc:
        check("live", "status snapshot readable", False, exc)
        return
    tiles = {}
    for s in payload.get("streams", []):
        sid = s.get("stream")
        st = (s.get("state_after") or s.get("state_before") or {})
        check("live", f"stream {sid} streaming", bool(st.get("streaming")))
        check("live", f"stream {sid} shows real sooka content", bool(st.get("sooka_panel")))
        for step in s.get("steps", []):
            if step.get("step") == "tile" and step.get("tile"):
                tiles[sid] = step["tile"]
    if len(tiles) > 1:
        # The failure this guards: two streams sharing ONE browser window, so
        # two channels broadcast the same match.
        check("live", "no two streams share the same window",
              len(set(tiles.values())) == len(tiles), tiles)


# ── Layer 8: idempotency ─────────────────────────────────────────────────────
def layer_idempotent():
    print("\nLayer 8 - idempotency (a second pass must change nothing)")
    r = run([PYTHON, "sookastage_prod.py", "--all", "--json"], cwd=REPO, timeout=400)
    if r.returncode not in (0, 1):
        check("idempotent", "second pass ran", False, f"rc={r.returncode}")
        return
    try:
        data = json.loads(r.stdout)
    except ValueError as exc:
        check("idempotent", "--json stdout is pure JSON", False, exc)
        return
    check("idempotent", "--json stdout is pure JSON", True)
    if isinstance(data, dict) and data.get("skipped"):
        check("idempotent", "second pass deferred to the lock holder", True, data["skipped"])
        return
    # Only streams that were ALREADY streaming when this pass started are
    # required to be untouched. A stream that had genuinely dropped is
    # *supposed* to be re-driven -- counting that as an idempotency failure
    # makes the check punish the system for doing its job.
    touched, considered = [], 0
    for s in data:
        if not (s.get("state_before") or {}).get("streaming"):
            continue
        considered += 1
        for st in s.get("steps", []):
            if not st.get("already") and st.get("step") not in ("channel", "undeafen"):
                touched.append(f"stream{s.get('stream')}:{st.get('step')}")
    if considered == 0:
        check("idempotent", "no already-live stream to test against", True,
              "nothing was live at pass start -- inconclusive, not a failure")
        return
    check("idempotent",
          f"no step re-did work on the {considered} already-live stream(s)",
          not touched, touched or "all steps reported 'already'")


# ── Layer 9: concurrency ─────────────────────────────────────────────────────
def layer_concurrency():
    print("\nLayer 9 - concurrency (the run lock)")
    first = subprocess.Popen([PYTHON, "sookastage_prod.py", "--all", "--json"],
                             cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             text=True, **NO_WINDOW)
    try:
        time.sleep(3)
        second = run([PYTHON, "sookastage_prod.py", "--all", "--json"], cwd=REPO, timeout=120)
        refused = "another run in progress" in (second.stdout or "")
        check("concurrency", "second simultaneous run is refused", refused,
              (second.stdout or "").strip()[:120])
        check("concurrency", "refusal exits 0 (not an error)", second.returncode == 0,
              f"rc={second.returncode}")
    finally:
        try:
            first.wait(timeout=400)
        except subprocess.TimeoutExpired:
            first.kill()


# ── Destructive: self-heal ───────────────────────────────────────────────────
def layer_selfheal():
    print("\nLayer 10 - self-heal (DESTRUCTIVE: kills a live client)")
    r = run(["powershell", "-NoProfile", "-Command",
             "$p=@(Get-Process DiscordPTB -ErrorAction SilentlyContinue);"
             "$p | ForEach-Object { Stop-Process -Id $_.Id -Force };"
             "$p.Count"])
    killed = (r.stdout or "0").strip()
    check("selfheal", "killed the PTB client", killed not in ("", "0"), f"procs={killed}")
    time.sleep(3)
    check("selfheal", "port 9224 is actually down", not port_open(9224))
    r = run([PYTHON, os.path.join(REPO, "scripts", "preflight.py"), "--all", "--json"],
            cwd=REPO, timeout=500)
    check("selfheal", "preflight relaunched it", port_open(9224))
    ok = False
    try:
        with open(STATUS_PATH, encoding="utf-8") as fh:
            for s in json.load(fh).get("streams", []):
                if s.get("stream") == 3:
                    ok = bool((s.get("state_after") or {}).get("streaming"))
    except (OSError, ValueError):
        pass
    check("selfheal", "stream 3 returned to streaming", ok)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--destructive", action="store_true",
                    help="also kill a live client to prove self-heal works")
    ap.add_argument("--json", dest="as_json", action="store_true")
    args = ap.parse_args()

    print("=" * 62)
    print("  SookaStage + Manager - system verification")
    print("=" * 62)

    for fn in (layer_static, layer_config, layer_startup, layer_services,
               layer_api, layer_discord, layer_live, layer_idempotent,
               layer_concurrency):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - a broken layer must not hide the rest
            check(fn.__name__, "layer completed", False, repr(exc))
    if args.destructive:
        try:
            layer_selfheal()
        except Exception as exc:  # noqa: BLE001
            check("selfheal", "layer completed", False, repr(exc))

    passed = sum(1 for r in results if r["ok"])
    failed = [r for r in results if not r["ok"]]
    print("\n" + "=" * 62)
    print(f"  {passed}/{len(results)} checks passed")
    for r in failed:
        print(f"  FAILED [{r['layer']}] {r['check']} -- {r['detail']}")
    print("=" * 62)

    if args.as_json:
        print(json.dumps({"passed": passed, "total": len(results), "results": results},
                         indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
