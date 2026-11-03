from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from uuid import uuid4

from college_finance_manager.domain.ledger import CashTotals


class TransactionRuleError(ValueError):
    pass


class TransactionNotFound(TransactionRuleError):
    pass


@dataclass(frozen=True, slots=True)
class CreateTransactionCommand:
    ledger_id: str
    occurred_on: date
    direction: str
    amount_cents: int
    category_id: str
    purpose: str
    item: str = ""
    handler: str = ""
    payment_method: str = ""
    note: str = ""
    idempotency_key: str = ""


@dataclass(frozen=True, slots=True)
class TransactionFilter:
    date_from: date | None = None
    date_to: date | None = None
    direction: str | None = None
    category_id: str | None = None
    amount_min_cents: int | None = None
    amount_max_cents: int | None = None
    handler: str = ""
    keyword: str = ""
    include_voided: bool = False


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def _audit(
    connection: sqlite3.Connection,
    ledger_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    summary: dict,
    reason: str | None = None,
) -> None:
    connection.execute(
        """INSERT INTO audit_logs
           (id, ledger_id, entity_type, entity_id, action, change_summary, reason, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            str(uuid4()), ledger_id, entity_type, entity_id, action,
            json.dumps(summary, ensure_ascii=False, sort_keys=True), reason, _now(),
        ),
    )


def _next_transaction_number(connection: sqlite3.Connection, ledger_id: str) -> str:
    row = connection.execute(
        "SELECT value FROM settings WHERE ledger_id = ? AND key = 'transaction_sequence'",
        (ledger_id,),
    ).fetchone()
    sequence = int(row["value"]) + 1 if row else 1
    now = _now()
    connection.execute(
        """INSERT INTO settings(ledger_id, key, value, updated_at)
           VALUES (?, 'transaction_sequence', ?, ?)
           ON CONFLICT(ledger_id, key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
        (ledger_id, str(sequence), now),
    )
    return f"TX-{sequence:08d}"


def create_direct_transaction(connection: sqlite3.Connection, command: CreateTransactionCommand) -> str:
    if command.direction not in {"income", "expense"}:
        raise TransactionRuleError("收支方向无效")
    if isinstance(command.amount_cents, bool) or not isinstance(command.amount_cents, int) or command.amount_cents <= 0:
        raise TransactionRuleError("金额必须是大于零的整数分")
    purpose = command.purpose.strip()
    if not purpose:
        raise TransactionRuleError("用途或来源不能为空")
    idempotency_key = command.idempotency_key.strip() or str(uuid4())

    try:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            "SELECT id FROM transactions WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        if existing:
            connection.commit()
            return existing["id"]
        transaction_id = insert_linked_cash_transaction(
            connection,
            ledger_id=command.ledger_id,
            occurred_on=command.occurred_on,
            direction=command.direction,
            amount_cents=command.amount_cents,
            category_id=command.category_id,
            purpose=purpose,
            item=command.item,
            source="direct",
            idempotency_key=idempotency_key,
            handler=command.handler,
            payment_method=command.payment_method,
            note=command.note,
        )
        connection.commit()
        return transaction_id
    except Exception:
        connection.rollback()
        raise


def get_cash_totals(connection: sqlite3.Connection, ledger_id: str) -> CashTotals:
    ledger = connection.execute(
        "SELECT opening_balance_cents FROM ledgers WHERE id = ?", (ledger_id,)
    ).fetchone()
    if not ledger:
        raise ValueError("账本不存在")
    row = connection.execute(
        """SELECT
               COALESCE(SUM(CASE WHEN direction = 'income' THEN amount_cents ELSE 0 END), 0) AS income,
               COALESCE(SUM(CASE WHEN direction = 'expense' THEN amount_cents ELSE 0 END), 0) AS expense
           FROM transactions
           WHERE ledger_id = ? AND status = 'active' AND source <> 'reversal'""",
        (ledger_id,),
    ).fetchone()
    return CashTotals(ledger["opening_balance_cents"], row["income"], row["expense"])


def _transaction_conditions(ledger_id, filters):
    filters = filters or TransactionFilter()
    clauses = ["ledger_id = ?"]
    parameters: list[object] = [ledger_id]
    if not filters.include_voided:
        clauses.extend(("status = 'active'", "source <> 'reversal'"))
    if filters.date_from:
        clauses.append("occurred_on >= ?")
        parameters.append(filters.date_from.isoformat())
    if filters.date_to:
        clauses.append("occurred_on <= ?")
        parameters.append(filters.date_to.isoformat())
    if filters.direction:
        clauses.append("direction = ?")
        parameters.append(filters.direction)
    if filters.category_id:
        clauses.append("category_id = ?")
        parameters.append(filters.category_id)
    if filters.amount_min_cents is not None:
        clauses.append("amount_cents >= ?")
        parameters.append(filters.amount_min_cents)
    if filters.amount_max_cents is not None:
        clauses.append("amount_cents <= ?")
        parameters.append(filters.amount_max_cents)
    if filters.handler.strip():
        clauses.append("COALESCE(handler, '') LIKE ? ESCAPE '\\'")
        parameters.append(f"%{_escape_like(filters.handler.strip())}%")
    if filters.keyword.strip():
        clauses.append(
            "(purpose LIKE ? ESCAPE '\\' OR COALESCE(item, '') LIKE ? ESCAPE '\\' "
            "OR COALESCE(note, '') LIKE ? ESCAPE '\\')"
        )
        pattern = f"%{_escape_like(filters.keyword.strip())}%"
        parameters.extend((pattern, pattern, pattern))
    return " AND ".join(clauses), parameters


def transaction_summary(connection, ledger_id, filters=None):
    where, parameters = _transaction_conditions(ledger_id, filters)
    row = connection.execute(
        f"""SELECT COUNT(*) AS count,
            COALESCE(SUM(CASE WHEN direction='income' THEN amount_cents ELSE 0 END), 0) AS income,
            COALESCE(SUM(CASE WHEN direction='expense' THEN amount_cents ELSE 0 END), 0) AS expense
            FROM transactions WHERE {where}""", parameters,
    ).fetchone()
    return row["income"], row["expense"], row["income"] - row["expense"], row["count"]


def list_transactions(
    connection: sqlite3.Connection, ledger_id: str, filters: TransactionFilter | None = None,
    *, limit: int = 500, offset: int = 0,
) -> list[sqlite3.Row]:
    where, parameters = _transaction_conditions(ledger_id, filters)
    return list(
        connection.execute(
            f"""SELECT transactions.*,
                       (SELECT COUNT(*) FROM attachments a
                        WHERE a.entity_type='transaction' AND a.entity_id=transactions.id AND a.archived_at IS NULL) AS attachment_count
                FROM transactions WHERE {where}
                ORDER BY occurred_on DESC, created_at DESC, id DESC LIMIT ? OFFSET ?""",
            (*parameters, limit, offset),
        )
    )


def insert_linked_cash_transaction(
    connection: sqlite3.Connection,
    *,
    ledger_id: str,
    occurred_on: date,
    direction: str,
    amount_cents: int,
    category_id: str,
    purpose: str,
    source: str,
    idempotency_key: str,
    item: str = "",
    handler: str = "",
    payment_method: str = "",
    note: str = "",
) -> str:
    """在调用方已开启的事务中插入现金流水，供原子业务用例使用。"""
    if source not in {"direct", "reimbursement", "advance_payment", "advance_refund", "correction"}:
        raise TransactionRuleError("流水来源无效")
    if direction not in {"income", "expense"} or amount_cents <= 0:
        raise TransactionRuleError("流水方向或金额无效")
    duplicate = connection.execute(
        "SELECT id FROM transactions WHERE idempotency_key = ?", (idempotency_key,)
    ).fetchone()
    if duplicate:
        return duplicate["id"]
    category = connection.execute(
        "SELECT name, type, is_active FROM categories WHERE id = ? AND ledger_id = ?",
        (category_id, ledger_id),
    ).fetchone()
    if not category or category["type"] != direction or not category["is_active"]:
        raise TransactionRuleError("类别不存在、已停用或与收支方向不匹配")
    transaction_id = str(uuid4())
    transaction_no = _next_transaction_number(connection, ledger_id)
    now = _now()
    connection.execute(
        """INSERT INTO transactions
           (id, ledger_id, transaction_no, occurred_on, direction, amount_cents,
            category_id, category_name_snapshot, purpose, item, handler, payment_method, note,
            status, source, idempotency_key, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)""",
        (
            transaction_id, ledger_id, transaction_no, occurred_on.isoformat(), direction, amount_cents,
            category_id, category["name"], purpose.strip(), item.strip() or None, handler.strip() or None,
            payment_method.strip() or None, note.strip() or None, source, idempotency_key, now, now,
        ),
    )
    _audit(
        connection, ledger_id, "transaction", transaction_id, "created",
        {"transaction_no": transaction_no, "direction": direction, "amount_cents": amount_cents, "source": source},
    )
    return transaction_id


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def reverse_transaction(
    connection: sqlite3.Connection,
    transaction_id: str,
    reason: str,
    *,
    idempotency_key: str,
    occurred_on: date,
) -> str:
    reason = reason.strip()
    if not reason:
        raise TransactionRuleError("冲销原因不能为空")
    if not idempotency_key.strip():
        raise TransactionRuleError("冲销必须提供幂等键")
    try:
        connection.execute("BEGIN IMMEDIATE")
        duplicate = connection.execute(
            "SELECT id FROM transactions WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        if duplicate:
            connection.commit()
            return duplicate["id"]
        original = connection.execute(
            "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        if not original:
            raise TransactionNotFound("原流水不存在")
        if original["status"] != "active" or original["source"] == "reversal":
            raise TransactionRuleError("该流水不可重复冲销")
        reversal_id = str(uuid4())
        number = _next_transaction_number(connection, original["ledger_id"])
        now = _now()
        direction = "expense" if original["direction"] == "income" else "income"
        connection.execute(
            """INSERT INTO transactions
               (id, ledger_id, transaction_no, occurred_on, direction, amount_cents,
                category_id, category_name_snapshot, purpose, item, handler, payment_method, note,
                status, source, reversal_of_id, idempotency_key, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 'reversal', ?, ?, ?, ?)""",
            (
                reversal_id, original["ledger_id"], number, occurred_on.isoformat(), direction,
                original["amount_cents"], original["category_id"], original["category_name_snapshot"],
                f"冲销 {original['transaction_no']}：{original['purpose']}", original["item"], original["handler"],
                original["payment_method"], reason, transaction_id, idempotency_key, now, now,
            ),
        )
        connection.execute(
            "UPDATE transactions SET status = 'reversed', updated_at = ? WHERE id = ?", (now, transaction_id)
        )
        _audit(connection, original["ledger_id"], "transaction", transaction_id, "reversed", {"reversal_id": reversal_id}, reason)
        _audit(connection, original["ledger_id"], "transaction", reversal_id, "created", {"source": "reversal", "original_id": transaction_id}, reason)
        connection.commit()
        return reversal_id
    except Exception:
        connection.rollback()
        raise


def correct_transaction_date(
    connection: sqlite3.Connection,
    transaction_id: str,
    new_date: date,
    reason: str,
    *,
    idempotency_key: str,
) -> str:
    if type(new_date) is not date:
        raise TransactionRuleError("更正日期无效")
    return _correct_transaction(
        connection, transaction_id, {"occurred_on": new_date}, reason,
        idempotency_key=idempotency_key, date_only=True,
    )


def _correct_transaction(connection, transaction_id, changes, reason, *, idempotency_key, date_only=False):
    """Correct a direct transaction without rewriting its historical values.

    The original is marked reversed, an equal and opposite record neutralizes it
    on its original date, and a linked correction recreates the cash effect on
    the requested date. Attachments follow the active correction record while
    their files remain unchanged.
    """
    reason = reason.strip()
    idempotency_key = idempotency_key.strip()
    if not reason:
        raise TransactionRuleError("更正原因不能为空")
    if not idempotency_key:
        raise TransactionRuleError("更正必须提供幂等键")

    try:
        connection.execute("BEGIN IMMEDIATE")
        duplicate = connection.execute(
            "SELECT id FROM transactions WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        if duplicate:
            connection.commit()
            return duplicate["id"]

        original = connection.execute(
            "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        if not original:
            raise TransactionNotFound("原流水不存在")
        if original["status"] != "active" or original["source"] not in {"direct", "correction"}:
            raise TransactionRuleError("仅有效的直接收支或更正流水可以编辑")

        ledger_id = original["ledger_id"]
        fields = ("occurred_on", "direction", "amount_cents", "category_id", "purpose", "item", "handler", "payment_method", "note")
        before = {field: original[field] for field in fields}
        after = {**before, **changes}
        if "occurred_on" in changes:
            if type(after["occurred_on"]) is not date:
                raise TransactionRuleError("日期无效")
            after["occurred_on"] = after["occurred_on"].isoformat()
        if type(after["amount_cents"]) is not int or not 0 < after["amount_cents"] <= 2**63 - 1:
            raise TransactionRuleError("金额必须为有效的正数")
        if after["direction"] not in {"income", "expense"} or not isinstance(after["purpose"], str) or not after["purpose"].strip():
            raise TransactionRuleError("收支方向或用途无效")
        for field in ("purpose", "item", "handler", "payment_method", "note"):
            value = after[field]
            if value is not None and not isinstance(value, str):
                raise TransactionRuleError("文本字段格式无效")
            after[field] = value.strip() or None if value is not None else None
        if after == before:
            raise TransactionRuleError("新日期必须与原日期不同" if date_only else "没有需要保存的修改")
        category_name = original["category_name_snapshot"]
        if after["category_id"] != before["category_id"] or after["direction"] != before["direction"]:
            category = connection.execute(
                "SELECT name FROM categories WHERE id=? AND ledger_id=? AND type=? AND is_active=1",
                (after["category_id"], ledger_id, after["direction"]),
            ).fetchone()
            if not category:
                raise TransactionRuleError("请选择与收支方向匹配的有效类别")
            category_name = category["name"]
        now = _now()
        reversal_id = str(uuid4())
        reversal_number = _next_transaction_number(connection, ledger_id)
        reversal_direction = "expense" if original["direction"] == "income" else "income"
        connection.execute(
            """INSERT INTO transactions
               (id, ledger_id, transaction_no, occurred_on, direction, amount_cents,
                category_id, category_name_snapshot, purpose, item, handler, payment_method, note,
                status, source, reversal_of_id, idempotency_key, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 'reversal', ?, ?, ?, ?)""",
            (
                reversal_id, ledger_id, reversal_number, original["occurred_on"], reversal_direction,
                original["amount_cents"], original["category_id"], original["category_name_snapshot"],
                f"{'日期' if date_only else ''}更正冲销 {original['transaction_no']}：{original['purpose']}", original["item"],
                original["handler"], original["payment_method"], reason, transaction_id,
                f"{idempotency_key}:reversal", now, now,
            ),
        )

        correction_id = str(uuid4())
        correction_number = _next_transaction_number(connection, ledger_id)
        connection.execute(
            """INSERT INTO transactions
               (id, ledger_id, transaction_no, occurred_on, direction, amount_cents,
                category_id, category_name_snapshot, purpose, item, handler, payment_method, note,
                status, source, correction_of_id, idempotency_key, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 'correction', ?, ?, ?, ?)""",
            (
                correction_id, ledger_id, correction_number, after["occurred_on"], after["direction"],
                after["amount_cents"], after["category_id"], category_name,
                after["purpose"], after["item"], after["handler"], after["payment_method"],
                after["note"], transaction_id, idempotency_key, now, now,
            ),
        )
        attachment_ids = [row["id"] for row in connection.execute(
            "SELECT id FROM attachments WHERE entity_type='transaction' AND entity_id=? AND archived_at IS NULL",
            (transaction_id,),
        )]
        connection.executemany(
            "INSERT OR IGNORE INTO transaction_attachment_history(transaction_id, attachment_id) VALUES (?, ?)",
            ((transaction_id, attachment_id) for attachment_id in attachment_ids),
        )
        moved_attachments = connection.execute(
            """UPDATE attachments SET entity_id = ?
               WHERE entity_type = 'transaction' AND entity_id = ? AND archived_at IS NULL""",
            (correction_id, transaction_id),
        ).rowcount
        connection.execute(
            "UPDATE transactions SET status = 'reversed', updated_at = ? WHERE id = ?",
            (now, transaction_id),
        )
        _audit(
            connection, ledger_id, "transaction", transaction_id, "date_corrected" if date_only else "edited",
            {
                "from": original["occurred_on"], "to": after["occurred_on"],
                "before": {**before, "category_name": original["category_name_snapshot"]},
                "after": {**after, "category_name": category_name},
                "reversal_id": reversal_id, "correction_id": correction_id,
                "moved_attachments": moved_attachments, "attachment_ids": attachment_ids,
            },
            reason,
        )
        _audit(
            connection, ledger_id, "transaction", reversal_id, "created",
            {"source": "reversal", "original_id": transaction_id, "reason": "date_correction" if date_only else "edit"},
            reason,
        )
        _audit(
            connection, ledger_id, "transaction", correction_id, "created",
            {"source": "correction", "original_id": transaction_id},
            reason,
        )
        connection.commit()
        return correction_id
    except Exception:
        connection.rollback()
        raise


def void_unrealized_transaction(connection: sqlite3.Connection, transaction_id: str, reason: str) -> None:
    reason = reason.strip()
    if not reason:
        raise TransactionRuleError("作废原因不能为空")
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
        if not row:
            raise TransactionNotFound("流水不存在")
        if row["status"] != "active" or row["source"] == "reversal":
            raise TransactionRuleError("该流水不可作废")
        now = _now()
        connection.execute(
            "UPDATE transactions SET status = 'voided', void_reason = ?, updated_at = ? WHERE id = ?",
            (reason, now, transaction_id),
        )
        _audit(connection, row["ledger_id"], "transaction", transaction_id, "voided", {"previous_status": "active"}, reason)
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def rename_category(connection: sqlite3.Connection, category_id: str, new_name: str) -> None:
    new_name = new_name.strip()
    if not new_name:
        raise TransactionRuleError("类别名称不能为空")
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM categories WHERE id = ?", (category_id,)).fetchone()
        if not row:
            raise TransactionRuleError("类别不存在")
        connection.execute(
            "UPDATE categories SET name = ?, updated_at = ? WHERE id = ?", (new_name, _now(), category_id)
        )
        _audit(connection, row["ledger_id"], "category", category_id, "renamed", {"from": row["name"], "to": new_name})
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def create_category(connection: sqlite3.Connection, ledger_id: str, category_type: str, name: str) -> str:
    name = name.strip()
    if category_type not in {"income", "expense"} or not name:
        raise TransactionRuleError("类别类型或名称无效")
    category_id = str(uuid4())
    try:
        connection.execute("BEGIN IMMEDIATE")
        now = _now()
        connection.execute(
            """INSERT INTO categories(id,ledger_id,type,name,is_active,created_at,updated_at)
               VALUES (?,?,?,?,1,?,?)""",
            (category_id, ledger_id, category_type, name, now, now),
        )
        _audit(connection, ledger_id, "category", category_id, "created", {"type": category_type, "name": name})
        connection.commit()
        return category_id
    except Exception:
        connection.rollback()
        raise


def set_category_active(connection: sqlite3.Connection, category_id: str, active: bool) -> None:
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM categories WHERE id=?", (category_id,)).fetchone()
        if not row:
            raise TransactionRuleError("类别不存在")
        connection.execute(
            "UPDATE categories SET is_active=?, updated_at=? WHERE id=?",
            (1 if active else 0, _now(), category_id),
        )
        _audit(connection, row["ledger_id"], "category", category_id, "activated" if active else "deactivated", {"name": row["name"]})
        connection.commit()
    except Exception:
        connection.rollback()
        raise
