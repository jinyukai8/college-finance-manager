from __future__ import annotations

import sqlite3
from datetime import date, datetime
from uuid import uuid4

from college_finance_manager.application.transactions import _audit, get_cash_totals


def record_reconciliation(connection: sqlite3.Connection, *, ledger_id: str, reconciled_on: date, actual_balance_cents: int, note: str = "") -> str:
    if isinstance(actual_balance_cents, bool) or not isinstance(actual_balance_cents, int):
        raise TypeError("人工核对金额必须为整数分")
    book = get_cash_totals(connection, ledger_id).balance_cents
    reconciliation_id = str(uuid4())
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """INSERT INTO reconciliations
               (id, ledger_id, reconciled_on, book_balance_cents, actual_balance_cents,
                difference_cents, note, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (reconciliation_id, ledger_id, reconciled_on.isoformat(), book, actual_balance_cents,
             actual_balance_cents - book, note.strip() or None,
             datetime.now().astimezone().isoformat(timespec="seconds")),
        )
        _audit(connection, ledger_id, "reconciliation", reconciliation_id, "created", {"book_balance_cents": book, "actual_balance_cents": actual_balance_cents})
        connection.commit()
        return reconciliation_id
    except Exception:
        connection.rollback()
        raise
