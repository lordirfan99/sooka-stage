<#
.SYNOPSIS
    Launch one Discord client with the automation flags and the correct stage deep link.

.DESCRIPTION
    `--remote-debugging-port` is only honoured at process start, so this must launch the
    executable directly (or from a shortcut carrying the same arguments). If Discord has
    auto-updated, the app-* directory name changes - update the paths below, or the
    script will report which version directories actually exist.

.PARAMETER Stream
    1 = Discord stable (port 9223, ch1), 3 = PTB (port 9224, ch3), 2 = Canary (port 9225, ch2).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File schtask_launch_client.ps1 -Stream 1
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet(1, 2, 3)]
    [int]$Stream
)

$GUILD = '1251553669644816518'

$map = @{
    1 = @{
        Exe     = "C:\Users\irfan\AppData\Local\Discord\app-1.0.9258\Discord.exe"
        Port    = 9223
        Channel = '1477692113738137600'
        Root    = "C:\Users\irfan\AppData\Local\Discord"
    }
    2 = @{
        Exe     = "C:\Users\irfan\AppData\Local\DiscordCanary\app-1.0.1177\DiscordCanary.exe"
        Port    = 9225
        Channel = '1481358977584599283'
        Root    = "C:\Users\irfan\AppData\Local\DiscordCanary"
    }
    3 = @{
        Exe     = "C:\Users\irfan\AppData\Local\DiscordPTB\app-1.0.1220\DiscordPTB.exe"
        Port    = 9224
        Channel = '1481359453759475876'
        Root    = "C:\Users\irfan\AppData\Local\DiscordPTB"
    }
}

$cfg = $map[$Stream]

if (-not (Test-Path $cfg.Exe)) {
    Write-Output "EXE NOT FOUND: $($cfg.Exe)"
    Write-Output "Installed versions in $($cfg.Root):"
    Get-ChildItem $cfg.Root -Directory -Filter 'app-*' -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty Name
    exit 1
}

$uri = "discord://-/channels/$GUILD/$($cfg.Channel)"
$args = @('--force-renderer-accessibility', "--remote-debugging-port=$($cfg.Port)", $uri)

Start-Process -FilePath $cfg.Exe -ArgumentList $args
Write-Output "launched stream=$Stream port=$($cfg.Port) channel=$($cfg.Channel)"

Start-Sleep -Seconds 20

try {
    $targets = Invoke-RestMethod "http://127.0.0.1:$($cfg.Port)/json/list" -TimeoutSec 6
    $pages = $targets | Where-Object { $_.type -eq 'page' }
    foreach ($p in $pages) { Write-Output ("page " + $p.url.Substring(0, [Math]::Min(70, $p.url.Length))) }
} catch {
    Write-Output "CDP NOT UP on port $($cfg.Port) - client may have exited (Canary 1.0.1177 is known for this)"
}
