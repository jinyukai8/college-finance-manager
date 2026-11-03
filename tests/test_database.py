from __future__ import annotations

import hashlib
import sqlite3
from importlib.resources import files

import pytest

from college_finance_manager.infrastructure.database import MigrationError, apply_migration_script


EXPECTED_TABLES = {
    "ledgers",
    "categories",
    "transactions",
    "reimbursements",
    "advances",
    "advance_events",
    "attachments",
    "audit_logs",
    "reconciliations",
    "settings",
    "schema_migrations",
}


def test_database_pragmas(database):
    assert database.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert database.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert database.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_initial_migration_creates_expected_tables_without_demo_data(database):
    tables = {
        row[0]
        for row in database.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert EXPECTED_TABLES <= tables
    assert database.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 4
    assert database.execute("SELECT count(*) FROM ledgers").fetchone()[0] == 0
    assert database.execute("SELECT count(*) FROM transactions").fetchone()[0] == 0
    columns = {row["name"] for row in database.execute("PRAGMA table_info(transactions)")}
    assert "item" in columns
    assert "correction_of_id" in columns


def test_amount_and_enum_constraints_are_enforced(database):
    database.execute(
        """INSERT INTO ledgers VALUES
           ('ledger', '测试', '2026-01-01', 0, '2026-01-01T00:00:00+08:00', '2026-01-01T00:00:00+08:00')"""
    )
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            """INSERT INTO transactions
               (id, ledger_id, transaction_no, occurred_on, direction, amount_cents,
                purpose, status, source, created_at, updated_at)
               VALUES ('t', 'ledger', '0001', '2026-01-01', 'income', 0,
                       '无效金额', 'active', 'direct', 'now', 'now')"""
        )
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            """INSERT INTO categories
               (id, ledger_id, type, name, is_active, created_at, updated_at)
               VALUES ('c', 'ledger', 'unknown', '测试', 1, 'now', 'now')"""
        )


def test_failed_migration_rolls_back_and_preserves_existing_data(database):
    database.execute(
        """INSERT INTO ledgers VALUES
           ('safe', '历史账本', '2026-01-01', 12345, 'now', 'now')"""
    )
    with pytest.raises(MigrationError):
        apply_migration_script(
            database,
            version="9999_broken",
            sql="CREATE TABLE should_rollback(id INTEGER); INVALID SQL;",
        )
    assert database.execute("SELECT name FROM ledgers WHERE id='safe'").fetchone()[0] == "历史账本"
    assert database.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='should_rollback'"
    ).fetchone() is None
    assert database.execute(
        "SELECT 1 FROM schema_migrations WHERE version='9999_broken'"
    ).fetchone() is None


def test_sequential_migrations_preserve_existing_transaction(tmp_path):
    from college_finance_manager.infrastructure.database import apply_migrations, connect_database

    connection = connect_database(tmp_path / "upgrade.db")
    connection.execute(
        """CREATE TABLE schema_migrations (
               version TEXT PRIMARY KEY,
               applied_at TEXT NOT NULL,
               checksum_sha256 TEXT NOT NULL CHECK(length(checksum_sha256) = 64)
           )"""
    )
    resource = files("college_finance_manager.infrastructure.migrations").joinpath("0001_initial.sql")
    sql = resource.read_text(encoding="utf-8")
    apply_migration_script(
        connection,
        version="0001_initial",
        sql=sql,
        checksum=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
    )
    connection.execute(
        """INSERT INTO ledgers VALUES
           ('ledger', '历史账本', '2026-01-01', 0, 'now', 'now')"""
    )
    connection.execute(
        """INSERT INTO transactions
           (id, ledger_id, transaction_no, occurred_on, direction, amount_cents,
            purpose, status, source, created_at, updated_at)
           VALUES ('tx', 'ledger', 'TX-00000001', '2026-01-01', 'expense', 100,
                   '历史用途', 'active', 'direct', 'now', 'now')"""
    )
    apply_migrations(connection)
    row = connection.execute(
        "SELECT purpose, item, correction_of_id FROM transactions WHERE id='tx'"
    ).fetchone()
    assert tuple(row) == ("历史用途", None, None)
    connection.close()
