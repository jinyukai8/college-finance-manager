param(
    [string]$DeployRoot = (Join-Path $PSScriptRoot "..\build\windows")
)

$ErrorActionPreference = "Stop"
$SourceRoot = Split-Path -Parent $PSScriptRoot
$DeployRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($DeployRoot)
$VenvRoot = Join-Path $DeployRoot ".venv"
$PythonExe = Join-Path $VenvRoot "Scripts\python.exe"
$BuildTemp = Join-Path $DeployRoot "build\tmp"

New-Item -ItemType Directory -Force -Path $BuildTemp | Out-Null
$PreviousBuildTemp = $env:TEMP
$PreviousBuildTmp = $env:TMP
try {
    $env:TEMP = $BuildTemp
    $env:TMP = $BuildTemp
    if (-not (Test-Path -LiteralPath $PythonExe)) {
        & py -3.12 -m venv $VenvRoot
        if ($LASTEXITCODE -ne 0) { throw "Python environment setup failed with exit code $LASTEXITCODE" }
    }
    & $PythonExe -m pip install --disable-pip-version-check --no-cache-dir --requirement (Join-Path $SourceRoot "requirements.lock")
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed with exit code $LASTEXITCODE" }
}
finally {
    $env:TEMP = $PreviousBuildTemp
    $env:TMP = $PreviousBuildTmp
}

Write-Host "Development environment ready: $VenvRoot"
