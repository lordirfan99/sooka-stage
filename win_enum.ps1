Add-Type @"
using System;using System.Text;using System.Runtime.InteropServices;
public class W {
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr l);
  public delegate bool EnumWindowsProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int c);
}
"@
$out = @()
[W]::EnumWindows({param($h,$l) if([W]::IsWindowVisible($h)){$sb=New-Object System.Text.StringBuilder 256;[W]::GetWindowText($h,$sb,256)|Out-Null;if($sb.ToString()){ $out += $sb.ToString() }}; $true},[IntPtr]::Zero) | Out-Null
"VISIBLE WINDOWS:"
$out
"canary_procs=" + ((Get-Process DiscordCanary -ErrorAction SilentlyContinue).Count)
