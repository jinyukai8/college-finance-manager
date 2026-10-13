param(
    [string]$DeployRoot = "D:\CollegeFinanceManager"
)

$ErrorActionPreference = "Stop"
$PythonExe = Join-Path $DeployRoot ".venv\Scripts\python.exe"
$DataRoot = Join-Path $DeployRoot "data"

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "未找到 D 盘运行环境，请先执行 scripts\setup_d_drive.ps1"
}

& $PythonExe -m college_finance_manager --data-dir $DataRoot
exit $LASTEXITCODE
