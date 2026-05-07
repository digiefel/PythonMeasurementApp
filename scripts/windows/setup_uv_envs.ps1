[CmdletBinding()]
param(
    [string]$Python64 = "",
    [string]$Python32 = "",
    [string]$PythonVersion = "3.11",
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\.." )).Path,
    [switch]$Recreate
)

$ErrorActionPreference = "Stop"

function Assert-Command {
    param([string]$Name, [string]$InstallHint)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name`n$InstallHint"
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
        throw "Failed to query Python bitness: $PythonPath"
    }
    return [int]($out | Select-Object -First 1)
}

function Get-PythonFromLauncher {
    param([string[]]$Selectors)
    if (-not (Get-Command "py" -ErrorAction SilentlyContinue)) {
        return ""
    }
    foreach ($selector in $Selectors) {
        $out = & py $selector -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) {
            return [string]($out | Select-Object -First 1)
        }
    }
    return ""
}

function Resolve-Python {
    param(
        [string]$ExplicitPath,
        [int]$RequiredBits,
        [string]$Version
    )

    if (-not [string]::IsNullOrWhiteSpace($ExplicitPath)) {
        Assert-File $ExplicitPath "Python${RequiredBits}"
        return (Resolve-Path -LiteralPath $ExplicitPath).Path
    }

    $selectors = if ($RequiredBits -eq 64) {
        @("-${Version}-64", "-3-64")
    } else {
        @("-${Version}-32", "-3-32")
    }
    $fromLauncher = Get-PythonFromLauncher -Selectors $selectors
    if (-not [string]::IsNullOrWhiteSpace($fromLauncher)) {
        return (Resolve-Path -LiteralPath $fromLauncher).Path
    }

    throw @"
Could not find a ${RequiredBits}-bit Python interpreter.
Install Python ${Version} ${RequiredBits}-bit, or rerun this script with:
  -Python${RequiredBits} "C:\Path\To\python.exe"
"@
}

function Invoke-Uv {
    param([string[]]$UvArgs, [string]$Label)
    Write-Host "==> $Label"
    Write-Host "    uv $($UvArgs -join ' ')"
    & uv @UvArgs
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code ${LASTEXITCODE}"
    }
}

Assert-Command "uv" "Install uv first, for example: winget install --id Astral.UV"

$projectResolved = (Resolve-Path -LiteralPath $ProjectRoot).Path
$python64Resolved = Resolve-Python -ExplicitPath $Python64 -RequiredBits 64 -Version $PythonVersion
$python32Resolved = Resolve-Python -ExplicitPath $Python32 -RequiredBits 32 -Version $PythonVersion

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
$mainReq = Join-Path $projectResolved "requirements.txt"

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
    Invoke-Uv -UvArgs @("venv", "-p", $python64Resolved, $mainEnvPath) -Label "Create main 64-bit env"
} else {
    Write-Host "==> Main env already exists: $mainEnvPath"
}

if (-not (Test-Path -LiteralPath $workerEnvPath)) {
    Invoke-Uv -UvArgs @("venv", "-p", $python32Resolved, $workerEnvPath) -Label "Create worker 32-bit env"
} else {
    Write-Host "==> Worker env already exists: $workerEnvPath"
}

$mainPython = Join-Path $mainEnvPath "Scripts\python.exe"
$workerPython = Join-Path $workerEnvPath "Scripts\python.exe"

Assert-File $mainPython "Main env Python"
Assert-File $workerPython "Worker env Python"
Assert-File $mainReq "Requirements file"

Invoke-Uv -UvArgs @("pip", "install", "-p", $mainPython, "-r", $mainReq) -Label "Install/update main packages"

Write-Host ""
Write-Host "Setup complete."
Write-Host "Main env Python  : $mainPython"
Write-Host "Worker env Python: $workerPython"
