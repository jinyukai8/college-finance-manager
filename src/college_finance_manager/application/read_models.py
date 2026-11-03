from __future__ import annotations

import sqlite3


def get_ledger(connection: sqlite3.Connection):
    return connection.execute(
        "SELECT id, name, opening_balance_cents, opening_date FROM ledgers LIMIT 1"
    ).fetchone()


def get_transaction(connection: sqlite3.Connection, transaction_id: str):
    return connection.execute(
        "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
    ).fetchone()


def list_reversals(connection: sqlite3.Connection, ledger_id: str):
    return list(connection.execute(
        """SELECT r.*, o.transaction_no AS original_no
           FROM transactions r JOIN transactions o ON o.id=r.reversal_of_id
           WHERE r.ledger_id=? AND r.source='reversal'
           ORDER BY r.created_at DESC""", (ledger_id,),
    ))


def related_transactions(connection: sqlite3.Connection, transaction_id: str):
    return list(connection.execute(
        """SELECT t.* FROM transactions t JOIN transactions current ON current.id=?
           WHERE t.ledger_id=current.ledger_id AND
             (t.id IN (current.reversal_of_id, current.correction_of_id)
              OR t.reversal_of_id=current.id OR t.correction_of_id=current.id)
           ORDER BY t.created_at""", (transaction_id,),
    ))


def transaction_history(connection: sqlite3.Connection, transaction_id: str):
    return list(connection.execute(
        """SELECT action, reason, change_summary, created_at FROM audit_logs
           WHERE entity_type='transaction' AND entity_id=? AND action IN ('edited','date_corrected','reversed')
           ORDER BY created_at DESC""", (transaction_id,),
    ))


def list_categories(connection: sqlite3.Connection, ledger_id: str, category_type: str | None = None):
    sql = "SELECT id, type, name, is_active FROM categories WHERE ledger_id=?"
    parameters: list[object] = [ledger_id]
    if category_type:
        sql += " AND type=?"
        parameters.append(category_type)
    sql += " ORDER BY type, name"
    return list(connection.execute(sql, parameters))


def list_reimbursements(connection: sqlite3.Connection, ledger_id: str):
    return list(
        connection.execute(
            """SELECT r.*, t.transaction_no FROM reimbursements r
               LEFT JOIN transactions t ON t.id=r.payment_transaction_id
               WHERE r.ledger_id=? ORDER BY r.applied_on DESC, r.created_at DESC""",
            (ledger_id,),
        )
    )


def list_advances(connection: sqlite3.Connection, ledger_id: str):
    return list(
        connection.execute(
            """SELECT a.*,
                      COALESCE(SUM(CASE WHEN e.event_type='settlement' THEN e.amount_cents ELSE 0 END),0) AS settled_cents,
                      COALESCE(SUM(CASE WHEN e.event_type='refund' THEN e.amount_cents ELSE 0 END),0) AS refunded_cents
               FROM advances a LEFT JOIN advance_events e ON e.advance_id=a.id
               WHERE a.ledger_id=? GROUP BY a.id ORDER BY a.requested_on DESC, a.created_at DESC""",
            (ledger_id,),
        )
    )


def list_attachments(connection: sqlite3.Connection, entity_type: str, entity_id: str, *,
                     include_archived=False, include_historical_links=False):
    return list(
        connection.execute(
            """SELECT id, entity_id, original_name, internal_path, media_type, sha256, size_bytes, imported_at, archived_at
               FROM attachments WHERE entity_type=?
                 AND (entity_id=? OR (? AND entity_type='transaction' AND EXISTS (
                     SELECT 1 FROM transaction_attachment_history h
                     WHERE h.attachment_id=attachments.id AND h.transaction_id=?
                 ))) AND (? OR archived_at IS NULL)
               ORDER BY archived_at IS NOT NULL, imported_at DESC""",
            (entity_type, entity_id, include_historical_links, entity_id, include_archived),
        )
    )


def list_reconciliations(connection: sqlite3.Connection, ledger_id: str):
    return list(
        connection.execute(
            """SELECT * FROM reconciliations WHERE ledger_id=?
               ORDER BY reconciled_on DESC, created_at DESC""",
            (ledger_id,),
        )
    )


def get_setting(connection: sqlite3.Connection, ledger_id: str, key: str) -> str | None:
    row = connection.execute(
        "SELECT value FROM settings WHERE ledger_id=? AND key=?", (ledger_id, key)
    ).fetchone()
    return row["value"] if row else None


def get_dashboard_data(connection: sqlite3.Connection, ledger_id: str, month_prefix: str) -> dict:
    month = connection.execute(
        """SELECT
               COALESCE(SUM(CASE WHEN direction='income' THEN amount_cents ELSE 0 END),0) income,
               COALESCE(SUM(CASE WHEN direction='expense' THEN amount_cents ELSE 0 END),0) expense
           FROM transactions WHERE ledger_id=? AND substr(occurred_on,1,7)=?
               AND status='active' AND source<>'reversal'""",
        (ledger_id, month_prefix),
    ).fetchone()
    pending_reimbursements = connection.execute(
        "SELECT COUNT(*) FROM reimbursements WHERE ledger_id=? AND status='awaiting_payment'", (ledger_id,)
    ).fetchone()[0]
    open_advances = connection.execute(
        """SELECT COUNT(*) FROM advances WHERE ledger_id=?
           AND status IN ('pending_payment','pending_settlement','partially_settled')""",
        (ledger_id,),
    ).fetchone()[0]
    recent = list(
        connection.execute(
            """SELECT transaction_no,occurred_on,direction,amount_cents,purpose,status
               FROM transactions WHERE ledger_id=? AND status='active' AND source<>'reversal'
               ORDER BY occurred_on DESC,created_at DESC LIMIT 10""",
            (ledger_id,),
        )
    )
    categories = list(
        connection.execute(
            """SELECT direction,category_name_snapshot,SUM(amount_cents) total
               FROM transactions WHERE ledger_id=? AND status='active' AND source<>'reversal'
               GROUP BY direction,category_name_snapshot ORDER BY total DESC LIMIT 8""",
            (ledger_id,),
        )
    )
    return {
        "month_income_cents": month["income"],
        "month_expense_cents": month["expense"],
        "pending_reimbursements": pending_reimbursements,
        "open_advances": open_advances,
        "recent": recent,
        "categories": categories,
    }


def list_recycle_bin_records(connection: sqlite3.Connection, ledger_id: str):
    return list(
        connection.execute(
            """SELECT 'transaction' AS entity_type, id AS entity_id,
                      transaction_no AS record_no, occurred_on AS record_date,
                      purpose AS summary, status, void_reason AS reason, updated_at
               FROM transactions WHERE ledger_id=? AND status='voided'
               UNION ALL
               SELECT 'reimbursement', id, '报销', applied_on, purpose, status,
                      COALESCE(decision_reason, ''), updated_at
               FROM reimbursements WHERE ledger_id=? AND status IN ('rejected','cancelled')
               UNION ALL
               SELECT 'advance', id, '预付款', requested_on, purpose, status,
                      COALESCE(cancel_reason, ''), updated_at
               FROM advances WHERE ledger_id=? AND status='cancelled'
               ORDER BY updated_at DESC""",
            (ledger_id, ledger_id, ledger_id),
        )
    )
