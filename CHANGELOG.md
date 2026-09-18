# Changelog

Notable changes to SookaStage (the Discord stage/screenshare automation) and to
its integration with the SookaStream Manager.

Format follows [Keep a Changelog](https://keepachangelog.com/). Dates are UTC+8.

---

## [1.1.0] — 2026-09-18

The release that made the automation actually run unattended. Everything below
was found by running the full flow repeatedly against live clients rather than
once, and each fix is a root cause, not a retry.

### Fixed

- **Stages were being auto-ended by Discord seconds after creation.** The stage
  was started over REST *before* joining the voice channel, so it had zero
  speakers; Discord reaps an empty stage. `POST` returned `200`, the instance
  was `404` moments later, the client showed "Start Stage" again, and the
  account sat in **Audience** where "Share Your Screen" does not exist. The
  flow order is now `channel → join → undeafen → start_stage → speaker →
  picker → tile → go_live`.
- **The join step could never succeed.** It matched an `<a>` whose `href` ends
  in the channel ID, but Discord renders that row with `href=null` and only a
  `data-list-item-id="channels___<id>"`. Both forms are now accepted, still
  strictly by ID (never by name — the renamer rewrites names live).
- **Channel rows below the fold failed as `not-found`.** Hit-testing requires
  the element to intersect the viewport; the row sat at y=680 in a 519px-tall
  Canary window. Scrolled into view before clicking.
- **Discord auto-updates broke client launch two ways.** The `app-*` path was
  hardcoded (Canary moved 1.0.1177 → 1.0.1181, and an update strips the old
  directory's exe), and after updating Discord relaunches *itself* without
  `--remote-debugging-port` — being single-instance, a later launch silently
  hands off to that copy and drops the flags. The launcher now resolves the
  newest build containing the exe at run time, and stops a running-but-portless
  instance by PID first.
- **A wedged client could stall everything indefinitely.** PTB was seen
  listening on its port while `/json` never answered and its UI thread was
  hung; `focus_client`'s `AttachThreadInput` then blocked forever. One run held
  the single-run lock for 15+ minutes, so every watchdog pass behind it was
  skipped. Each stream now runs under `SOOKASTAGE_STREAM_TIMEOUT` (default
  180s), and `netstat` is bounded.
- **The watchdog healed share state but never a dead client.** If a client's
  *process* was gone there was nothing to drive, yet it reported healthy.
  `scripts/preflight.py` now ensures the watch windows and the Discord clients
  themselves are up first.
- **Two dishonest "success" branches.** `ensure_in_stage` inferred "already
  joined" from the absence of a Join button (there is no such button before the
  stage starts), and `ensure_speaker` reported success while stuck in the
  audience. Both now fail at the step that actually failed.
- **Brave's presence check matched any browser's window** (`path_hint=None`),
  reporting "Brave : already open" when no Brave window existed.
- **All three channels opened their stage with topic `1`**; unset `--topic` now
  means "this stream's own number".
- **The channel renamer had never been running.** Its task was disabled (it
  spawned a console window at every logon) and nothing replaced it.
- **The launcher restarted a healthy dashboard on every run**, because it
  matched `sooka_server.py` while the process runs `run_headless.py`.

### Added

- `Desktop\Start SookaStage.bat` — one-click start: Manager dashboard, channel
  renamer, three sooka.my watch windows, three Discord clients, then all three
  streams. Idempotent; a second run touches nothing.
- `Desktop\Sooka Startup Settings.bat` — ON/OFF control for what starts with
  Windows. Reads and writes the real mechanism (`HKCU` Run), never a saved
  preference, and reports failures instead of silently lying.
- `scripts/startup_config.py` — the underlying startup manager
  (`status` / `sookastage on|off` / `discord on|off`).
- `scripts/preflight.py` — shared "is everything that must be running actually
  running" layer, used by both the launcher and the watchdog.
- `scripts/watch_windows.py` — tags the Chrome Beta window title so the share
  picker can tell it apart from plain Chrome (stands in for Tampermonkey's
  "Set Browser Identity", which is not installed here).
- A single-run PID lock, so the 5-minute watchdog and a hand-run `--all` cannot
  drive the same clients at once. Stale locks (holder PID gone) are taken over.
- A status snapshot (`sookastage_status.json`) written after every run, and a
  `/stage-status` endpoint plus a **SookaStage** panel on the Manager dashboard
  that reads it — so the dashboard never opens its own CDP session.
- Handling for the "New Audio Device Detected" toast, which rendered over the
  share picker and ate the click.

### Changed

- `--json` keeps stdout as pure JSON (logs go to stderr), so callers can
  `json.load()` it directly.
- Headless wrappers use line-buffered logs; an unbuffered daemon log reads as
  empty and made a working renamer look dead.

### Security

- Removed `shell=True` from the runner (it routed `netstat` through `cmd.exe` —
  both a console-window source and an unnecessary injection shape).
- Console children (`netstat`, `tasklist`, `powershell`) now spawn with
  `CREATE_NO_WINDOW`. A console child allocates its *own* console when the
  parent has none, which is exactly the `pythonw` watchdog case — that was the
  visible-CMD-window problem, firing every 5 minutes.
- The startup control is deliberately a **local** desktop tool. The Manager
  dashboard is tunnelled publicly via ngrok, so it shows startup state
  read-only and exposes no control that rewrites Windows configuration.

### Removed

- Six obsolete scheduled tasks (`SookStage9223/9224/9225`, `SookaStageProd`,
  `SookaBootFix`, `SookaRenamer`) holding stale hardcoded paths — two versions
  out of date in Canary's case. `SookaStageWatchdog` is the only one left.

### Documentation

- `CLAUDE.md` rewritten around the current reality: flow order, the run lock,
  the one-click entry point, and the auto-update failure modes that replaced
  the old "known blocker".
- `ISSUES.md` gains F10–F17 with symptom → root cause → resolution → evidence.
