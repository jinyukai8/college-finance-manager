from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class InitializeLedgerCommand:
    name: str
    opening_date: date
    opening_balance_cents: int
    backup_directory: str


DEFAULT_CATEGORIES = (
    ("income", "其他收入"),
    ("expense", "办公用品"),
    ("expense", "活动支出"),
    ("expense", "差旅交通"),
    ("expense", "其他支出"),
)


class LedgerAlreadyInitialized(RuntimeError):
    pass


def initialize_ledger(connection: sqlite3.Connection, command: InitializeLedgerCommand) -> str:
    name = command.name.strip()
    if not name:
        raise ValueError("账本名称不能为空")
    if isinstance(command.opening_balance_cents, bool) or not isinstance(command.opening_balance_cents, int):
        raise TypeError("期初金额必须使用整数分")
    backup_directory = command.backup_directory.strip()
    if not backup_directory:
        raise ValueError("备份位置不能为空")

    ledger_id = str(uuid4())
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute("SELECT 1 FROM ledgers LIMIT 1").fetchone():
            raise LedgerAlreadyInitialized("V1 仅支持一个账本")
        connection.execute(
            """INSERT INTO ledgers
               (id, name, opening_date, opening_balance_cents, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ledger_id, name, command.opening_date.isoformat(), command.opening_balance_cents, now, now),
        )
        connection.executemany(
            """INSERT INTO categories
               (id, ledger_id, type, name, is_active, created_at, updated_at)
               VALUES (?, ?, ?, ?, 1, ?, ?)""",
            [(str(uuid4()), ledger_id, kind, category_name, now, now) for kind, category_name in DEFAULT_CATEGORIES],
        )
        connection.execute(
            "INSERT INTO settings (ledger_id, key, value, updated_at) VALUES (?, 'backup_directory', ?, ?)",
            (ledger_id, backup_directory, now),
        )
        connection.execute(
            """INSERT INTO audit_logs
               (id, ledger_id, entity_type, entity_id, action, change_summary, reason, created_at)
               VALUES (?, ?, 'ledger', ?, 'created', ?, NULL, ?)""",
            (str(uuid4()), ledger_id, ledger_id, "创建账本并设置期初金额", now),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return ledger_id
