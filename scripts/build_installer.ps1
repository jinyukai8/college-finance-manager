param(
    [string]$DeployRoot = "D:\CollegeFinanceManager"
)

$ErrorActionPreference = "Stop"
$SourceRoot = Split-Path -Parent $PSScriptRoot

& (Join-Path $PSScriptRoot "build_windows.ps1") -DeployRoot $DeployRoot
if ($LASTEXITCODE -ne 0) {
    throw "Application build failed with exit code $LASTEXITCODE"
}

$Candidates = @(
    (Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "D:\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

$Compiler = $Candidates | Select-Object -First 1
if (-not $Compiler) {
    throw "Inno Setup 6 was not found. Install it before running this script."
}

New-Item -ItemType Directory -Force -Path (Join-Path $DeployRoot "installer") | Out-Null
& $Compiler (Join-Path $SourceRoot "installer\CollegeFinanceManager.iss")
if ($LASTEXITCODE -ne 0) {
    throw "Installer build failed with exit code $LASTEXITCODE"
}

Write-Host "Installer created: $DeployRoot\installer\CollegeFinanceManager-Setup-0.2.0.exe"
