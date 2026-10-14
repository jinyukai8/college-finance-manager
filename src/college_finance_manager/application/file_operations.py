from __future__ import annotations

import hashlib
import shutil
import sqlite3
from datetime import date, datetime
from pathlib import Path

from college_finance_manager.infrastructure.attachments import import_attachment
from college_finance_manager.infrastructure.backup import create_complete_backup, validate_backup
from college_finance_manager.infrastructure.paths import AppPaths
from college_finance_manager.infrastructure.reports import export_financial_report, export_transaction_rows


def add_attachment(
    connection: sqlite3.Connection,
    *,
    paths: AppPaths,
    ledger_id: str,
    entity_type: str,
    entity_id: str,
    source_path: Path,
) -> str:
    return import_attachment(
        connection,
        attachments_root=paths.attachments,
        ledger_id=ledger_id,
        entity_type=entity_type,
        entity_id=entity_id,
        source_path=source_path,
    )


def resolve_verified_attachment(
    connection: sqlite3.Connection, *, paths: AppPaths, attachment_id: str
) -> Path:
    row = connection.execute(
        "SELECT internal_path, sha256, size_bytes FROM attachments WHERE id=?", (attachment_id,)
    ).fetchone()
    if not row:
        raise ValueError("凭证不存在")
    root = paths.attachments.resolve()
    candidate = (root / row["internal_path"]).resolve()
    if root not in candidate.parents or not candidate.is_file():
        raise ValueError("凭证路径无效或文件缺失")
    if candidate.stat().st_size != row["size_bytes"]:
        raise ValueError("凭证大小校验失败")
    digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
    if digest != row["sha256"]:
        raise ValueError("凭证哈希校验失败")
    return candidate


def export_attachment(
    connection: sqlite3.Connection,
    *,
    paths: AppPaths,
    attachment_id: str,
    destination: Path,
) -> Path:
    source = resolve_verified_attachment(
        connection, paths=paths, attachment_id=attachment_id
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def export_report(
    connection: sqlite3.Connection,
    *,
    ledger_id: str,
    date_from: date,
    date_to: date,
    destination: Path,
) -> Path:
    return export_financial_report(
        connection,
        ledger_id=ledger_id,
        date_from=date_from,
        date_to=date_to,
        destination=destination,
    )


def export_filtered_transactions(
    rows: list[sqlite3.Row], destination: Path, *, ledger_name: str = "实验室账本"
) -> Path:
    return export_transaction_rows(rows, destination, ledger_name=ledger_name)


def create_manual_backup(connection: sqlite3.Connection, *, paths: AppPaths) -> Path:
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    ledger = connection.execute("SELECT id FROM ledgers LIMIT 1").fetchone()
    configured = connection.execute(
        "SELECT value FROM settings WHERE ledger_id=? AND key='backup_directory'", (ledger["id"],)
    ).fetchone() if ledger else None
    backup_root = Path(configured["value"]).expanduser().resolve() if configured else paths.backups
    destination = backup_root / f"manual-{stamp}.cfmbackup"
    return create_complete_backup(
        connection, attachments_root=paths.attachments, destination=destination
    )


def verify_backup(path: Path) -> dict:
    return validate_backup(path)
