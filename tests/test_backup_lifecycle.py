from datetime import date

import pytest

from college_finance_manager.application.initialize_ledger import InitializeLedgerCommand, initialize_ledger
from college_finance_manager.infrastructure.backup import (
    BackupValidationError,
    create_complete_backup,
    create_daily_backup_if_needed,
    restore_backup_in_place,
    validate_backup,
)
from college_finance_manager.infrastructure.database import apply_migrations, connect_database
from college_finance_manager.infrastructure.paths import AppPaths
from college_finance_manager.infrastructure.single_instance import AlreadyRunningError, SingleInstanceLock


def test_single_instance_lock_rejects_second_owner(tmp_path):
    first = SingleInstanceLock(tmp_path / "app.lock")
    second = SingleInstanceLock(tmp_path / "app.lock")
    first.acquire()
    try:
        with pytest.raises(AlreadyRunningError):
            second.acquire()
    finally:
        first.release()
    second.acquire()
    second.release()


def test_daily_backup_runs_once_and_applies_retention(database, tmp_path):
    ledger = initialize_ledger(database, InitializeLedgerCommand("账本", date.today(), 0, str(tmp_path)))
    paths = AppPaths.from_root(tmp_path / "app")
    paths.ensure_directories()
    assert create_daily_backup_if_needed(database, paths=paths, today=date(2026, 1, 1), retention_count=2)
    assert create_daily_backup_if_needed(database, paths=paths, today=date(2026, 1, 1), retention_count=2) is None
    assert create_daily_backup_if_needed(database, paths=paths, today=date(2026, 1, 2), retention_count=2)
    assert create_daily_backup_if_needed(database, paths=paths, today=date(2026, 1, 3), retention_count=2)
    assert [p.name for p in sorted(tmp_path.glob("auto-*.cfmbackup"))] == [
        "auto-2026-01-02.cfmbackup", "auto-2026-01-03.cfmbackup"
    ]
    assert database.execute("SELECT id FROM ledgers").fetchone()[0] == ledger


def test_backup_rejects_missing_attachment_listed_by_database(database, tmp_path):
    ledger = initialize_ledger(database, InitializeLedgerCommand("账本", date.today(), 0, str(tmp_path)))
    database.execute(
        """INSERT INTO attachments
           (id,ledger_id,entity_type,entity_id,internal_path,original_name,media_type,sha256,size_bytes,imported_at)
           VALUES ('a',?,'reimbursement','missing','missing.pdf','x.pdf','application/pdf',?,4,'now')""",
        (ledger, "0" * 64),
    )
    with pytest.raises(BackupValidationError):
        create_complete_backup(
            database,
            attachments_root=tmp_path / "attachments",
            destination=tmp_path / "bad.cfmbackup",
        )


def test_in_place_restore_preserves_previous_data_in_recovery(tmp_path):
    current_paths = AppPaths.from_root(tmp_path / "current")
    current_paths.ensure_directories()
    current = connect_database(current_paths.database)
    apply_migrations(current)
    initialize_ledger(current, InitializeLedgerCommand("当前账本", date.today(), 100, str(current_paths.backups)))
    current.close()

    source_paths = AppPaths.from_root(tmp_path / "source")
    source_paths.ensure_directories()
    source = connect_database(source_paths.database)
    apply_migrations(source)
    initialize_ledger(source, InitializeLedgerCommand("恢复账本", date.today(), 200, str(source_paths.backups)))
    backup = create_complete_backup(source, attachments_root=source_paths.attachments, destination=tmp_path / "restore.cfmbackup")
    source.close()

    recovery = restore_backup_in_place(backup, current_paths)
    restored = connect_database(current_paths.database)
    try:
        assert restored.execute("SELECT name FROM ledgers").fetchone()[0] == "恢复账本"
    finally:
        restored.close()
    old = connect_database(recovery / "finance.db")
    try:
        assert old.execute("SELECT name FROM ledgers").fetchone()[0] == "当前账本"
    finally:
        old.close()
