
# SookaStage (sooka-stage)

Automation untuk stream sooka → Discord stage channels, per-streamer (3 Discord clients).

| Stream | Discord client | CDP port | sooka browser | Stage channel ID |
|---|---|---|---|---|
| 1 | Discord (stable) | 9223 | Brave | `1477692113738137600` |
| 2 | Canary | 9225 | Chrome Beta | `1481358977584599283` |
| 3 | PTB | 9224 | Google Chrome | `1481359453759475876` |

Status, isu aktif dan next steps: lihat [`SOOKASTAGE_PROGRESS.md`](SOOKASTAGE_PROGRESS.md).

## Files
- `sookastage_prod.py` — production runner draft (1 persistent CDP ws, rect + `Input.dispatchMouseEvent`, no focus needed)
- `cdp_lib.py` — helper untuk other scripts
- `probe_panel.py`, `api_stage.py` — CDP probes / channel ID → name resolver
- `main40.py` — kompilasi flow snapshot dari debug malam 16 Sep

## Rules (Wajib)
1. **Channel ID sahaja** — nama channel berubah live oleh voice_renamer (2 rename/10min). Jangan hint by name.
2. Stage share hanya mesej bila stage **already started**; klik "Start the Stage" topic modal dari scheduled-task context SELALU gagal (Windows foreground-lock) — guna real mouse di owner, atau AttachThreadInput helper.
3. `Ctrl+Shift+D` = toggle deafen; "Server Deafened" modal block share sampai di-undeaft.
4. DevTools /json pada main build (app-1.0.9258) wedges selepas beberapa ws sessions; 1 persistent ws per script.
