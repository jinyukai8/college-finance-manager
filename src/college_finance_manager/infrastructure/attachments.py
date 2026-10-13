from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4


class AttachmentError(ValueError):
    pass


_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".pdf": "application/pdf",
}


def _detect_type(header: bytes) -> str | None:
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def import_attachment(
    connection: sqlite3.Connection,
    *,
    attachments_root: Path,
    ledger_id: str,
    entity_type: str,
    entity_id: str,
    source_path: Path,
    max_size_bytes: int = 20 * 1024 * 1024,
) -> str:
    source = source_path.resolve(strict=True)
    expected_type = _TYPES.get(source.suffix.lower())
    if not expected_type:
        raise AttachmentError("仅支持 JPG、JPEG、PNG 和 PDF")
    size = source.stat().st_size
    if size <= 0 or size > max_size_bytes:
        raise AttachmentError("凭证为空或超过大小限制")
    with source.open("rb") as stream:
        header = stream.read(16)
        digest = hashlib.sha256(header)
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    media_type = _detect_type(header)
    if media_type != expected_type:
        raise AttachmentError("文件扩展名与实际内容不一致")
    table_map = {
        "transaction": "transactions",
        "reimbursement": "reimbursements",
        "advance": "advances",
        "advance_event": "advance_events",
    }
    table = table_map.get(entity_type)
    if not table:
        raise AttachmentError("凭证关联类型无效")
    if not connection.execute(f"SELECT 1 FROM {table} WHERE id = ?", (entity_id,)).fetchone():
        raise AttachmentError("关联业务不存在")

    root = attachments_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    attachment_id = str(uuid4())
    filename = attachment_id + source.suffix.lower()
    destination = root / filename
    temporary = root / (filename + ".tmp")
    shutil.copyfile(source, temporary)
    try:
        connection.execute("BEGIN IMMEDIATE")
        os.replace(temporary, destination)
        connection.execute(
            """INSERT INTO attachments
               (id, ledger_id, entity_type, entity_id, internal_path, original_name,
                media_type, sha256, size_bytes, imported_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                attachment_id, ledger_id, entity_type, entity_id, filename, source.name,
                media_type, digest.hexdigest(), size,
                datetime.now().astimezone().isoformat(timespec="seconds"),
            ),
        )
        connection.commit()
        return attachment_id
    except Exception:
        connection.rollback()
        destination.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)
        raise
