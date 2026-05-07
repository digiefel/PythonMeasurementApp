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

$runScript = Join-Path $PSScriptRoot "run_app.ps1"
& $runScript `
    -Python64 $Python64 `
    -Python32 $Python32 `
    -PythonVersion $PythonVersion `
    -WorkerPython $WorkerPython `
    -B1500Dll $B1500Dll `
    -WGFMUDll $WGFMUDll `
    -Visa32Dll $Visa32Dll `
    -SkipSetup:$SkipSetup `
    -Recreate:$Recreate
exit $LASTEXITCODE
