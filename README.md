# SookaStage (sooka-stage)

Automation untuk stream sooka → Discord stage channels, per-streamer (3 Discord clients).

| Stream | Discord client | CDP port | sooka browser | Stage channel ID |
|---|---|---|---|---|
| 1 | Discord (stable) | 9223 | Brave | `1477692113738137600` |
| 2 | Canary | 9225 | Chrome Beta | `1481358977584599283` |
| 3 | PTB | 9224 | Google Chrome | `1481359453759475876` |

## Start here

```powershell
python sooka_diag.py                    # triage all 3 clients, read-only
python sookastage_prod.py --stream 1    # run one streamer
python sookastage_prod.py --all         # run all three
```

- **[`HERMES_GUIDE.md`](HERMES_GUIDE.md)** — how it works, the failure catalogue, what never to do.
- **[`HERMES_PLAN.md`](HERMES_PLAN.md)** — the ordered plan to get all 3 streams green.
- **[`SOOKASTAGE_PROGRESS.md`](SOOKASTAGE_PROGRESS.md)** — status and history.

## Files
- `sooka_cdp.py` — CDP transport + verified click engine (hit-tests every click before pressing) + Windows helpers
- `sookastage_prod.py` — config (`STREAMS`, `SELECTORS`), stage state machine, CLI
- `sooka_diag.py` — preflight triage; run this before debugging anything
- `tests/test_sooka.py` — regression tests, run anywhere: `python -m unittest discover -s tests`
- `cdp_lib.py`, `probe_panel.py`, `api_stage.py` — older standalone CDP probes
- `main40.py` — **deprecated**, hardcoded pixel coordinates; kept as a record of the 16 Sep debug session

## Rules (Wajib)
1. **Channel ID sahaja** — nama channel berubah live oleh voice_renamer (2 rename/10min). Jangan hint by name.
2. **Stage mesti START dulu** — butang "Share Your Screen" tak wujud sebelum itu. Jangan klik "Continue without starting"; itu cabang yang buat stage tak start.
3. **Share dan Go Live perlu trusted input** — `Input.dispatchMouseEvent`, bukan `el.click()`. Synthetic event tak bagi user activation, jadi ia "klik" tapi tak jadi apa-apa.
4. `Ctrl+Shift+D` = toggle deafen; "Server Deafened" modal block share sampai di-undeaft.
5. DevTools `/json` pada main build (app-1.0.9258) wedges selepas beberapa ws sessions — **satu** panggilan `/json`, **satu** persistent ws per proses.
