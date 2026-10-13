from __future__ import annotations

from datetime import date

import pytest

from college_finance_manager.application.initialize_ledger import InitializeLedgerCommand, initialize_ledger
from college_finance_manager.application.transactions import (
    CreateTransactionCommand,
    TransactionFilter,
    TransactionRuleError,
    create_direct_transaction,
    get_cash_totals,
    list_transactions,
    rename_category,
    reverse_transaction,
    void_unrealized_transaction,
    create_category,
    set_category_active,
)
from college_finance_manager.application.read_models import get_dashboard_data, list_recycle_bin_records


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


def test_categories_can_be_added_and_deactivated_without_deleting_history(database, tmp_path):
    ledger_id, categories = _initialized(database, tmp_path)
    category_id = create_category(database, ledger_id, "expense", "宣传印刷")
    transaction_id = _record(database, ledger_id, category_id, "expense", 500, "category-history")
    set_category_active(database, category_id, False)
    assert database.execute("SELECT is_active FROM categories WHERE id=?", (category_id,)).fetchone()[0] == 0
    assert database.execute("SELECT category_name_snapshot FROM transactions WHERE id=?", (transaction_id,)).fetchone()[0] == "宣传印刷"
    with pytest.raises(TransactionRuleError):
        _record(database, ledger_id, category_id, "expense", 500, "inactive-new")


def test_direct_transaction_stores_optional_item_and_searches_it(database, tmp_path):
    ledger_id, categories = _initialized(database, tmp_path)
    transaction_id = create_direct_transaction(
        database,
        CreateTransactionCommand(
            ledger_id=ledger_id,
            occurred_on=date(2026, 1, 2),
            direction="expense",
            amount_cents=888,
            category_id=categories["expense"],
            purpose="运动会用品",
            item="篮球",
            idempotency_key="item-search",
        ),
    )
    stored = database.execute("SELECT item FROM transactions WHERE id=?", (transaction_id,)).fetchone()[0]
    assert stored == "篮球"
    rows = list_transactions(database, ledger_id, TransactionFilter(keyword="篮球"))
    assert [row["id"] for row in rows] == [transaction_id]
    assert rows[0]["attachment_count"] == 0


def test_voided_transaction_is_hidden_from_active_views_and_kept_in_recycle_bin(database, tmp_path):
    ledger_id, categories = _initialized(database, tmp_path)
    transaction_id = _record(database, ledger_id, categories["expense"], "expense", 500, "void-view")
    void_unrealized_transaction(database, transaction_id, "测试误录")

    assert list_transactions(database, ledger_id) == []
    assert list_transactions(
        database, ledger_id, TransactionFilter(include_voided=True)
    )[0]["status"] == "voided"
    dashboard = get_dashboard_data(database, ledger_id, "2026-01")
    assert dashboard["recent"] == []
    recycle = list_recycle_bin_records(database, ledger_id)
    assert len(recycle) == 1
    assert recycle[0]["record_no"] == "TX-00000001"
    assert recycle[0]["reason"] == "测试误录"
