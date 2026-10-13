param(
    [string]$DeployRoot = "D:\CollegeFinanceManager"
)

$ErrorActionPreference = "Stop"
$SourceRoot = Split-Path -Parent $PSScriptRoot
$VenvRoot = Join-Path $DeployRoot ".venv"
$PythonExe = Join-Path $VenvRoot "Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $DeployRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DeployRoot "data") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DeployRoot "dist") | Out-Null

if (-not (Test-Path -LiteralPath $PythonExe)) {
    py -3.12 -m venv $VenvRoot
}

& $PythonExe -m pip install --disable-pip-version-check --requirement (Join-Path $SourceRoot "requirements.lock")
& $PythonExe -m pip install --disable-pip-version-check --no-deps $SourceRoot

Write-Host "部署环境已准备：$DeployRoot"
Write-Host "应用数据目录：$(Join-Path $DeployRoot 'data')"
