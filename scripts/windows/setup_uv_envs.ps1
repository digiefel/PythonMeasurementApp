[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Python64,

    [Parameter(Mandatory = $true)]
    [string]$Python32,

    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\.." )).Path,

    [switch]$Recreate
)

$ErrorActionPreference = "Stop"

function Assert-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

function Assert-File {
    param([string]$PathValue, [string]$Label)
    if (-not (Test-Path -LiteralPath $PathValue)) {
        throw "$Label not found: $PathValue"
    }
}

function Get-PythonBitness {
    param([string]$PythonPath)
    $out = & $PythonPath -c "import struct; print(struct.calcsize('P') * 8)"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to query python bitness: $PythonPath"
    }
    return [int]($out | Select-Object -First 1)
}

function Invoke-Uv {
    param([string[]]$Args, [string]$Label)
    Write-Host "==> $Label"
    $cmdText = "uv " + ($Args -join " ")
    Write-Host "    $cmdText"
    $output = & uv @Args 2>&1
    $exitCode = $LASTEXITCODE
    if ($output) {
        $output | ForEach-Object { Write-Host $_ }
    }
    if ($exitCode -ne 0) {
        throw "$Label failed with exit code $exitCode: $cmdText"
    }
}

Assert-Command "uv"
Assert-File $Python64 "Python64"
Assert-File $Python32 "Python32"

$python64Resolved = (Resolve-Path -LiteralPath $Python64).Path
$python32Resolved = (Resolve-Path -LiteralPath $Python32).Path
$projectResolved = (Resolve-Path -LiteralPath $ProjectRoot).Path

$bit64 = Get-PythonBitness -PythonPath $python64Resolved
$bit32 = Get-PythonBitness -PythonPath $python32Resolved

if ($bit64 -ne 64) {
    throw "Python64 is not 64-bit: $python64Resolved ($bit64-bit)"
}
if ($bit32 -ne 32) {
    throw "Python32 is not 32-bit: $python32Resolved ($bit32-bit)"
}

$mainEnvPath = Join-Path $projectResolved ".venv"
$workerEnvPath = Join-Path $projectResolved ".venv32"

if ($Recreate) {
    if (Test-Path -LiteralPath $mainEnvPath) {
        Write-Host "==> Removing $mainEnvPath"
        Remove-Item -LiteralPath $mainEnvPath -Recurse -Force
    }
    if (Test-Path -LiteralPath $workerEnvPath) {
        Write-Host "==> Removing $workerEnvPath"
        Remove-Item -LiteralPath $workerEnvPath -Recurse -Force
    }
}

if (-not (Test-Path -LiteralPath $mainEnvPath)) {
    Invoke-Uv -Args @("venv", "--seed", "--python", $python64Resolved, $mainEnvPath) -Label "Create main 64-bit env"
} else {
    Write-Host "==> Main env already exists: $mainEnvPath"
}

if (-not (Test-Path -LiteralPath $workerEnvPath)) {
    Invoke-Uv -Args @("venv", "--seed", "--python", $python32Resolved, $workerEnvPath) -Label "Create worker 32-bit env"
} else {
    Write-Host "==> Worker env already exists: $workerEnvPath"
}

$mainPython = Join-Path $mainEnvPath "Scripts\python.exe"
$workerPython = Join-Path $workerEnvPath "Scripts\python.exe"
$mainReq = Join-Path $projectResolved "requirements.txt"

Assert-File $mainPython "Main env python"
Assert-File $workerPython "Worker env python"
Assert-File $mainReq "Main requirements"

Invoke-Uv -Args @("pip", "install", "--python", $mainPython, "-r", $mainReq) -Label "Install main 64-bit packages"
Write-Host "==> Worker env ready: $workerEnvPath"

Write-Host ""
Write-Host "Setup complete."
Write-Host "Main env python  : $mainPython"
Write-Host "Worker env python: $workerPython"
Write-Host ""
Write-Host "Next steps:"
Write-Host "1) Activate .venv and run: python ui.py"
