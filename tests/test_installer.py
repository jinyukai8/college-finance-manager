from pathlib import Path


def test_installer_allows_custom_program_and_data_directories():
    script = (
        Path(__file__).resolve().parents[1] / "installer" / "CollegeFinanceManager.iss"
    ).read_text(encoding="utf-8")

    assert "DisableDirPage=no" in script
    assert "DefaultDirName={localappdata}\\Programs\\{#MyAppName}" in script
    assert "CreateInputDirPage" in script
    assert 'Name: "{code:GetDataDir}"' in script
    assert 'Parameters: "--data-dir ""{code:GetDataDir}"""' in script
    assert 'ValueName: "DataDir"' in script

