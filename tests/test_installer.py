from pathlib import Path


def test_installer_allows_custom_program_and_data_directories():
    script = (
        Path(__file__).resolve().parents[1] / "installer" / "CollegeFinanceManager.iss"
    ).read_text(encoding="utf-8")

    assert "DisableDirPage=no" in script
    assert "DefaultDirName={localappdata}\\Programs\\{#MyAppName}" in script
    assert "CreateInputDirPage" in script
    assert 'Name: "{code:GetDataDir}"; Flags: uninsneveruninstall' in script
    assert 'ValueName: "DataDir"' in script
    assert 'OutputDir={#InstallerOutputDir}' in script
    assert 'Source: "{#BuildSourceDir}\\*"' in script


def test_installer_launch_routes_share_the_configured_data_path():
    script = (
        Path(__file__).resolve().parents[1] / "installer" / "CollegeFinanceManager.iss"
    ).read_text(encoding="utf-8")

    assert "--data-dir" not in script
    assert "ledger-paths.ini" in script
    assert "SaveStringsToUTF8File" in script
    assert "CreateOrRefreshDesktopShortcut" in script

