from pathlib import Path

import pytest

from college_finance_manager.infrastructure import paths


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16"])
def test_installed_exe_uses_adjacent_setting_from_any_working_directory(tmp_path, monkeypatch, encoding):
    install = tmp_path / "程序"
    ledger = tmp_path / "自选账本 100%"
    install.mkdir()
    ledger.mkdir()
    (install / "ledger-paths.ini").write_text(f"[Paths]\nDataDir={ledger}\n", encoding=encoding)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(paths, "_legacy_installed_data_dir", lambda: str(tmp_path / "other"))

    selected = paths.resolve_startup_paths(executable=install / "CollegeFinanceManager.exe")
    assert selected.root == ledger
    assert selected.database == ledger / "finance.db"


def test_explicit_directory_overrides_even_a_broken_installed_config(tmp_path):
    (tmp_path / "ledger-paths.ini").write_text("invalid", encoding="utf-8")
    alternate = tmp_path / "isolated-test"
    selected = paths.resolve_startup_paths(alternate, executable=tmp_path / "app.exe")
    assert selected.root == alternate
    assert not alternate.exists()


def test_legacy_registry_is_used_only_for_packaged_launch(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "_legacy_installed_data_dir", lambda: str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert paths.resolve_startup_paths(executable=tmp_path / "app.exe").root == tmp_path
    assert paths.resolve_startup_paths() is None
    assert not (tmp_path / "local").exists()


def test_missing_configured_directory_is_not_silently_created_or_replaced(tmp_path, monkeypatch):
    (tmp_path / "ledger-paths.ini").write_text("[Paths]\nDataDir=offline-drive\n", encoding="utf-8")
    monkeypatch.setattr(paths, "_legacy_installed_data_dir", lambda: str(tmp_path))
    with pytest.raises(paths.DataDirectoryError, match="offline-drive"):
        paths.resolve_startup_paths(executable=tmp_path / "app.exe")
    assert not (tmp_path / "offline-drive").exists()


def test_migration_mismatch_is_reported_without_switching_ledgers(tmp_path, monkeypatch):
    import importlib

    from college_finance_manager.infrastructure.database import apply_migrations, connect_database

    application = importlib.import_module("college_finance_manager.main")
    ledger = tmp_path / "selected"
    ledger.mkdir()
    connection = connect_database(ledger / "finance.db")
    try:
        apply_migrations(connection)
        old_checksum = "0" * 64
        connection.execute(
            "UPDATE schema_migrations SET checksum_sha256 = ? WHERE version = '0001_initial'",
            (old_checksum,),
        )
    finally:
        connection.close()
    messages = []
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setattr(application.QMessageBox, "critical", lambda _, title, text: messages.append((title, text)))
    assert application.main(["--data-dir", str(ledger)]) == 2
    assert len(messages) == 1
    assert str(ledger) in messages[0][1]
    assert "0001_initial" in messages[0][1]
    connection = connect_database(ledger / "finance.db")
    try:
        assert connection.execute(
            "SELECT checksum_sha256 FROM schema_migrations WHERE version = '0001_initial'"
        ).fetchone()[0] == old_checksum
    finally:
        connection.close()
