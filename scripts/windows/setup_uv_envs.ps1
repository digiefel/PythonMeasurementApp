[CmdletBinding()]
param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\.." )).Path,
    [string]$WorkerPython = "",
    [switch]$Recreate
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
    throw "Required command not found: uv. Install uv first, for example: winget install --id Astral.UV"
}

$projectResolved = (Resolve-Path -LiteralPath $ProjectRoot).Path
$mainEnvPath = Join-Path $projectResolved ".venv"
$workerEnvPath = Join-Path $projectResolved ".venv32"
$mainReq = Join-Path $projectResolved "requirements.txt"

if ($Recreate) {
    if (Test-Path -LiteralPath $mainEnvPath) {
        Remove-Item -LiteralPath $mainEnvPath -Recurse -Force
    }
    if (Test-Path -LiteralPath $workerEnvPath) {
        Remove-Item -LiteralPath $workerEnvPath -Recurse -Force
    }
}

if (-not (Test-Path -LiteralPath $mainEnvPath)) {
    Write-Host "==> Creating main env: $mainEnvPath"
    & uv venv $mainEnvPath
    if ($LASTEXITCODE -ne 0) { throw "Failed to create main env." }
} else {
    Write-Host "==> Main env already exists: $mainEnvPath"
}

$mainPython = Join-Path $mainEnvPath "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $mainPython)) {
    throw "Main env Python not found: $mainPython"
}

if ([string]::IsNullOrWhiteSpace($WorkerPython)) {
    $WorkerPython = Join-Path $workerEnvPath "Scripts\python.exe"
}

if (-not (Test-Path -LiteralPath $WorkerPython)) {
    Write-Host "==> Creating 32-bit worker env: $workerEnvPath"
    & uv venv -p 3.11-32 $workerEnvPath
    if ($LASTEXITCODE -ne 0) { throw "Failed to create 32-bit worker env. Install 32-bit Python 3.11 or create .venv32 manually." }
}

if (-not (Test-Path -LiteralPath $WorkerPython)) {
    throw "Worker Python not found: $WorkerPython"
}

Write-Host "==> Installing/updating main packages"
& uv pip install -p $mainPython -r $mainReq
if ($LASTEXITCODE -ne 0) { throw "Failed to install main packages." }

Write-Host ""
Write-Host "Setup complete."
Write-Host "Main env Python  : $mainPython"
Write-Host "Worker env Python: $WorkerPython"
