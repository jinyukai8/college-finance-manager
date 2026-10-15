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
    throw "Build environment not found. Run scripts\setup_d_drive.ps1 first."
}

New-Item -ItemType Directory -Force -Path $DistRoot, $BuildRoot, $SpecRoot | Out-Null
Push-Location $SourceRoot
try {
    # Refresh the build environment so data collection uses current sources.
    & $PythonExe -m pip install --disable-pip-version-check --no-deps --no-build-isolation --force-reinstall $SourceRoot
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "Installing current sources failed with exit code $LASTEXITCODE"
    }
    $IconPath = Join-Path $SpecRoot "laboratory-ledger.ico"
    & $PythonExe (Join-Path $PSScriptRoot "build_icon.py") $IconPath
    if ($LASTEXITCODE -ne 0) { throw "Application icon generation failed" }
    & $PythonExe -m PyInstaller --noconfirm --clean --windowed --icon $IconPath --name "CollegeFinanceManager" --distpath $DistRoot --workpath $BuildRoot --specpath $SpecRoot --paths (Join-Path $SourceRoot "src") --collect-data "college_finance_manager" (Join-Path $SourceRoot "src\college_finance_manager\__main__.py")
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

Write-Host "Windows build completed: $(Join-Path $DistRoot 'CollegeFinanceManager\CollegeFinanceManager.exe')"
