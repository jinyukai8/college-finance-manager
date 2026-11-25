param(
    [string]$DeployRoot = (Join-Path $PSScriptRoot "..\build\windows")
)

$ErrorActionPreference = "Stop"
$SourceRoot = Split-Path -Parent $PSScriptRoot
$DeployRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($DeployRoot)
$PythonExe = Join-Path $DeployRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Development environment not found at $PythonExe. Run scripts\setup.ps1 with the same -DeployRoot."
}

Push-Location -LiteralPath $SourceRoot
try {
    & $PythonExe -B -m pytest
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
