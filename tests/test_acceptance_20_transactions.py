from datetime import date

from college_finance_manager.application.initialize_ledger import InitializeLedgerCommand, initialize_ledger
from college_finance_manager.application.transactions import CreateTransactionCommand, create_direct_transaction, get_cash_totals, list_transactions


def test_twenty_cross_month_transactions_reconcile(database, tmp_path):
    ledger = initialize_ledger(
        database, InitializeLedgerCommand("跨月验收账本", date(2026, 1, 1), 10_000, str(tmp_path))
    )
    income = database.execute("SELECT id FROM categories WHERE ledger_id=? AND type='income'", (ledger,)).fetchone()[0]
    expense = database.execute("SELECT id FROM categories WHERE ledger_id=? AND type='expense'", (ledger,)).fetchone()[0]
    expected_income = 0
    expected_expense = 0
    for index in range(20):
        direction = "income" if index % 3 == 0 else "expense"
        amount = (index + 1) * 100
        occurred_on = date(2026, 1 + index // 7, 1 + index % 7)
        create_direct_transaction(
            database,
            CreateTransactionCommand(
                ledger_id=ledger, occurred_on=occurred_on, direction=direction, amount_cents=amount,
                category_id=income if direction == "income" else expense,
                purpose=f"跨月验收第 {index + 1} 笔", idempotency_key=f"acceptance-{index + 1}",
            ),
        )
        if direction == "income":
            expected_income += amount
        else:
            expected_expense += amount
    totals = get_cash_totals(database, ledger)
    assert len(list_transactions(database, ledger)) == 20
    assert totals.income_cents == expected_income
    assert totals.expense_cents == expected_expense
    assert totals.balance_cents == 10_000 + expected_income - expected_expense
    assert database.execute("SELECT count(*) FROM audit_logs WHERE entity_type='transaction'").fetchone()[0] == 20
