# Hermes Operating Guide — SookaStage

**Audience:** Hermes (the agent/operator that runs these scripts on the Windows
box), and any human doing the same job. "Hermes" is not referenced anywhere in
the code — it is the operator role, not a component.

**Companion doc:** [`HERMES_PLAN.md`](HERMES_PLAN.md) — the ordered plan of work.
**Status log:** [`SOOKASTAGE_PROGRESS.md`](SOOKASTAGE_PROGRESS.md).

---

## Ringkasan (30 saat)

Runner lama **tak pernah klik apa-apa**. Dua bug:

1. `clipped_click` parse JSON dua kali → `TypeError` → ditelan oleh `except` →
   `return None`. Setiap klik jadi no-op senyap.
2. Langkah pertama klik **"Continue without starting"** — itulah cabang yang
   memastikan stage **tidak** start. Butang "Share Your Screen" cuma wujud
   kalau stage **sudah** start. Sebab itu ch1 nampak "stage ada, share takde".

Sekarang: `sooka_diag.py` untuk periksa dulu, `sookastage_prod.py` untuk jalan,
dan setiap klik disahkan (hit-test) sebelum ditekan.

---

## 1. First move, always

Never debug blind. Run the preflight and read the VERDICT block:

```powershell
python sooka_diag.py                 # all 3 clients, read-only
python sooka_diag.py --stream 1 --calibrate --buttons
```

It tells you, per client, which of the six known blockers is active. Only then
touch the runner:

```powershell
python sookastage_prod.py --stream 1            # one streamer
python sookastage_prod.py --all                 # all three
python sookastage_prod.py --stream 1 --diagnose # state only, clicks nothing
```

Exit code is `0` only when every requested stream reached "Stop Streaming".
Scheduled tasks and the Manager GUI can branch on that.

---

## 2. How this automation actually works

Each Discord client runs with `--remote-debugging-port`. We attach one
persistent CDP WebSocket and drive the renderer directly.

```
Discord.exe --remote-debugging-port=9223
        │
        ├── http://127.0.0.1:9223/json      ← target list (call ONCE per run)
        └── ws://…/devtools/page/<id>       ← one persistent session
                 ├── Runtime.evaluate        (read DOM state, find rects)
                 └── Input.dispatchMouseEvent(trusted clicks at viewport px)
```

Two consequences worth internalising:

* **Window focus is not required** for CDP input. The old "make it foreground
  first" dance is only needed for the real-mouse fallback. `focus_client()`
  still tries, but a failure there is logged and ignored.
* **Overlays do not block CDP clicks.** The sooka PiP window, the Codex
  ComputerUse overlay and the topmost watchdog are irrelevant to this path.
  They only ever mattered for the `pyautogui` approach in `main40.py`.

---

## 3. The rule that explains most "the click did nothing"

> **Synthetic JS clicks do not grant user activation. CDP input does.**

`el.click()` and `dispatchEvent(new MouseEvent(...))` produce **untrusted**
events. Anything the browser gates behind a user gesture — screen capture
being the obvious one — will accept the event and then quietly do nothing.

| Action | Gated? | Allowed method |
|---|---|---|
| Navigate / open a channel | no | JS click fine |
| Join stage (`li → a`) | no | JS click fine (already proven) |
| Dismiss a modal | no | JS click fine |
| **Start Stage** | treat as gated | `Input.dispatchMouseEvent` |
| **Share Your Screen** | **yes** | `Input.dispatchMouseEvent` only |
| **Go Live** | **yes** | `Input.dispatchMouseEvent` only |

This is why joining always worked while share never did, and why "just use
`el.click()` as a fallback" is the wrong instinct for the last three rows.
`CDP.click(..., trusted_only=True)` (the default) refuses to fall back.

---

## 4. Verified clicks — no more blind coordinates

`CDP.click()` does not fire and hope. Per click:

1. `find()` locates the element, checks it is visible, records its rect, its
   cumulative CSS `zoom`, and whether `document.elementFromPoint()` at the
   centre returns something *else* (i.e. it is **covered**).
2. Dispatch `mouseMoved` at the candidate coordinate.
3. Ask the page `document.querySelectorAll(':hover')`. **`:hover` only responds
   to trusted input**, so a hit is real proof the coordinate landed.
4. Only on a hit: `mousePressed` → `mouseReleased`.

If no coordinate hits, the click is reported as failed with the reason —
`covered-by:<what>` or `no-coordinate-hit (miss:DIV:…)` — instead of being
recorded as success.

**Why the coordinate ladder exists.** `getBoundingClientRect()` and
`Input.dispatchMouseEvent` agree on modern Chromium. On the older main build
(app-1.0.9258) they can disagree once Discord's zoom level is not 100%, so a
rect click lands somewhere else entirely. Rather than guess the build, the
engine tries `1.0`, `zoom`, `1/zoom`, `dpr`, `1/dpr` and keeps whichever one
hit (`self.scale`) for the rest of the session. This is the most likely
explanation for "button click at rect coordinates does not register on main
build" in the progress log — `--calibrate` measures it directly.

---

## 5. What was wrong with the v1 runner

| # | Bug | Effect |
|---|---|---|
| 1 | `ev()` parsed the JSON string, `clipped_click` parsed the **dict** again → `TypeError` → caught → `d = None` | **Every click a silent no-op.** The runner connected, logged, exited "done". |
| 2 | Steps 3 & 4 passed predicates that never referenced the element under test (`(()=>{…dlg…})()`) into `.find(x => PRED)` | `.find` returned the **first button on the page**; the tile and Go Live were never the target. |
| 3 | Step 1 clicked "Continue without starting" | Stage never starts → "Share Your Screen" never exists. **This is the ch1 symptom.** |
| 4 | `_recv()` ignored the WebSocket opcode | One PING or fragmented frame → JSON decode error → run dies. (`cdp_lib.py` handled this; the runner had regressed.) |
| 5 | `[t for t in j if …][0]` on the target list | `IndexError` whenever the client was on another view. |
| 6 | `netstat … findstr ":9223"` keeping the **last** match | Matched `19223`, remote `:9223` and `ESTABLISHED` rows → wrong pid. |
| 7 | `get_win_rect_by_pid` could return `None`, unpacked into 6 names on the next line | `TypeError` with no context. |
| 8 | `main()` had no `try/except`; `log()` swallowed every error | Scheduled-task runs failed invisibly. |
| 9 | Fixed `time.sleep(8/12/7)` between steps | Slow frame → click into nothing; fast frame → wasted 27s per run. |
| 10 | Tile matched by `browser.lower() in label` | `"chrome"` matches **both** Chrome Beta and Google Chrome → two streams on one window. |
| 11 | Bare `SetForegroundWindow` from a schtask | Returns success, does nothing (Windows foreground lock). |

All eleven are fixed. 1, 2, 3, 4, 6 and 10 have regression tests in
`tests/test_sooka.py`.

---

## 6. Failure catalogue

### A. `/json` did not answer — the DevTools wedge
*Symptom:* `sooka_diag.py` prints `/json : DEAD`. Only ever the main build
(app-1.0.9258); PTB/Canary (app-1.0.117x) are fine.
*Cause:* the HTTP endpoint sticks after several WebSocket sessions.
*Mitigation in code:* `http_json()` retries, and the runner calls it **once**
per process, then keeps a single persistent ws. Do **not** add code that
reconnects mid-flow.
*Fix on the box:* restart that client via the deep-link launcher, then re-run.
*Real fix:* upgrade the main client (untested against the saved session —
Phase 4 in the plan).

### B. "Server Deafened" modal eats the share click
*Symptom:* diag flags `deafened`; every share click opens a modal.
*Fix:* `ensure_undeafened()` clicks the Undeafen button (a button labelled
"Undeafen" exists **only while deafened**), falling back to `Ctrl+Shift+D`,
then verifies the state actually flipped.
*Note:* server-deafened by a moderator cannot be self-cleared — that needs a
human with permissions.

### C. Share button does not exist
*Symptom:* diag flags `stage_not_started`; `share_button: false`.
*Cause:* the stage is not started. **This is not a click problem.**
*Fix:* `ensure_stage_started()` types the topic and clicks **Start Stage**.
Never "Continue without starting" — that is the branch that caused this.
*If Start Stage itself will not register:* run `--calibrate`. Either it reports
`covered-by:<something>` (close that overlay) or `NO HIT` (coordinate space —
the ladder should already handle it; capture the output and escalate).

### D. Picker opens, wrong window gets shared
*Symptom:* owner sees the same stream on two channels.
*Cause:* all sooka windows share the title "Watch online Live Sports, sooka";
only the browser suffix differs, and `"chrome" in label` matches two of them.
*Fix:* `choose_tile()` resolves each tile to its **longest** known browser
phrase, so `google chrome` and `chrome beta` never collide. If two tiles still
resolve identically it **refuses to click** and reports both labels. A refusal
is the correct outcome — do not relax it into a guess.

### E. Go Live clicked, nothing happens
*Symptom:* `go_live` step fails, `streaming` stays false.
*Causes, in order of likelihood:* (1) something synthetic clicked it — see §3;
(2) the picker closed before the click; (3) tile never actually selected.
*Fix:* the runner verifies `picker_open` before selecting and `streaming` after
clicking, so the step now fails loudly at the right place instead of three
steps later.

### F. Channel matched by name
*Never do this.* `voice_renamer` rewrites channel names live (2 renames per
10 min). Channel **ID** is the only source of truth. IDs live in `STREAMS` in
`sookastage_prod.py`; the JS never matches on a name.

---

## 7. When Discord renames a button

Everything the flow matches on is in one dict:

```python
# sookastage_prod.py
SELECTORS = {
    "deafen_on":       r"^\s*undeafen",
    "start_stage":     r"start stage|start the stage",
    "continue_without": r"continue without starting",
    "share":           r"share your screen",
    "golive":          r"go live",
    "stop":            r"stop streaming",
    "join_stage":      r"join stage|join channel",
}
```

To repair a broken match:

```powershell
python sooka_diag.py --stream 1 --buttons     # every live button label
```

Copy the real label, update the regex, re-run. **One dict, one edit.** Do not
scatter new selectors through the flow.

---

## 8. Files

| File | Role |
|---|---|
| `sooka_cdp.py` | CDP transport + verified click engine + Windows helpers. Import this. |
| `sookastage_prod.py` | Config (`STREAMS`, `SELECTORS`), state machine, CLI. |
| `sooka_diag.py` | Preflight triage. Run first. |
| `tests/test_sooka.py` | Regression tests, run anywhere: `python -m unittest discover -s tests` |
| `cdp_lib.py`, `probe_panel.py`, `api_stage.py` | Older standalone probes, still fine for ad-hoc pokes. |
| `main40.py` | **Deprecated.** Hardcoded pixel coordinates; kept only as a record of the 16 Sep debug session. |

---

## 9. Rules — do not break these

1. **Channel ID only.** Names are rewritten live. Never hint by name.
2. **One `/json` call, one persistent ws, per process.** Reconnecting is what
   wedges the main build.
3. **Never JS-click Share or Go Live.** Untrusted events do not grant
   activation. Keep `trusted_only=True`.
4. **Never click "Continue without starting"** unless the stage is already
   running — it is the branch that removes the Share button.
5. **Never widen the tile match to a bare substring.** A refusal beats two
   streams on one window.
6. **Never report a step as passed without verifying the state changed.** Every
   step polls for its own postcondition.
7. **Never re-add fixed `time.sleep()` as flow control.** Use `wait_for`.

---

## 10. When escalating, capture this

```powershell
python sooka_diag.py --calibrate --buttons --json > diag.json
python sookastage_prod.py --stream 1 --json > run.json
```

Attach `diag.json`, `run.json` and the tail of `sookastage_prod.log`. The failing
step records `click`, `hover`, `covered` and `cover_label` — which is usually
enough to name the cause without touching the box again.
