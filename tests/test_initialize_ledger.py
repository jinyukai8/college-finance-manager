from datetime import date

import pytest

from college_finance_manager.application.initialize_ledger import (
    DEFAULT_CATEGORIES,
    InitializeLedgerCommand,
    LedgerAlreadyInitialized,
    initialize_ledger,
)
from college_finance_manager.application.ledgers import rename_ledger


def test_initialize_ledger_is_atomic_and_contains_no_demo_transactions(database, tmp_path):
    ledger_id = initialize_ledger(
        database,
        InitializeLedgerCommand("学院账本", date(2026, 10, 1), 100_000, str(tmp_path / "backups")),
    )
    ledger = database.execute("SELECT * FROM ledgers WHERE id = ?", (ledger_id,)).fetchone()
    assert ledger["opening_balance_cents"] == 100_000
    assert database.execute("SELECT count(*) FROM categories").fetchone()[0] == len(DEFAULT_CATEGORIES)
    assert database.execute("SELECT count(*) FROM transactions").fetchone()[0] == 0
    assert database.execute("SELECT count(*) FROM audit_logs").fetchone()[0] == 1


def test_v1_rejects_second_ledger_without_partial_writes(database, tmp_path):
    command = InitializeLedgerCommand("第一本", date.today(), 0, str(tmp_path))
    initialize_ledger(database, command)
    with pytest.raises(LedgerAlreadyInitialized):
        initialize_ledger(database, InitializeLedgerCommand("第二本", date.today(), 0, str(tmp_path)))
    assert database.execute("SELECT count(*) FROM ledgers").fetchone()[0] == 1
    assert database.execute("SELECT count(*) FROM categories").fetchone()[0] == len(DEFAULT_CATEGORIES)


def test_rename_ledger_is_audited_and_preserves_financial_history(database, tmp_path):
    ledger_id = initialize_ledger(
        database,
        InitializeLedgerCommand("原账本", date(2026, 10, 1), 100_000, str(tmp_path)),
    )
    before = database.execute(
        "SELECT COUNT(*) FROM transactions WHERE ledger_id=?", (ledger_id,)
    ).fetchone()[0]

    rename_ledger(database, ledger_id, " 实验室账本 ")

    ledger = database.execute("SELECT * FROM ledgers WHERE id=?", (ledger_id,)).fetchone()
    audit = database.execute(
        """SELECT action, change_summary FROM audit_logs
           WHERE ledger_id=? AND entity_type='ledger' AND entity_id=?
           ORDER BY created_at DESC LIMIT 1""",
        (ledger_id, ledger_id),
    ).fetchone()
    assert ledger["name"] == "实验室账本"
    assert database.execute(
        "SELECT COUNT(*) FROM transactions WHERE ledger_id=?", (ledger_id,)
    ).fetchone()[0] == before
    assert audit["action"] == "renamed"
    assert '"from": "原账本"' in audit["change_summary"]
    assert '"to": "实验室账本"' in audit["change_summary"]


def test_rename_ledger_rejects_blank_name_without_changes(database, tmp_path):
    ledger_id = initialize_ledger(
        database,
        InitializeLedgerCommand("原账本", date(2026, 10, 1), 0, str(tmp_path)),
    )
    audit_count = database.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]

    with pytest.raises(ValueError, match="账本名称不能为空"):
        rename_ledger(database, ledger_id, "   ")

    assert database.execute("SELECT name FROM ledgers WHERE id=?", (ledger_id,)).fetchone()[0] == "原账本"
    assert database.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] == audit_count
