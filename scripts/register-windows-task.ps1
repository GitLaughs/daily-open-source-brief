param(
  [string]$TaskName = "daily-open-source-brief",
  [string]$DailyAt = "08:00",
  [string]$ProjectRoot = "",
  [string]$PythonPath = "",
  [switch]$SkipMail,
  [switch]$SkipLark
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
  $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
if (-not $PythonPath) {
  $PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path $PythonPath)) {
  throw "Python path not found: $PythonPath. Run scripts\install-windows.ps1 first."
}

$runArgs = @("-m", "app.cli", "run")
if ($SkipMail) { $runArgs += "--skip-mail" }
if ($SkipLark) { $runArgs += "--skip-lark" }

$quotedProject = $ProjectRoot.Replace("'", "''")
$quotedPython = $PythonPath.Replace("'", "''")
$command = "Set-Location '$quotedProject'; & '$quotedPython' $($runArgs -join ' ')"

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -Command `"$command`""
$trigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Run daily-open-source-brief" -Force | Out-Null

Write-Host "Registered Windows task '$TaskName' at $DailyAt."

