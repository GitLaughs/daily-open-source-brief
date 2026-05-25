param(
  [string]$RemoteHost = "example.com",
  [string]$User = "deploy",
  [string]$RemoteRoot = "/opt/daily-open-source-brief",
  [string]$RunTime = "06:00:00",
  [string]$BriefInterval = "08,11,14,17,20,22:00:00",
  [string]$CollectInterval = "*:00:00",
  [switch]$SkipSmoke
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Package = Join-Path $env:TEMP "daily-open-source-brief-deploy.tar.gz"
$Remote = "${User}@${RemoteHost}"
$RemotePackage = "/tmp/daily-open-source-brief-deploy.tar.gz"

function Assert-LastExitCode {
  param([string]$Step)
  if ($LASTEXITCODE -ne 0) {
    throw "${Step} failed with exit code ${LASTEXITCODE}"
  }
}

Push-Location $ProjectRoot
try {
  if (Test-Path $Package) { Remove-Item -LiteralPath $Package -Force }
  tar `
    --exclude=".venv" `
    --exclude="data" `
    --exclude="logs" `
    --exclude="public/archive" `
    --exclude="__pycache__" `
    --exclude=".pytest_cache" `
    --exclude=".git" `
    --exclude=".env" `
    -czf $Package .
  Assert-LastExitCode "package"

  scp $Package "${Remote}:${RemotePackage}"
  Assert-LastExitCode "upload"
  ssh $Remote "set -euo pipefail; mkdir -p '$RemoteRoot'; tar -xzf '$RemotePackage' -C '$RemoteRoot'; cd '$RemoteRoot'; bash scripts/install-linux.sh --install-root '$RemoteRoot' --run-time '$RunTime' --brief-interval '$BriefInterval' --collect-interval '$CollectInterval'"
  Assert-LastExitCode "remote install"

  if (-not $SkipSmoke) {
    ssh $Remote "set -euo pipefail; cd '$RemoteRoot'; set -a; [ -f .env ] && . ./.env; set +a; .venv/bin/python -m app.run_daily --sample --skip-mail --force-send"
    Assert-LastExitCode "remote smoke"
  }
}
finally {
  Pop-Location
}

Write-Host "Deployed to ${Remote}:${RemoteRoot}"
