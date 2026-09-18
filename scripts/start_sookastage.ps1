# Double-click entry point for SookaStage.
#
# 0. Makes sure the Manager dashboard (sooka_server.py, port 8080) is running
#    -- the safe .py source tree, never the frozen SookaStream-v8.16.exe
#    (that build has a live Discord gateway bot; per an explicit 2026-09-18
#    decision it stays off). If the old exe is somehow the one holding the
#    port, it is stopped (by PID) and replaced.
# 1. Makes sure each of the three sooka.my watch windows (Brave / Chrome /
#    Chrome Beta) is open -- these are the screenshare SOURCES.
# 2. Chrome Beta's own window title never says "Beta" on this machine, so it
#    is indistinguishable from plain Chrome in Discord's share picker unless
#    something tags it -- normally Tampermonkey's "Set Browser Identity".
#    Since that is not installed, this script tags it directly by setting
#    the OS-level window title (SetWindowText). Safe to run every time.
# 3. Makes sure each of the three Discord clients is up with its debug port.
# 4. Runs sookastage_prod.py --all, which is idempotent -- already-live
#    streams are untouched, only what's actually down gets (re)driven.

$ErrorActionPreference = "Continue"
$repo = "C:\Users\irfan\Desktop\sooka-stage"
$python = "C:\Users\irfan\AppData\Local\Programs\Python\Python312\python.exe"
$pythonw = "C:\Users\irfan\AppData\Local\Programs\Python\Python312\pythonw.exe"
$managerDir = "C:\Users\irfan\Desktop\Restored-Desktop\SookaStream-Windows-x64-v8.6\SookaStream-Windows-x64-v8.6"

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class SookaWin32 {
    [DllImport("user32.dll", CharSet=CharSet.Auto)] public static extern bool SetWindowText(IntPtr hWnd, string text);
}
"@

Write-Host "=== SookaStage ===" -ForegroundColor Cyan
Write-Host ""

# ---- 0: Manager dashboard ---------------------------------------------------
Write-Host "Checking Manager dashboard (port 8080)..."
$mgrConn = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
$mgrOk = $false
if ($mgrConn) {
    $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId=$($mgrConn.OwningProcess)" -ErrorAction SilentlyContinue).CommandLine
    if ($cmdLine -like "*sooka_server.py*") {
        Write-Host "  Manager dashboard : already up (safe .py server)" -ForegroundColor Green
        $mgrOk = $true
    } else {
        Write-Host "  Manager dashboard : port 8080 held by something else ($cmdLine) -- stopping it" -ForegroundColor Yellow
        Stop-Process -Id $mgrConn.OwningProcess -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
}
if (-not $mgrOk) {
    Write-Host "  Manager dashboard : starting (headless)..." -ForegroundColor Yellow
    Start-Process $pythonw -ArgumentList "`"$managerDir\run_headless.py`""
    Start-Sleep -Seconds 8
}

# ---- 1 & 2: watch-browser windows -----------------------------------------
Write-Host "Checking watch-browser windows..."

$watch = @(
    @{ name = "Brave";       exe = "C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"; pathLike = $null;                          tag = $null }
    @{ name = "Chrome";      exe = "C:\Program Files\Google\Chrome\Application\chrome.exe";               pathLike = "*\Chrome\Application*";        tag = $null }
    @{ name = "Chrome Beta"; exe = "C:\Program Files\Google\Chrome Beta\Application\chrome.exe";           pathLike = "*Chrome Beta*";                 tag = "Chrome Beta" }
)

foreach ($w in $watch) {
    $procName = if ($w.name -eq "Brave") { "brave" } else { "chrome" }
    $existing = Get-Process $procName -ErrorAction SilentlyContinue |
        Where-Object {
            (-not $w.pathLike -or $_.Path -like $w.pathLike) -and
            $_.MainWindowTitle -like "Watch online Live Sports*"
        } | Select-Object -First 1

    if (-not $existing) {
        Write-Host "  $($w.name) : no sooka.my window found, opening one..." -ForegroundColor Yellow
        Start-Process $w.exe -ArgumentList "--new-window", "https://sooka.my/"
        Start-Sleep -Seconds 6
        $existing = Get-Process $procName -ErrorAction SilentlyContinue |
            Where-Object {
                (-not $w.pathLike -or $_.Path -like $w.pathLike) -and
                $_.MainWindowTitle -like "Watch online Live Sports*"
            } | Select-Object -First 1
    } else {
        Write-Host "  $($w.name) : already open" -ForegroundColor Green
    }

    if ($existing -and $w.tag -and $existing.MainWindowTitle -notlike "*$($w.tag)*") {
        $newTitle = "$($existing.MainWindowTitle) - $($w.tag)"
        [SookaWin32]::SetWindowText($existing.MainWindowHandle, $newTitle) | Out-Null
        Write-Host "  $($w.name) : tagged window title for picker disambiguation" -ForegroundColor DarkYellow
    }
}

# ---- 3: Discord clients -----------------------------------------------------
Write-Host ""
Write-Host "Checking Discord clients..."

$streams = @{ 1 = 9223; 2 = 9225; 3 = 9224 }
$names   = @{ 1 = "Discord (stable)"; 2 = "Canary"; 3 = "PTB" }

foreach ($n in 1, 2, 3) {
    $port = $streams[$n]
    $up = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
          Where-Object { $_.LocalPort -eq $port }
    if ($up) {
        Write-Host "  stream $n ($($names[$n])) : already up on port $port" -ForegroundColor Green
    } else {
        Write-Host "  stream $n ($($names[$n])) : launching (port $port)..." -ForegroundColor Yellow
        powershell -ExecutionPolicy Bypass -File "$repo\scripts\schtask_launch_client.ps1" -Stream $n
        Start-Sleep -Seconds 8
    }
}

Write-Host ""
Write-Host "Waiting a moment for everything to settle..."
Start-Sleep -Seconds 3

# ---- 4: run the automation ---------------------------------------------------
Write-Host ""
Write-Host "Starting stages and screenshare on all three streams..." -ForegroundColor Cyan
Write-Host ""
& $python "$repo\sookastage_prod.py" --all
$rc = $LASTEXITCODE

Write-Host ""
Write-Host "Manager dashboard: http://localhost:8080/dashboard" -ForegroundColor DarkCyan
if ($rc -eq 0) {
    Write-Host "=== All three streams are live. ===" -ForegroundColor Green
} else {
    Write-Host "=== Something did not come up. See the step that failed above. ===" -ForegroundColor Red
    Write-Host "Tip: pick the right match on each sooka.my tab yourself if it's showing the wrong thing --" -ForegroundColor DarkYellow
    Write-Host "this script only makes sure a sooka.my window exists, it does not choose the match." -ForegroundColor DarkYellow
}
Write-Host ""
Write-Host "Press any key to close this window..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
