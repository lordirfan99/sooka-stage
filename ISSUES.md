# SookaStage — Issues Checklist (2026-09-17 evening)

## FIXED / PROVEN
- **Start Stage via API** ✅ — POST /api/v9/stage-instances {channel_id, topic:"1)", privacy_level:2} → 200 on all 3 channel IDs. Modal permanently bypassed.
- **User token extraction** ✅ — CDP Network.enable + Page.navigate; catch Authorization header. LS tokens are stale (401). Stored: PC `C:\Users\irfan\SookaStage\.user_token.json` (REDACTED).
- **Canary updater DB corruption** ✅ — root cause `installer.db` + missing `modules/` from `/s` (lowercase) silent install. Fix: real `/S` (uppercase NSIS switch) → modules populated (442MB), updater logs "Already up to date".
- **Subagent on PC** ✅ — OpenCode CLI 1.18.31, default model omen-alpha (custom provider with x-opencode-session header). Smoke tests passed. Skill saved: `pc-opencode-agent`.

## OPEN ISSUES (next session)
1. **Canary 1.0.1177 silent self-exit (2–7 min)** — reproduced 5×: with flags, bare, disable-gpu. No crash dump, no WER event, app exits itself. Last-act pattern = voice/RTC latency test. Suspect discord_media.node path (historical crash 0xc0000409 on 1.0.1165). Options: wait for 1.0.1178+, or stream-2 rides PTB-with-restart watchdog.
2. **Share flow not automated end-to-end yet** — stage API start works; the CDP Share-Your-Screen → tile-pick → Go-Live flow still needs the client running: relaunch with flags (`--force-renderer-accessibility --remote-debugging-port` + deep-link), then resume sookastage_prod.py on ch1/ch3.
3. **Subagent computer-use needs interactive session** — SSH-run opencode gets black screenshots. Launch via `schtasks /it` into owner's desktop session.
4. **voice_renamer + auto-heal schtasks** — still reference channel names; scheduled rework to ID-only and scheduled shutdown of browser auto-heal.

## Channel IDs (immutable source of truth)
- ch1: 1477692113738137600 (Stream 1, main/9223, topic "1)")
- ch2: 1481358977584599283 (Stream 2, canary/9225, topic "2)")
- ch3: 1481359453759475876 (Stream 3, PTB/9224, topic "3)")
