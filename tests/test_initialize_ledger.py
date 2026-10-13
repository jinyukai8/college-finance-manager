from datetime import date

import pytest

from college_finance_manager.application.initialize_ledger import (
    DEFAULT_CATEGORIES,
    InitializeLedgerCommand,
    LedgerAlreadyInitialized,
    initialize_ledger,
)


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
