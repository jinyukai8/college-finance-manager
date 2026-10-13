from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path

from college_finance_manager.infrastructure.paths import AppPaths


class BackupValidationError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_complete_backup(
    connection: sqlite3.Connection,
    *,
    attachments_root: Path,
    destination: Path,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temp_name:
        temp = Path(temp_name)
        database_copy = temp / "finance.db"
        target = sqlite3.connect(database_copy)
        try:
            connection.backup(target)
        finally:
            target.close()
        check_connection = sqlite3.connect(database_copy)
        try:
            check = check_connection.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            check_connection.close()
        if check != "ok":
            raise BackupValidationError("数据库备份完整性检查失败")
        files = {"finance.db": _sha256(database_copy)}
        attachment_files = []
        if attachments_root.exists():
            for path in sorted(p for p in attachments_root.rglob("*") if p.is_file()):
                relative = path.relative_to(attachments_root).as_posix()
                archive_name = f"attachments/{relative}"
                files[archive_name] = _sha256(path)
                attachment_files.append((path, archive_name))
        manifest = {
            "format_version": 1,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "files": files,
        }
        temporary_zip = temp / "backup.tmp"
        with zipfile.ZipFile(temporary_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(database_copy, "finance.db")
            for path, archive_name in attachment_files:
                archive.write(path, archive_name)
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        temporary_zip.replace(destination)
    validate_backup(destination)
    return destination


def validate_backup(path: Path) -> dict:
    with tempfile.TemporaryDirectory() as temp_name, zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if "manifest.json" not in names or "finance.db" not in names:
            raise BackupValidationError("备份缺少清单或数据库")
        for name in names:
            if name.startswith(("/", "\\")) or ".." in Path(name).parts:
                raise BackupValidationError("备份包含不安全路径")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format_version") != 1:
            raise BackupValidationError("不支持的备份版本")
        archive.extractall(temp_name)
        root = Path(temp_name)
        for name, expected in manifest.get("files", {}).items():
            candidate = root / name
            if not candidate.is_file() or _sha256(candidate) != expected:
                raise BackupValidationError(f"备份文件校验失败：{name}")
        database = sqlite3.connect(root / "finance.db")
        database.row_factory = sqlite3.Row
        try:
            if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BackupValidationError("备份数据库损坏")
            migrations = database.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()
            if not migrations:
                raise BackupValidationError("备份缺少数据库版本信息")
            for row in database.execute("SELECT internal_path, sha256, size_bytes FROM attachments"):
                relative = Path(row["internal_path"])
                if relative.is_absolute() or ".." in relative.parts:
                    raise BackupValidationError("凭证记录包含不安全路径")
                attachment = root / "attachments" / relative
                if not attachment.is_file():
                    raise BackupValidationError(f"备份缺少凭证：{relative.as_posix()}")
                if attachment.stat().st_size != row["size_bytes"] or _sha256(attachment) != row["sha256"]:
                    raise BackupValidationError(f"凭证校验失败：{relative.as_posix()}")
        finally:
            database.close()
        return manifest


def restore_backup_to_empty_directory(path: Path, destination_root: Path) -> None:
    validate_backup(path)
    destination_root.mkdir(parents=True, exist_ok=True)
    if any(destination_root.iterdir()):
        raise BackupValidationError("恢复目标必须为空目录，防止覆盖现有数据")
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            if member.filename == "manifest.json":
                continue
            archive.extract(member, destination_root)
    database_path = destination_root / "finance.db"
    database = sqlite3.connect(database_path)
    try:
        if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise BackupValidationError("恢复后数据库校验失败")
    finally:
        database.close()


def create_daily_backup_if_needed(
    connection: sqlite3.Connection,
    *,
    paths: AppPaths,
    today: date | None = None,
    retention_count: int = 14,
) -> Path | None:
    """每日首次启动备份。只清理本功能生成且已超保留数量的自动备份。"""
    if retention_count < 1:
        raise ValueError("自动备份保留数量至少为 1")
    current_day = today or date.today()
    ledger = connection.execute("SELECT id FROM ledgers LIMIT 1").fetchone()
    if not ledger:
        return None
    last = connection.execute(
        "SELECT value FROM settings WHERE ledger_id=? AND key='last_auto_backup_date'", (ledger["id"],)
    ).fetchone()
    if last and last["value"] == current_day.isoformat():
        return None
    configured = connection.execute(
        "SELECT value FROM settings WHERE ledger_id=? AND key='backup_directory'", (ledger["id"],)
    ).fetchone()
    backup_root = Path(configured["value"]).expanduser().resolve() if configured else paths.backups
    backup_root.mkdir(parents=True, exist_ok=True)
    destination = backup_root / f"auto-{current_day.isoformat()}.cfmbackup"
    create_complete_backup(connection, attachments_root=paths.attachments, destination=destination)
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            """INSERT INTO settings(ledger_id,key,value,updated_at)
               VALUES (?, 'last_auto_backup_date', ?, ?)
               ON CONFLICT(ledger_id,key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
            (ledger["id"], current_day.isoformat(), now),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    automatic = sorted(backup_root.glob("auto-????-??-??.cfmbackup"), key=lambda p: p.name, reverse=True)
    for old in automatic[retention_count:]:
        old.unlink()
    return destination


def restore_backup_in_place(path: Path, paths: AppPaths) -> Path:
    """从已验证备份切换数据；原数据移动到带时间戳的可恢复目录。调用前须关闭数据库。"""
    validate_backup(path)
    paths.root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    recovery = paths.backups / f"restore-recovery-{stamp}"
    recovery.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(dir=paths.root, prefix="restore-stage-") as temp_name:
        stage = Path(temp_name)
        restore_backup_to_empty_directory(path, stage)
        staged_db = stage / "finance.db"
        staged_attachments = stage / "attachments"
        moved: list[tuple[Path, Path]] = []
        try:
            for source in (paths.database, Path(str(paths.database) + "-wal"), Path(str(paths.database) + "-shm")):
                if source.exists():
                    target = recovery / source.name
                    source.replace(target)
                    moved.append((target, source))
            if paths.attachments.exists():
                target = recovery / "attachments"
                paths.attachments.replace(target)
                moved.append((target, paths.attachments))
            staged_db.replace(paths.database)
            if staged_attachments.exists():
                staged_attachments.replace(paths.attachments)
            else:
                paths.attachments.mkdir()
        except Exception:
            if paths.database.exists():
                paths.database.replace(recovery / "failed-restored-finance.db")
            if paths.attachments.exists():
                paths.attachments.replace(recovery / "failed-restored-attachments")
            for backup_source, original_target in reversed(moved):
                if backup_source.exists():
                    backup_source.replace(original_target)
            raise
    try:
        check = sqlite3.connect(paths.database)
        try:
            if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BackupValidationError("切换后的数据库完整性检查失败")
        finally:
            check.close()
    except Exception:
        if paths.database.exists():
            paths.database.replace(recovery / "failed-restored-finance.db")
        if paths.attachments.exists():
            paths.attachments.replace(recovery / "failed-restored-attachments")
        for backup_source, original_target in reversed(moved):
            if backup_source.exists():
                backup_source.replace(original_target)
        raise BackupValidationError("恢复后验证失败，已自动切回原数据")
    return recovery
