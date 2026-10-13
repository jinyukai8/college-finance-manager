from __future__ import annotations

import sqlite3

import pytest


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
    assert database.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 1
    assert database.execute("SELECT count(*) FROM ledgers").fetchone()[0] == 0
    assert database.execute("SELECT count(*) FROM transactions").fetchone()[0] == 0


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
