from __future__ import annotations

from datetime import date

import pytest

from college_finance_manager.application.initialize_ledger import InitializeLedgerCommand, initialize_ledger
from college_finance_manager.application.transactions import (
    CreateTransactionCommand,
    TransactionRuleError,
    create_direct_transaction,
    get_cash_totals,
    rename_category,
    reverse_transaction,
    void_unrealized_transaction,
)


def _initialized(database, tmp_path, opening=100_000):
    ledger_id = initialize_ledger(
        database, InitializeLedgerCommand("测试账本", date(2026, 1, 1), opening, str(tmp_path))
    )
    categories = {
        row["type"]: row["id"]
        for row in database.execute("SELECT id, type FROM categories ORDER BY name")
    }
    return ledger_id, categories


def _record(database, ledger_id, category_id, direction, cents, key, purpose="测试"):
    return create_direct_transaction(
        database,
        CreateTransactionCommand(
            ledger_id=ledger_id,
            occurred_on=date(2026, 1, 2),
            direction=direction,
            amount_cents=cents,
            category_id=category_id,
            purpose=purpose,
            idempotency_key=key,
        ),
    )


def test_acceptance_balance_1000_plus_500_minus_200(database, tmp_path):
    ledger_id, categories = _initialized(database, tmp_path)
    _record(database, ledger_id, categories["income"], "income", 50_000, "income-1")
    _record(database, ledger_id, categories["expense"], "expense", 20_000, "expense-1")
    totals = get_cash_totals(database, ledger_id)
    assert totals.income_cents == 50_000
    assert totals.expense_cents == 20_000
    assert totals.balance_cents == 130_000


def test_duplicate_submit_is_idempotent(database, tmp_path):
    ledger_id, categories = _initialized(database, tmp_path)
    first = _record(database, ledger_id, categories["income"], "income", 100, "same-key")
    second = _record(database, ledger_id, categories["income"], "income", 100, "same-key")
    assert first == second
    assert database.execute("SELECT count(*) FROM transactions").fetchone()[0] == 1


def test_category_must_match_direction_and_be_active(database, tmp_path):
    ledger_id, categories = _initialized(database, tmp_path)
    with pytest.raises(TransactionRuleError):
        _record(database, ledger_id, categories["expense"], "income", 100, "bad-category")
    database.execute("UPDATE categories SET is_active = 0 WHERE id = ?", (categories["income"],))
    with pytest.raises(TransactionRuleError):
        _record(database, ledger_id, categories["income"], "income", 100, "inactive-category")
    assert database.execute("SELECT count(*) FROM transactions").fetchone()[0] == 0


def test_reversal_preserves_both_records_and_cancels_cash_effect(database, tmp_path):
    ledger_id, categories = _initialized(database, tmp_path)
    original_id = _record(database, ledger_id, categories["expense"], "expense", 20_000, "original")
    reversal_id = reverse_transaction(
        database, original_id, "金额录错，完整冲销", idempotency_key="reverse-once", occurred_on=date(2026, 1, 3)
    )
    assert reversal_id != original_id
    assert get_cash_totals(database, ledger_id).balance_cents == 100_000
    rows = list(database.execute("SELECT status, source, reversal_of_id FROM transactions ORDER BY created_at"))
    assert len(rows) == 2
    assert {row["status"] for row in rows} == {"reversed", "active"}
    assert any(row["reversal_of_id"] == original_id for row in rows)
    duplicate = reverse_transaction(
        database, original_id, "重试", idempotency_key="reverse-once", occurred_on=date(2026, 1, 3)
    )
    assert duplicate == reversal_id
    assert database.execute("SELECT count(*) FROM transactions").fetchone()[0] == 2


def test_void_keeps_trace_but_removes_unrealized_cash_effect(database, tmp_path):
    ledger_id, categories = _initialized(database, tmp_path)
    transaction_id = _record(database, ledger_id, categories["income"], "income", 10_000, "mistake")
    void_unrealized_transaction(database, transaction_id, "确认交易从未发生")
    row = database.execute("SELECT status, void_reason FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    assert tuple(row) == ("voided", "确认交易从未发生")
    assert get_cash_totals(database, ledger_id).balance_cents == 100_000
    assert database.execute("SELECT count(*) FROM audit_logs WHERE action = 'voided'").fetchone()[0] == 1


def test_category_rename_does_not_change_historical_snapshot(database, tmp_path):
    ledger_id, categories = _initialized(database, tmp_path)
    transaction_id = _record(database, ledger_id, categories["income"], "income", 100, "snapshot")
    before = database.execute(
        "SELECT category_name_snapshot FROM transactions WHERE id = ?", (transaction_id,)
    ).fetchone()[0]
    rename_category(database, categories["income"], "捐赠收入")
    after = database.execute(
        "SELECT category_name_snapshot FROM transactions WHERE id = ?", (transaction_id,)
    ).fetchone()[0]
    assert after == before
    assert database.execute("SELECT name FROM categories WHERE id = ?", (categories["income"],)).fetchone()[0] == "捐赠收入"


def test_negative_balance_is_recorded_not_rejected(database, tmp_path):
    ledger_id, categories = _initialized(database, tmp_path, opening=0)
    _record(database, ledger_id, categories["expense"], "expense", 100, "negative")
    totals = get_cash_totals(database, ledger_id)
    assert totals.balance_cents == -100
    assert totals.is_negative
