param(
    [string]$DeployRoot = (Join-Path $PSScriptRoot "..\build\windows")
)

$ErrorActionPreference = "Stop"
$SourceRoot = Split-Path -Parent $PSScriptRoot
$DeployRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($DeployRoot)
$SourcePath = Join-Path $SourceRoot "src"
$PythonExe = Join-Path $DeployRoot ".venv\Scripts\python.exe"
$DistRoot = Join-Path $DeployRoot "dist"
$BuildRoot = Join-Path $DeployRoot "build"
$SpecRoot = Join-Path $DeployRoot "spec"
$BuildTemp = Join-Path $BuildRoot "tmp"

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Build environment not found at $PythonExe. Run scripts\setup.ps1 with the same -DeployRoot."
}

New-Item -ItemType Directory -Force -Path $DistRoot, $BuildTemp, $SpecRoot | Out-Null
$PreviousPythonPath = $env:PYTHONPATH
$PreviousPyInstallerCache = $env:PYINSTALLER_CONFIG_DIR
$PreviousBuildTemp = $env:TEMP
$PreviousBuildTmp = $env:TMP
Push-Location -LiteralPath $BuildRoot
try {
    $env:PYTHONPATH = $SourcePath
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $BuildRoot "pyinstaller-cache"
    $env:TEMP = $BuildTemp
    $env:TMP = $BuildTemp
    $IconPath = Join-Path $SpecRoot "laboratory-ledger.ico"
    & $PythonExe -B (Join-Path $PSScriptRoot "build_icon.py") $IconPath
    if ($LASTEXITCODE -ne 0) { throw "Application icon generation failed" }
    $MigrationPath = Join-Path $SourcePath "college_finance_manager\infrastructure\migrations\*.sql"
    $EntryPoint = Join-Path $SourcePath "college_finance_manager\__main__.py"
    $BuildArgs = @(
        "--noconfirm", "--clean", "--windowed", "--icon", $IconPath,
        "--name", "CollegeFinanceManager", "--distpath", $DistRoot,
        "--workpath", $BuildRoot, "--specpath", $SpecRoot, "--paths", $SourcePath,
        "--hidden-import", "college_finance_manager.infrastructure.migrations",
        "--add-data", "${MigrationPath}:college_finance_manager/infrastructure/migrations",
        $EntryPoint
    )
    & $PythonExe -B -m PyInstaller @BuildArgs
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
}
finally {
    $env:PYTHONPATH = $PreviousPythonPath
    $env:PYINSTALLER_CONFIG_DIR = $PreviousPyInstallerCache
    $env:TEMP = $PreviousBuildTemp
    $env:TMP = $PreviousBuildTmp
    Pop-Location
}

Write-Host "Windows build completed: $(Join-Path $DistRoot 'CollegeFinanceManager\CollegeFinanceManager.exe')"
