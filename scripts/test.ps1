param(
  [string]$Proxy = "",
  [switch]$SkipSample
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

function Assert-LastExitCode {
  param([string]$Step)
  if ($LASTEXITCODE -ne 0) {
    throw "$Step failed with exit code $LASTEXITCODE"
  }
}

if ($Proxy) {
  $env:HTTP_PROXY = $Proxy
  $env:HTTPS_PROXY = $Proxy
}

Push-Location $ProjectRoot
try {
  if (-not (Test-Path $VenvPython)) {
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1 -SkipSample
    Assert-LastExitCode "install"
  }

  & $VenvPython -m pip install -r requirements.txt pytest
  Assert-LastExitCode "install test dependencies"

  & $VenvPython -m pytest
  Assert-LastExitCode "pytest"

  if (Get-Command git -ErrorAction SilentlyContinue) {
    git diff --check
    Assert-LastExitCode "git diff --check"
  }

  if (-not $SkipSample) {
    & $VenvPython -m app.cli run --sample --skip-web --skip-rss --skip-mail --skip-lark --force-send
    Assert-LastExitCode "sample run"
  }
}
finally {
  Pop-Location
}

Write-Host "All checks passed."

