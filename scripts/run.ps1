param(
    [string]$DeployRoot = (Join-Path $PSScriptRoot "..\build\windows"),
    [string]$DataDir
)

$ErrorActionPreference = "Stop"
$SourceRoot = Split-Path -Parent $PSScriptRoot
$DeployRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($DeployRoot)
$PythonExe = Join-Path $DeployRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Development environment not found at $PythonExe. Run scripts\setup.ps1 with the same -DeployRoot."
}
if (-not $DataDir) { $DataDir = Join-Path $DeployRoot "test-data" }
$DataDir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($DataDir)

Push-Location -LiteralPath (Join-Path $SourceRoot "src")
try {
    & $PythonExe -B -m college_finance_manager --data-dir $DataDir
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
