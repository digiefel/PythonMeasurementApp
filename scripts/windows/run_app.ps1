[CmdletBinding()]
param(
    [string]$Python64 = "",
    [string]$Python32 = "",
    [string]$PythonVersion = "3.11",
    [string]$WorkerPython = "",
    [string]$B1500Dll = "",
    [string]$WGFMUDll = "",
    [string]$Visa32Dll = "",
    [switch]$SkipSetup,
    [switch]$Recreate
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\.." )).Path
$setupScript = Join-Path $PSScriptRoot "setup_uv_envs.ps1"
$mainPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not $SkipSetup) {
    & $setupScript `
        -Python64 $Python64 `
        -Python32 $Python32 `
        -PythonVersion $PythonVersion `
        -ProjectRoot $projectRoot `
        -Recreate:$Recreate
}

if (-not (Test-Path -LiteralPath $mainPython)) {
    throw "Main env not found: $mainPython"
}

if ([string]::IsNullOrWhiteSpace($WorkerPython)) {
    $WorkerPython = Join-Path $projectRoot ".venv32\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $WorkerPython)) {
    throw "Worker Python not found: $WorkerPython"
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
    & $mainPython "main.py"
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}

exit $exitCode
