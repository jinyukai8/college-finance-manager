param(
    [string]$DeployRoot = (Join-Path $PSScriptRoot "..\build\windows"),
    [string]$CompilerPath
)

$ErrorActionPreference = "Stop"
$SourceRoot = Split-Path -Parent $PSScriptRoot
$DeployRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($DeployRoot)
$InstallerScript = Join-Path $SourceRoot "installer\CollegeFinanceManager.iss"

if ($CompilerPath) {
    $Compiler = (Resolve-Path -LiteralPath $CompilerPath).ProviderPath
}
else {
    $Candidates = @(
        Get-Command ISCC.exe -CommandType Application -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty Source
        foreach ($Folder in "ProgramFilesX86", "ProgramFiles") {
            $ProgramFilesDir = [Environment]::GetFolderPath($Folder)
            if ($ProgramFilesDir) { Join-Path $ProgramFilesDir "Inno Setup 6\ISCC.exe" }
        }
    )
    $Compiler = $Candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
        Select-Object -First 1
    if (-not $Compiler) {
        throw "Inno Setup 6 was not found. Specify the full ISCC.exe path with -CompilerPath."
    }
}

& (Join-Path $PSScriptRoot "build_windows.ps1") -DeployRoot $DeployRoot
$ApplicationDir = Join-Path $DeployRoot "dist\CollegeFinanceManager"
$InstallerDir = Join-Path $DeployRoot "installer"
$BuildTemp = Join-Path $DeployRoot "build\tmp"
New-Item -ItemType Directory -Force -Path $InstallerDir, $BuildTemp | Out-Null
$PreviousBuildTemp = $env:TEMP
$PreviousBuildTmp = $env:TMP
try {
    $env:TEMP = $BuildTemp
    $env:TMP = $BuildTemp
    & $Compiler "/DBuildSourceDir=$ApplicationDir" "/DInstallerOutputDir=$InstallerDir" $InstallerScript
    if ($LASTEXITCODE -ne 0) {
        throw "Installer build failed with exit code $LASTEXITCODE"
    }
}
finally {
    $env:TEMP = $PreviousBuildTemp
    $env:TMP = $PreviousBuildTmp
}

Write-Host "Installer output directory: $InstallerDir"
