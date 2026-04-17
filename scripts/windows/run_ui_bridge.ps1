[CmdletBinding()]
param(
    [string]$WorkerPython = "",

    [string]$B1500Dll = "",

    [string]$WGFMUDll = "",

    [string]$Visa32Dll = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\.." )).Path
$mainPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $mainPython)) {
    throw "Main env not found. Run scripts/windows/setup_uv_envs.ps1 first."
}

if ([string]::IsNullOrWhiteSpace($WorkerPython)) {
    $WorkerPython = Join-Path $projectRoot ".venv32\Scripts\python.exe"
}

if (-not (Test-Path -LiteralPath $WorkerPython)) {
    throw "WorkerPython not found: $WorkerPython"
}

$env:PYMEASUREMENT_BRIDGE_WORKER_PYTHON = (Resolve-Path -LiteralPath $WorkerPython).Path

if (-not [string]::IsNullOrWhiteSpace($B1500Dll)) {
    $env:PYMEASUREMENT_B1500_DLL = (Resolve-Path -LiteralPath $B1500Dll).Path
}
if (-not [string]::IsNullOrWhiteSpace($WGFMUDll)) {
    $env:PYMEASUREMENT_WGFMU_DLL = (Resolve-Path -LiteralPath $WGFMUDll).Path
}
if (-not [string]::IsNullOrWhiteSpace($Visa32Dll)) {
    $env:PYMEASUREMENT_VISA32_DLL = (Resolve-Path -LiteralPath $Visa32Dll).Path
}

Push-Location $projectRoot
try {
    & $mainPython "ui.py"
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}

exit $exitCode
