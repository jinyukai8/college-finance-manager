from __future__ import annotations

import sqlite3
from datetime import date, datetime
from uuid import uuid4

from college_finance_manager.application.transactions import _audit, insert_linked_cash_transaction


class ReimbursementRuleError(ValueError):
    pass


def create_reimbursement(
    connection: sqlite3.Connection,
    *,
    ledger_id: str,
    applicant: str,
    amount_cents: int,
    purpose: str,
    applied_on: date,
    note: str = "",
) -> str:
    if not applicant.strip() or not purpose.strip() or amount_cents <= 0:
        raise ReimbursementRuleError("申请人、正金额和用途均为必填")
    reimbursement_id = str(uuid4())
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """INSERT INTO reimbursements
               (id, ledger_id, applicant, amount_cents, purpose, applied_on, status, note, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
            (reimbursement_id, ledger_id, applicant.strip(), amount_cents, purpose.strip(), applied_on.isoformat(), note.strip() or None, now, now),
        )
        _audit(connection, ledger_id, "reimbursement", reimbursement_id, "created", {"amount_cents": amount_cents})
        connection.commit()
        return reimbursement_id
    except Exception:
        connection.rollback()
        raise


def mark_awaiting_payment(connection: sqlite3.Connection, reimbursement_id: str) -> None:
    _change_status(connection, reimbursement_id, "pending", "awaiting_payment", "approved")


def _change_status(connection, reimbursement_id, expected, target, action, reason=None):
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM reimbursements WHERE id = ?", (reimbursement_id,)).fetchone()
        if not row or row["status"] != expected:
            raise ReimbursementRuleError("报销状态不允许此操作")
        connection.execute(
            "UPDATE reimbursements SET status = ?, decision_reason = ?, updated_at = ? WHERE id = ?",
            (target, reason, datetime.now().astimezone().isoformat(timespec="seconds"), reimbursement_id),
        )
        _audit(connection, row["ledger_id"], "reimbursement", reimbursement_id, action, {"from": expected, "to": target}, reason)
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def cancel_reimbursement(connection: sqlite3.Connection, reimbursement_id: str, reason: str) -> None:
    reason = reason.strip()
    if not reason:
        raise ReimbursementRuleError("取消原因不能为空")
    row = connection.execute("SELECT status FROM reimbursements WHERE id = ?", (reimbursement_id,)).fetchone()
    if not row or row["status"] not in {"pending", "awaiting_payment"}:
        raise ReimbursementRuleError("当前报销不可取消")
    _change_status(connection, reimbursement_id, row["status"], "cancelled", "cancelled", reason)


def pay_reimbursement(
    connection: sqlite3.Connection,
    reimbursement_id: str,
    *,
    category_id: str,
    paid_on: date,
    idempotency_key: str,
) -> str:
    if not idempotency_key.strip():
        raise ReimbursementRuleError("付款必须提供幂等键")
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM reimbursements WHERE id = ?", (reimbursement_id,)).fetchone()
        if not row:
            raise ReimbursementRuleError("报销不存在")
        if row["status"] == "completed" and row["payment_transaction_id"]:
            connection.commit()
            return row["payment_transaction_id"]
        if row["status"] != "awaiting_payment":
            raise ReimbursementRuleError("只有待付款报销可确认付款")
        transaction_id = insert_linked_cash_transaction(
            connection, ledger_id=row["ledger_id"], occurred_on=paid_on, direction="expense",
            amount_cents=row["amount_cents"], category_id=category_id,
            purpose=f"报销：{row['purpose']}", source="reimbursement", idempotency_key=idempotency_key,
            handler=row["applicant"], note=f"关联报销 {reimbursement_id}",
        )
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        connection.execute(
            """UPDATE reimbursements SET status = 'completed', paid_on = ?, payment_transaction_id = ?, updated_at = ?
               WHERE id = ?""",
            (paid_on.isoformat(), transaction_id, now, reimbursement_id),
        )
        _audit(connection, row["ledger_id"], "reimbursement", reimbursement_id, "paid", {"transaction_id": transaction_id})
        connection.commit()
        return transaction_id
    except Exception:
        connection.rollback()
        raise
