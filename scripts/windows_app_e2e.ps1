param(
  [Parameter(Mandatory=$true)][string]$PortableExe,
  [Parameter(Mandatory=$true)][string]$InstallerExe
)

$ErrorActionPreference = "Stop"

function Assert-GuiWindow([string]$ExePath, [string]$Label) {
  if (-not (Test-Path $ExePath)) { throw "$Label executable missing: $ExePath" }
  $resolved = (Resolve-Path $ExePath).Path
  $processName = [IO.Path]::GetFileNameWithoutExtension($resolved)
  $startedAt = Get-Date
  $launcher = Start-Process -FilePath $resolved -PassThru
  $matched = $null
  try {
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline) {
      Start-Sleep -Milliseconds 500
      # PyInstaller --onefile uses a bootstrap parent and a child process. The
      # child, not necessarily Start-Process's returned process, owns Tk's HWND.
      $candidates = @(Get-Process -Name $processName -ErrorAction SilentlyContinue)
      foreach ($candidate in $candidates) {
        try {
          $candidate.Refresh()
          if ($candidate.StartTime -lt $startedAt.AddSeconds(-1)) { continue }
          if ($candidate.MainWindowHandle -ne 0 -and $candidate.MainWindowTitle -eq "FolderCompare") {
            $matched = $candidate
            break
          }
        }
        catch {
          # Process may disappear between enumeration and inspection.
        }
      }
      if ($null -ne $matched) { break }
      if ($launcher.HasExited -and $candidates.Count -eq 0) {
        throw "$Label exited before its GUI was validated (launcher exit $($launcher.ExitCode))"
      }
    }
    if ($null -eq $matched) {
      $snapshot = @(Get-Process -Name $processName -ErrorAction SilentlyContinue | ForEach-Object {
        try { "pid=$($_.Id), hwnd=$($_.MainWindowHandle), title='$($_.MainWindowTitle)'" } catch { "pid=$($_.Id), unavailable" }
      }) -join "; "
      throw "$Label never exposed the expected FolderCompare top-level window. Processes: $snapshot"
    }
    Write-Host "WINDOWS_GUI_OK label=$Label pid=$($matched.Id) hwnd=$($matched.MainWindowHandle) title=$($matched.MainWindowTitle)"
  }
  finally {
    @(Get-Process -Name $processName -ErrorAction SilentlyContinue) | ForEach-Object {
      try {
        if ($_.StartTime -ge $startedAt.AddSeconds(-1)) { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
      }
      catch {}
    }
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
foreach ($requiredNotice in @("LICENSE", "THIRD_PARTY_NOTICES.txt")) {
  $noticePath = Join-Path $installDir $requiredNotice
  if (-not (Test-Path $noticePath)) { throw "Installer omitted required notice: $noticePath" }
  if ((Get-Item $noticePath).Length -lt 100) { throw "Installed notice is unexpectedly small: $noticePath" }
}
Write-Host "WINDOWS_INSTALL_OK path=$installedExe notices=2"
Assert-GuiWindow -ExePath $installedExe -Label "installed"

$uninstaller = Join-Path $installDir "unins000.exe"
if (-not (Test-Path $uninstaller)) { throw "Uninstaller missing: $uninstaller" }
$uninstall = Start-Process -FilePath $uninstaller -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -Wait -PassThru
if ($uninstall.ExitCode -ne 0) { throw "Uninstaller failed with exit code $($uninstall.ExitCode)" }
Start-Sleep -Seconds 1
if (Test-Path $installedExe) { throw "Installed executable still exists after uninstall: $installedExe" }
Write-Host "WINDOWS_UNINSTALL_OK path=$installDir"
