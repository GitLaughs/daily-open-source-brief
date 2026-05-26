param(
  [string]$Python = "",
  [string]$Proxy = "",
  [switch]$SkipSample,
  [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

function Invoke-HostCommand {
  param(
    [string]$Command,
    [string[]]$Arguments
  )
  & $Command @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "$Command failed with exit code $LASTEXITCODE"
  }
}

function Find-PythonCommand {
  if ($Python) {
    return @($Python)
  }
  if (Get-Command py -ErrorAction SilentlyContinue) {
    return @("py", "-3")
  }
  if (Get-Command python -ErrorAction SilentlyContinue) {
    return @("python")
  }
  throw "Python 3.10+ not found. Install Python and add it to PATH."
}

if ($Proxy) {
  $env:HTTP_PROXY = $Proxy
  $env:HTTPS_PROXY = $Proxy
}

Push-Location $ProjectRoot
try {
  $PythonCommand = Find-PythonCommand
  $BasePython = $PythonCommand[0]
  $BaseArgs = @()
  if ($PythonCommand.Count -gt 1) {
    $BaseArgs = $PythonCommand[1..($PythonCommand.Count - 1)]
  }

  if ((Test-Path $VenvDir) -and $Force) {
    Remove-Item -LiteralPath $VenvDir -Recurse -Force
  }

  if (-not (Test-Path $VenvPython)) {
    Invoke-HostCommand $BasePython ($BaseArgs + @("-m", "venv", ".venv"))
  }

  Invoke-HostCommand $VenvPython @("-m", "pip", "install", "--upgrade", "pip")
  Invoke-HostCommand $VenvPython @("-m", "pip", "install", "-r", "requirements.txt")

  if (-not (Test-Path ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
    Write-Host "Created .env from .env.example. Fill real credentials only when needed."
  }

  Invoke-HostCommand $VenvPython @("-m", "app.cli", "plugin", "check")

  if (-not $SkipSample) {
    Invoke-HostCommand $VenvPython @(
      "-m", "app.cli", "run",
      "--sample",
      "--skip-web",
      "--skip-rss",
      "--skip-mail",
      "--skip-lark",
      "--force-send"
    )
  }
}
finally {
  Pop-Location
}

Write-Host "Install complete. Use .\.venv\Scripts\python.exe -m app.cli run"

