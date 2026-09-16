
# SookaStage — Stage Automation Progress & Known Issues
Last updated: 2026-09-17 (Malaysia timezone)

## Architecture
Automation flows are split per Discord client (3 streamers):
| Stream | Discord client | CDP port | sooka browser | Stage channel ID |
|---|---|---|---|---|
| 1 | Discord (stable) | 9223 | Brave | 1477692113738137600 |
| 2 | Canary | 9225 | Chrome Beta | 1481358977584599283 |
| 3 | PTB | 9224 | Google Chrome | 1481359453759475876 |

Flow per client: launch w/ `--remote-debugging-port` → navigate stage channel (channel-ID is source of truth, not name — names are rewritten live by voice_renamer) → join stage (li → a DOM click works without focus) → "Start the Stage" (topic modal w/ prefill) → "Continue without starting" or confirm topic → **Share Your Screen** → tile select (sooka browser window) → "Go Live".

## Working (verified live)
- Streamer2 (Canary/9225) & Streamer3 (PTB/9224) — full end-to-end automation success, screenshare sooka browser live (panel text `Watch online Live Sports, sooka - Brave 1440p 60FPS`).
- Join stage via DOM `li a.click()` — no window focus needed.
- Undeafen shortcut `Ctrl+Shift+D`.
- Main (9223) completed FULL flow once (screenshare live verified visually) but is not stable across reruns — see issues.

## Root causes identified
1. **Old main build (app-1.0.9258) DevTools wedging** — HTTP `/json` endpoint sticks after a few WebSocket sessions; rect lookups via `Runtime.evaluate` die mid-flow. PTB/Canary builds (app-1.0.117x) unaffected. Fix path: single persistent ws session per script (Claude-verified approach), or upgrade main client (breaks saved-session? untested). Deep-link relaunch `Discord.exe --remote-debugging-port=9223 "discord://-/channels/GUILD_ID/CHANNEL_ID"` correctly restores stage view at launch.
2. **"Server Deafened" permission modal blocks share flow** — main client gets deafened (manual toggle / ctrl+shift+D caught mid-automation). Every share click while deafened spawns the modal instead of the picker. Fix: send `Ctrl+Shift+D` once (undeaften works via keyboard).
3. **Stage "Start the Stage" topic modal** — topic input + Start Stage button: button click at rect coordinates does not register on main build; clicking "Continue without starting" instead enters speaker mode reliably. Stage must be **STARTED** before the Share button exists — that is what made Stream1 look "not live on channel 1".
4. **Spanner: voice_renamer rewrites channel names live** — NEVER match stage by name; always use channel ID → API name resolution → `data-dnd-name` lookup (implemented; name hints are dead).
5. **Share picker tile selection** — all sooka browser windows share the same page title ("Watch online Live Sports…"), they only differ by browser suffix (Brave / Chrome / Chrome Beta). Tile must be matched against the target browser string; mis-clicks caused two streams sharing the same browser window (owner saw "same channel on all browsers").
6. **sooka PiP floating window** covers Discord clicks intermittently — PiP must be closed before click-chain.

## Current state as of this commit
- ch1 (1477692113738137600): stage started (topic "1"), STREAMER1 speaker in stage, **screen share NOT live** — the Share Your Screen picker never appears after the topic modal is dismissed; clicking Go Live button in voice panel opens nothing (suspected: needs stage view as main content + non-deafened state + picker coords). Owner will retest tomorrow.
- ch2 + ch3: LIVE via screenshare automation.
- Ghost cmd consoles + one-shot schtasks cleaned; only operational tasks remain (SookaBootFix, SookaRenamer, SookCDP, SookDLaunch, SookTopWatch).
- Topmost watchdog keeps sooka browser above Codex overlay (root cause of "dark tile" was Codex ComputerUse fullscreen overlay pid — keep browsers TOPMOST or close ChatGPT desktop agent while streaming).

## Next steps (tomorrow)
1. Retain flow on fresh restart; first click topic "1" → "Start Stage" using a REAL mouse click inside the visible window (not scheduled task context — task context may not own foreground per Windows foreground-lock).
2. Add `AttachThreadInput` helper before `SetForegroundWindow` from schtask context (flag: Claude CTRL code review recommended this).
3. Share picker tile selection: match by browser window rect (top-left / top-right / bottom-left) instead of title strings.
4. Wrap the full chain into `sookastage_prod.py` + "STREAM ALL 3" button in SookaStream Manager GUI (manager repo); add stage watchdog (re-run flow if a stream drops).
5. Update the launcher bat to use the per-channel deep-link launch so stage view always opens first.
