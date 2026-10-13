param(
    [string]$DeployRoot = "D:\CollegeFinanceManager"
)

$ErrorActionPreference = "Stop"
$SourceRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $DeployRoot ".venv\Scripts\python.exe"
$DistRoot = Join-Path $DeployRoot "dist"
$BuildRoot = Join-Path $DeployRoot "build"
$SpecRoot = Join-Path $DeployRoot "spec"

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "未找到 D 盘运行环境，请先执行 scripts\setup_d_drive.ps1"
}

New-Item -ItemType Directory -Force -Path $DistRoot, $BuildRoot, $SpecRoot | Out-Null
Push-Location $SourceRoot
try {
    & $PythonExe -m PyInstaller `
        --noconfirm `
        --clean `
        --windowed `
        --name "CollegeFinanceManager" `
        --distpath $DistRoot `
        --workpath $BuildRoot `
        --specpath $SpecRoot `
        --paths (Join-Path $SourceRoot "src") `
        --collect-data "college_finance_manager" `
        (Join-Path $SourceRoot "src\college_finance_manager\__main__.py")
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller 构建失败，退出码 $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

Write-Host "Windows 构建完成：$(Join-Path $DistRoot 'CollegeFinanceManager\CollegeFinanceManager.exe')"
