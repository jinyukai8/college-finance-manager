param(
    [string]$DeployRoot = "D:\CollegeFinanceManager"
)

$ErrorActionPreference = "Stop"
$SourceRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $DeployRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "未找到 D 盘运行环境，请先执行 scripts\setup_d_drive.ps1"
}

Push-Location $SourceRoot
try {
    & $PythonExe -m pytest
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
