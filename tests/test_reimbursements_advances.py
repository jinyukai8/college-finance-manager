from datetime import date

import pytest

from college_finance_manager.application.advances import (
    AdvanceRuleError,
    create_advance,
    get_advance_breakdown,
    pay_advance,
    record_refund,
    record_settlement,
)
from college_finance_manager.application.initialize_ledger import InitializeLedgerCommand, initialize_ledger
from college_finance_manager.application.reimbursements import (
    create_reimbursement,
    mark_awaiting_payment,
    pay_reimbursement,
)
from college_finance_manager.application.transactions import get_cash_totals


def _book(database, tmp_path):
    ledger = initialize_ledger(database, InitializeLedgerCommand("账本", date(2026, 1, 1), 100_000, str(tmp_path)))
    income = database.execute("SELECT id FROM categories WHERE ledger_id=? AND type='income'", (ledger,)).fetchone()[0]
    expense = database.execute("SELECT id FROM categories WHERE ledger_id=? AND type='expense'", (ledger,)).fetchone()[0]
    return ledger, income, expense


def test_reimbursement_does_not_affect_cash_until_paid_and_retry_is_idempotent(database, tmp_path):
    ledger, _, expense = _book(database, tmp_path)
    reimbursement = create_reimbursement(
        database, ledger_id=ledger, applicant="张三", amount_cents=30_000,
        purpose="活动材料", applied_on=date(2026, 1, 2),
    )
    assert get_cash_totals(database, ledger).balance_cents == 100_000
    mark_awaiting_payment(database, reimbursement)
    first = pay_reimbursement(database, reimbursement, category_id=expense, paid_on=date(2026, 1, 3), idempotency_key="pay-r1")
    second = pay_reimbursement(database, reimbursement, category_id=expense, paid_on=date(2026, 1, 3), idempotency_key="pay-r1")
    assert first == second
    assert get_cash_totals(database, ledger).balance_cents == 70_000
    assert database.execute("SELECT count(*) FROM transactions WHERE source='reimbursement'").fetchone()[0] == 1


def test_advance_500_settle_460_refund_40(database, tmp_path):
    ledger, income, expense = _book(database, tmp_path)
    advance = create_advance(
        database, ledger_id=ledger, recipient="李四", amount_cents=50_000,
        purpose="会议采购", requested_on=date(2026, 1, 2),
    )
    pay_advance(database, advance, category_id=expense, paid_on=date(2026, 1, 2), idempotency_key="pay-a1")
    assert get_cash_totals(database, ledger).balance_cents == 50_000
    record_settlement(
        database, advance, amount_cents=46_000, occurred_on=date(2026, 1, 5),
        category_id=expense, note="发票核销", idempotency_key="settle-a1",
    )
    assert get_cash_totals(database, ledger).balance_cents == 50_000
    _, refund_tx = record_refund(
        database, advance, amount_cents=4_000, occurred_on=date(2026, 1, 6),
        income_category_id=income, note="收到退款", idempotency_key="refund-a1",
    )
    assert refund_tx
    assert get_cash_totals(database, ledger).balance_cents == 54_000
    assert get_advance_breakdown(database, advance)["remaining_cents"] == 0
    assert database.execute("SELECT status FROM advances WHERE id=?", (advance,)).fetchone()[0] == "settled"


def test_advance_overage_is_rejected_without_partial_cash_write(database, tmp_path):
    ledger, income, expense = _book(database, tmp_path)
    advance = create_advance(
        database, ledger_id=ledger, recipient="李四", amount_cents=50_000,
        purpose="采购", requested_on=date(2026, 1, 2),
    )
    pay_advance(database, advance, category_id=expense, paid_on=date(2026, 1, 2), idempotency_key="pay-a2")
    record_settlement(
        database, advance, amount_cents=47_000, occurred_on=date(2026, 1, 5),
        category_id=expense, note="", idempotency_key="settle-a2",
    )
    before = get_cash_totals(database, ledger)
    with pytest.raises(AdvanceRuleError):
        record_refund(
            database, advance, amount_cents=4_000, occurred_on=date(2026, 1, 6),
            income_category_id=income, note="", idempotency_key="refund-too-much",
        )
    after = get_cash_totals(database, ledger)
    assert after == before
    assert database.execute("SELECT count(*) FROM transactions WHERE source='advance_refund'").fetchone()[0] == 0
