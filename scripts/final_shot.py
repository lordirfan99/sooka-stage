"""Windowless full-screen screenshot helper for the Windows PC.

MUST be run through a scheduled task with the /it flag so it lands in the interactive
desktop session, and MUST use pythonw.exe so no console window appears on the owner's
desktop.

    schtasks /create /tn SookLastShot /tr "C:\\Users\\irfan\\AppData\\Local\\Programs\\Python\\Python312\\pythonw.exe C:\\Users\\irfan\\SookaStage\\scripts\\final_shot.py" /sc once /st 22:30 /it /f
    schtasks /run /tn SookLastShot
    schtasks /delete /tn SookLastShot /f

Why: screen capture from a plain SSH session fails with "The handle is invalid", and a
console window spawned by python.exe / a `> file` redirect can take foreground and make
the whole desktop look frozen.
"""

import subprocess
import sys

OUT = r"C:\Users\irfan\SookaStage\desktop_final.png"

PS = (
    "Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
    "$b = [System.Windows.Forms.SystemInformation]::VirtualScreen; "
    "$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height; "
    "$g = [System.Drawing.Graphics]::FromImage($bmp); "
    "$g.CopyFromScreen($b.X, $b.Y, 0, 0, $bmp.Size); "
    f"$bmp.Save('{OUT.replace(chr(92), chr(92) * 2)}', [System.Drawing.Imaging.ImageFormat]::Png); "
    "$g.Dispose(); $bmp.Dispose(); Write-Output 'SHOT_OK'"
)


def main() -> int:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", PS],
        capture_output=True,
        text=True,
        timeout=60,
    )
    ok = "SHOT_OK" in (result.stdout or "")
    print(result.stdout.strip() or result.stderr.strip()[:200])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
