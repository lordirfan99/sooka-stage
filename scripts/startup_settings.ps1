# Interactive startup settings for SookaStage.
#
# Deliberately a local desktop control, not a dashboard button: the Manager
# dashboard is tunnelled to the public internet via ngrok, and a control that
# rewrites Windows startup configuration must not be reachable from there.
# The dashboard shows this state read-only instead.

$python = "C:\Users\irfan\AppData\Local\Programs\Python\Python312\python.exe"
$cfg = "C:\Users\irfan\Desktop\sooka-stage\scripts\startup_config.py"

function Show-Status {
    Write-Host ""
    Write-Host "  Current settings" -ForegroundColor Cyan
    Write-Host "  ----------------"
    & $python $cfg status | ForEach-Object { Write-Host "  $_" }
    Write-Host ""
}

while ($true) {
    Clear-Host
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host "  SookaStage - Startup Settings" -ForegroundColor Cyan
    Write-Host "==================================================" -ForegroundColor Cyan
    Show-Status
    Write-Host "  What these do:" -ForegroundColor DarkGray
    Write-Host "    SookaStage starts with Windows" -ForegroundColor DarkGray
    Write-Host "      ON  = after you log in, SookaStage brings up the" -ForegroundColor DarkGray
    Write-Host "            dashboard, renamer, browsers, Discord clients" -ForegroundColor DarkGray
    Write-Host "            and all three streams, with no window shown." -ForegroundColor DarkGray
    Write-Host "      OFF = nothing starts until you run it yourself." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "    Discord clients start themselves" -ForegroundColor DarkGray
    Write-Host "      Recommended OFF. When ON, Windows starts Discord" -ForegroundColor DarkGray
    Write-Host "      WITHOUT the debugging port SookaStage needs, and" -ForegroundColor DarkGray
    Write-Host "      because Discord is single-instance that copy has to" -ForegroundColor DarkGray
    Write-Host "      be killed and restarted before streaming can work." -ForegroundColor DarkGray
    Write-Host "      Turning it off is reversible (nothing is deleted)." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  1) Turn SookaStage autostart ON"
    Write-Host "  2) Turn SookaStage autostart OFF"
    Write-Host "  3) Turn Discord autostart ON"
    Write-Host "  4) Turn Discord autostart OFF   (recommended)"
    Write-Host "  5) Refresh"
    Write-Host "  Q) Quit"
    Write-Host ""
    $choice = Read-Host "  Choose"

    switch ($choice.ToUpper()) {
        "1" { & $python $cfg sookastage on  | Out-Null }
        "2" { & $python $cfg sookastage off | Out-Null }
        "3" { & $python $cfg discord on     | Out-Null }
        "4" { & $python $cfg discord off    | Out-Null }
        "5" { }
        "Q" { return }
        default { }
    }
    if ($LASTEXITCODE -ne 0 -and $choice -match '^[1-4]$') {
        Write-Host ""
        Write-Host "  Windows refused that change. Details above." -ForegroundColor Red
        Read-Host "  Press Enter"
    }
}
