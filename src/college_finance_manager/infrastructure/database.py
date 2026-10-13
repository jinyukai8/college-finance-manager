from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from importlib.resources import files
from pathlib import Path


class MigrationError(RuntimeError):
    pass


def connect_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=5.0, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = FULL")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _migration_resources() -> list:
    root = files("college_finance_manager.infrastructure.migrations")
    return sorted((item for item in root.iterdir() if item.name.endswith(".sql")), key=lambda item: item.name)


def pending_migration_versions(connection: sqlite3.Connection) -> list[str]:
    table_exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    applied = set()
    if table_exists:
        applied = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
    return [resource.name.removesuffix(".sql") for resource in _migration_resources() if resource.name.removesuffix(".sql") not in applied]


def apply_migration_script(
    connection: sqlite3.Connection, *, version: str, sql: str, checksum: str | None = None
) -> None:
    checksum = checksum or hashlib.sha256(sql.encode("utf-8")).hexdigest()
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        script = (
            "BEGIN IMMEDIATE;\n"
            + sql
            + "\nINSERT INTO schema_migrations(version, applied_at, checksum_sha256) VALUES ("
            + "'" + version.replace("'", "''") + "', "
            + "'" + now.replace("'", "''") + "', "
            + "'" + checksum + "');\nCOMMIT;"
        )
        connection.executescript(script)
    except sqlite3.DatabaseError as exc:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.DatabaseError:
            pass
        raise MigrationError(f"迁移 {version} 失败") from exc


def apply_migrations(connection: sqlite3.Connection) -> None:
    connection.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
               version TEXT PRIMARY KEY,
               applied_at TEXT NOT NULL,
               checksum_sha256 TEXT NOT NULL CHECK(length(checksum_sha256) = 64)
           )"""
    )
    applied = {
        row["version"]: row["checksum_sha256"]
        for row in connection.execute("SELECT version, checksum_sha256 FROM schema_migrations")
    }
    for resource in _migration_resources():
        version = resource.name.removesuffix(".sql")
        sql = resource.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        if version in applied:
            if applied[version] != checksum:
                raise MigrationError(f"已应用迁移 {version} 的校验和发生变化")
            continue
        apply_migration_script(connection, version=version, sql=sql, checksum=checksum)
