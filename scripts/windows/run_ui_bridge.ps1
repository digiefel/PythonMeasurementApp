[CmdletBinding()]
param(
    [string]$WorkerPython = "",
    [string]$B1500Dll = "",
    [string]$WGFMUDll = "",
    [string]$Visa32Dll = "",
    [switch]$SkipSetup,
    [switch]$Recreate
)

$runScript = Join-Path $PSScriptRoot "run_app.ps1"
& $runScript `
    -WorkerPython $WorkerPython `
    -B1500Dll $B1500Dll `
    -WGFMUDll $WGFMUDll `
    -Visa32Dll $Visa32Dll `
    -SkipSetup:$SkipSetup `
    -Recreate:$Recreate
exit $LASTEXITCODE
