from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from uuid import uuid4


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def rename_ledger(connection: sqlite3.Connection, ledger_id: str, new_name: str) -> None:
    """Rename a ledger without changing its opening balance or financial history."""
    name = new_name.strip()
    if not name:
        raise ValueError("账本名称不能为空")

    try:
        connection.execute("BEGIN IMMEDIATE")
        ledger = connection.execute(
            "SELECT name FROM ledgers WHERE id=?", (ledger_id,)
        ).fetchone()
        if not ledger:
            raise ValueError("账本不存在")
        if ledger["name"] == name:
            connection.commit()
            return

        now = _now()
        connection.execute(
            "UPDATE ledgers SET name=?, updated_at=? WHERE id=?",
            (name, now, ledger_id),
        )
        connection.execute(
            """INSERT INTO audit_logs
               (id, ledger_id, entity_type, entity_id, action, change_summary, reason, created_at)
               VALUES (?, ?, 'ledger', ?, 'renamed', ?, NULL, ?)""",
            (
                str(uuid4()),
                ledger_id,
                ledger_id,
                json.dumps(
                    {"from": ledger["name"], "to": name},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                now,
            ),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
