param(
  [Parameter(Mandatory=$true)][string]$PortableExe,
  [Parameter(Mandatory=$true)][string]$InstallerExe
)

$ErrorActionPreference = "Stop"

function Assert-GuiWindow([string]$ExePath, [string]$Label) {
  if (-not (Test-Path $ExePath)) { throw "$Label executable missing: $ExePath" }
  $p = Start-Process -FilePath $ExePath -PassThru
  try {
    $deadline = (Get-Date).AddSeconds(15)
    $title = ""
    $handle = 0
    while ((Get-Date) -lt $deadline) {
      Start-Sleep -Milliseconds 500
      $p.Refresh()
      if ($p.HasExited) { throw "$Label exited before its GUI was validated (exit $($p.ExitCode))" }
      $title = $p.MainWindowTitle
      $handle = $p.MainWindowHandle
      if ($handle -ne 0 -and $title -eq "FolderCompare") { break }
    }
    if ($handle -eq 0) { throw "$Label never exposed a top-level Windows GUI handle" }
    if ($title -ne "FolderCompare") { throw "$Label window title was '$title', expected 'FolderCompare'" }
    Write-Host "WINDOWS_GUI_OK label=$Label pid=$($p.Id) hwnd=$handle title=$title"
  }
  finally {
    if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
  }
}

Assert-GuiWindow -ExePath (Resolve-Path $PortableExe).Path -Label "portable"

$installDir = Join-Path $env:RUNNER_TEMP ("FolderCompare-install-" + [guid]::NewGuid().ToString("N"))
$installer = (Resolve-Path $InstallerExe).Path
$installArgs = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=$installDir")
$install = Start-Process -FilePath $installer -ArgumentList $installArgs -Wait -PassThru
if ($install.ExitCode -ne 0) { throw "Installer failed with exit code $($install.ExitCode)" }

$installedExe = Join-Path $installDir "FolderCompare.exe"
if (-not (Test-Path $installedExe)) { throw "Installer completed but app is missing: $installedExe" }
Write-Host "WINDOWS_INSTALL_OK path=$installedExe"
Assert-GuiWindow -ExePath $installedExe -Label "installed"

$uninstaller = Join-Path $installDir "unins000.exe"
if (-not (Test-Path $uninstaller)) { throw "Uninstaller missing: $uninstaller" }
$uninstall = Start-Process -FilePath $uninstaller -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -Wait -PassThru
if ($uninstall.ExitCode -ne 0) { throw "Uninstaller failed with exit code $($uninstall.ExitCode)" }
Start-Sleep -Seconds 1
if (Test-Path $installedExe) { throw "Installed executable still exists after uninstall: $installedExe" }
Write-Host "WINDOWS_UNINSTALL_OK path=$installDir"
