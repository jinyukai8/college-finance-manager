from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path


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
        try:
            if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BackupValidationError("备份数据库损坏")
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
