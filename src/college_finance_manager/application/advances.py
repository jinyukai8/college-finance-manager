from __future__ import annotations

import sqlite3
from datetime import date, datetime
from uuid import uuid4

from college_finance_manager.application.transactions import _audit, insert_linked_cash_transaction


class AdvanceRuleError(ValueError):
    pass


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def create_advance(connection, *, ledger_id, recipient, amount_cents, purpose, requested_on, note="") -> str:
    if not recipient.strip() or not purpose.strip() or amount_cents <= 0:
        raise AdvanceRuleError("收款人、正金额和用途均为必填")
    advance_id = str(uuid4())
    try:
        connection.execute("BEGIN IMMEDIATE")
        now = _now()
        connection.execute(
            """INSERT INTO advances
               (id, ledger_id, recipient, amount_cents, purpose, requested_on, status, note, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending_payment', ?, ?, ?)""",
            (advance_id, ledger_id, recipient.strip(), amount_cents, purpose.strip(), requested_on.isoformat(), note.strip() or None, now, now),
        )
        _audit(connection, ledger_id, "advance", advance_id, "created", {"amount_cents": amount_cents})
        connection.commit()
        return advance_id
    except Exception:
        connection.rollback()
        raise


def pay_advance(connection, advance_id, *, category_id, paid_on, idempotency_key) -> str:
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM advances WHERE id = ?", (advance_id,)).fetchone()
        if not row:
            raise AdvanceRuleError("预付款不存在")
        if row["payment_transaction_id"]:
            connection.commit()
            return row["payment_transaction_id"]
        if row["status"] != "pending_payment":
            raise AdvanceRuleError("当前预付款不可支付")
        transaction_id = insert_linked_cash_transaction(
            connection, ledger_id=row["ledger_id"], occurred_on=paid_on, direction="expense",
            amount_cents=row["amount_cents"], category_id=category_id,
            purpose=f"预付款：{row['purpose']}", source="advance_payment", idempotency_key=idempotency_key,
            handler=row["recipient"], note=f"关联预付款 {advance_id}",
        )
        connection.execute(
            """UPDATE advances SET status = 'pending_settlement', paid_on = ?, payment_transaction_id = ?, updated_at = ?
               WHERE id = ?""",
            (paid_on.isoformat(), transaction_id, _now(), advance_id),
        )
        _audit(connection, row["ledger_id"], "advance", advance_id, "paid", {"transaction_id": transaction_id})
        connection.commit()
        return transaction_id
    except Exception:
        connection.rollback()
        raise


def cancel_advance(connection, advance_id: str, reason: str) -> None:
    reason = reason.strip()
    if not reason:
        raise AdvanceRuleError("取消原因不能为空")
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM advances WHERE id=?", (advance_id,)).fetchone()
        if not row or row["status"] != "pending_payment":
            raise AdvanceRuleError("只有待支付预付款可取消")
        connection.execute(
            "UPDATE advances SET status='cancelled', cancel_reason=?, updated_at=? WHERE id=?",
            (reason, _now(), advance_id),
        )
        _audit(connection, row["ledger_id"], "advance", advance_id, "cancelled", {"from": "pending_payment"}, reason)
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def _used_amount(connection, advance_id) -> int:
    return connection.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM advance_events WHERE advance_id = ?", (advance_id,)
    ).fetchone()[0]


def record_settlement(connection, advance_id, *, amount_cents, occurred_on, category_id, note, idempotency_key) -> str:
    return _record_event(
        connection, advance_id, event_type="settlement", amount_cents=amount_cents,
        occurred_on=occurred_on, category_id=category_id, note=note,
        idempotency_key=idempotency_key, refund_category_id=None,
    )[0]


def record_refund(connection, advance_id, *, amount_cents, occurred_on, income_category_id, note, idempotency_key) -> tuple[str, str]:
    return _record_event(
        connection, advance_id, event_type="refund", amount_cents=amount_cents,
        occurred_on=occurred_on, category_id=None, note=note,
        idempotency_key=idempotency_key, refund_category_id=income_category_id,
    )


def _record_event(
    connection, advance_id, *, event_type, amount_cents, occurred_on,
    category_id, note, idempotency_key, refund_category_id,
) -> tuple[str, str | None]:
    if amount_cents <= 0 or not idempotency_key.strip():
        raise AdvanceRuleError("金额必须大于零且操作必须可幂等")
    try:
        connection.execute("BEGIN IMMEDIATE")
        duplicate = connection.execute(
            "SELECT id, refund_transaction_id FROM advance_events WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        if duplicate:
            connection.commit()
            return duplicate["id"], duplicate["refund_transaction_id"]
        advance = connection.execute("SELECT * FROM advances WHERE id = ?", (advance_id,)).fetchone()
        if not advance or advance["status"] not in {"pending_settlement", "partially_settled"}:
            raise AdvanceRuleError("当前预付款不可核销或退款")
        used = _used_amount(connection, advance_id)
        if used + amount_cents > advance["amount_cents"]:
            raise AdvanceRuleError("核销与退款累计不可超过预付金额")
        category_name = None
        refund_transaction_id = None
        if event_type == "settlement":
            category = connection.execute(
                "SELECT name, type, is_active FROM categories WHERE id = ? AND ledger_id = ?",
                (category_id, advance["ledger_id"]),
            ).fetchone()
            if not category or category["type"] != "expense" or not category["is_active"]:
                raise AdvanceRuleError("核销费用类别无效")
            category_name = category["name"]
        else:
            refund_transaction_id = insert_linked_cash_transaction(
                connection, ledger_id=advance["ledger_id"], occurred_on=occurred_on, direction="income",
                amount_cents=amount_cents, category_id=refund_category_id,
                purpose=f"预付款退款：{advance['purpose']}", source="advance_refund",
                idempotency_key=f"cash:{idempotency_key}", handler=advance["recipient"], note=note,
            )
        event_id = str(uuid4())
        connection.execute(
            """INSERT INTO advance_events
               (id, advance_id, event_type, amount_cents, occurred_on, category_id,
                category_name_snapshot, note, refund_transaction_id, idempotency_key, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, advance_id, event_type, amount_cents, occurred_on.isoformat(), category_id,
             category_name, note.strip() or None, refund_transaction_id, idempotency_key, _now()),
        )
        total_used = used + amount_cents
        status = "settled" if total_used == advance["amount_cents"] else "partially_settled"
        connection.execute("UPDATE advances SET status = ?, updated_at = ? WHERE id = ?", (status, _now(), advance_id))
        _audit(
            connection, advance["ledger_id"], "advance", advance_id, event_type,
            {"event_id": event_id, "amount_cents": amount_cents, "remaining_cents": advance["amount_cents"] - total_used},
        )
        connection.commit()
        return event_id, refund_transaction_id
    except Exception:
        connection.rollback()
        raise


def get_advance_breakdown(connection, advance_id) -> dict[str, int]:
    advance = connection.execute("SELECT amount_cents FROM advances WHERE id = ?", (advance_id,)).fetchone()
    if not advance:
        raise AdvanceRuleError("预付款不存在")
    row = connection.execute(
        """SELECT
               COALESCE(SUM(CASE WHEN event_type = 'settlement' THEN amount_cents ELSE 0 END), 0) AS settled,
               COALESCE(SUM(CASE WHEN event_type = 'refund' THEN amount_cents ELSE 0 END), 0) AS refunded
           FROM advance_events WHERE advance_id = ?""",
        (advance_id,),
    ).fetchone()
    return {
        "amount_cents": advance["amount_cents"],
        "settled_cents": row["settled"],
        "refunded_cents": row["refunded"],
        "remaining_cents": advance["amount_cents"] - row["settled"] - row["refunded"],
    }
