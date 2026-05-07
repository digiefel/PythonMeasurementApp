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

function Get-UvWindowsX86PythonRequest {
    param([switch]$OnlyInstalled)

    $uvArgs = @(
        "python", "list",
        "--output-format", "json",
        "--all-versions",
        "--all-arches",
        "cpython-3.11"
    )
    if ($OnlyInstalled) {
        $uvArgs = @("python", "list", "--only-installed", "--output-format", "json", "--all-versions", "--all-arches", "cpython-3.11")
    }

    $json = & uv @uvArgs
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($json)) {
        return ""
    }

    $matches = @($json | ConvertFrom-Json | Where-Object {
        $_.implementation -eq "cpython" -and
        $_.os -eq "windows" -and
        $_.arch -eq "x86" -and
        $_.version_parts.major -eq 3 -and
        $_.version_parts.minor -eq 11
    } | Sort-Object -Property @{ Expression = { [version]$_.version }; Descending = $true })

    if ($matches.Count -eq 0) {
        return ""
    }
    return [string]$matches[0].key
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
    $workerRequest = Get-UvWindowsX86PythonRequest -OnlyInstalled
    if ([string]::IsNullOrWhiteSpace($workerRequest)) {
        $workerRequest = Get-UvWindowsX86PythonRequest
    }
    if ([string]::IsNullOrWhiteSpace($workerRequest)) {
        throw "uv could not find a CPython 3.11 Windows x86 runtime. Install one with uv or create .venv32 manually."
    }
    Write-Host "==> Using worker Python request: $workerRequest"
    & uv venv -p $workerRequest $workerEnvPath
    if ($LASTEXITCODE -ne 0) { throw "Failed to create 32-bit worker env from $workerRequest." }
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
