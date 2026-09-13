param(
  [string]$OutputPath = "THIRD_PARTY_NOTICES.txt"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path "LICENSE")) { throw "Project LICENSE is missing" }

$pythonRoot = (& python -c "import sys; print(sys.base_prefix)").Trim()
$pythonLicense = Join-Path $pythonRoot "LICENSE.txt"
if (-not (Test-Path $pythonLicense)) {
  throw "Python runtime license not found at $pythonLicense"
}

$sections = New-Object System.Collections.Generic.List[string]
$seenHashes = @{}

function Add-LicenseSection([string]$Title, [string]$Path) {
  if (-not (Test-Path $Path)) { throw "License file missing: $Path" }
  $resolved = (Resolve-Path $Path).Path
  $hash = (Get-FileHash $resolved -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($seenHashes.ContainsKey($hash)) { return }
  $seenHashes[$hash] = $true
  $body = Get-Content $resolved -Raw
  $sections.Add("===== $Title =====`r`nSHA-256: $hash`r`n`r`n$body")
}

Add-LicenseSection -Title "Python runtime license" -Path $pythonLicense

$tclRoot = Join-Path $pythonRoot "tcl"
if (-not (Test-Path $tclRoot)) { throw "Tcl/Tk runtime directory not found at $tclRoot" }
$tclLicenses = @(Get-ChildItem $tclRoot -Recurse -File -Filter "license.terms" -ErrorAction Stop)
if ($tclLicenses.Count -lt 1) { throw "No Tcl/Tk license.terms files found under $tclRoot" }
foreach ($license in $tclLicenses) {
  Add-LicenseSection -Title "Tcl/Tk runtime license ($($license.Directory.Name))" -Path $license.FullName
}

$pyInstallerLicenses = @(& python -c "import importlib.metadata as m; d=m.distribution('pyinstaller'); [print(d.locate_file(f)) for f in (d.files or []) if any(x in str(f).lower() for x in ('license','copying')) and d.locate_file(f).is_file()]")
if ($pyInstallerLicenses.Count -lt 1) { throw "PyInstaller license/copying notice was not found in the installed distribution" }
foreach ($license in $pyInstallerLicenses) {
  Add-LicenseSection -Title "PyInstaller bootloader/build-tool license" -Path $license
}

$header = @"
FolderCompare third-party notices

The Windows executable is assembled with the Python runtime, Tcl/Tk, and the
PyInstaller bootloader. Their license texts from the exact build environment
are reproduced below. FolderCompare's own MIT license is distributed
separately as LICENSE.

"@

$noticeText = $header + ($sections -join "`r`n`r`n")
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($OutputPath, $noticeText, $utf8NoBom)
if ((Get-Item $OutputPath).Length -lt 1000) { throw "Third-party notices file is unexpectedly small" }
Write-Host "WINDOWS_NOTICES_OK path=$OutputPath bytes=$((Get-Item $OutputPath).Length) sections=$($sections.Count)"
