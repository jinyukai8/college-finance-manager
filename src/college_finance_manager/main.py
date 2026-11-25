from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from college_finance_manager.application.file_operations import create_manual_backup
from college_finance_manager.infrastructure.backup import (
    BackupValidationError,
    create_complete_backup,
    create_daily_backup_if_needed,
    restore_backup_in_place,
    validate_backup,
)
from college_finance_manager.infrastructure.database import (
    MigrationError,
    apply_migrations,
    connect_database,
    pending_migration_versions,
)
from college_finance_manager.infrastructure.paths import (
    AppPaths,
    DataDirectoryError,
    resolve_startup_paths,
)
from college_finance_manager.infrastructure.single_instance import AlreadyRunningError, SingleInstanceLock
from college_finance_manager.ui.main_window import MainWindow, SetupDialog
from college_finance_manager.ui.theme import APP_STYLE_SHEET
from college_finance_manager.ui.app_icon import create_app_icon


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="实验室账本")
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="仅为本次启动指定账本数据目录，覆盖安装时的配置",
    )
    return parser


def _choose_data_paths() -> AppPaths | None:
    selected = QFileDialog.getExistingDirectory(
        None, "选择账本数据文件夹（已有账本请选含 finance.db 的文件夹）",
    )
    return AppPaths.from_root(Path(selected)) if selected else None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyleSheet(APP_STYLE_SHEET)
    app.setWindowIcon(create_app_icon())
    executable = Path(sys.executable) if getattr(sys, "frozen", False) else None
    try:
        paths = resolve_startup_paths(args.data_dir, executable=executable)
        if paths is None:
            paths = _choose_data_paths()
        if paths is None:
            return 0
        paths.ensure_directories()
    except (DataDirectoryError, OSError, ValueError) as exc:
        QMessageBox.critical(None, "无法打开账本目录", f"{exc}\n\n请检查驱动器和目录，或使用安装程序重新选择数据位置。")
        return 2
    instance_lock = SingleInstanceLock(paths.lock_file)
    try:
        instance_lock.acquire()
    except AlreadyRunningError as exc:
        QMessageBox.warning(None, "无法启动", str(exc))
        return 2
    except OSError as exc:
        QMessageBox.critical(None, "无法访问账本目录", f"{paths.root}\n\n{exc}")
        return 2
    connection = None
    try:
        database_existed = paths.database.exists()
        connection = connect_database(paths.database)
        pending = pending_migration_versions(connection)
        if database_existed and pending:
            stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
            pre_migration = paths.backups / f"pre-migration-{stamp}.cfmbackup"
            create_complete_backup(
                connection, attachments_root=paths.attachments, destination=pre_migration
            )
            validate_backup(pre_migration)
        apply_migrations(connection)
        if not connection.execute("SELECT 1 FROM ledgers LIMIT 1").fetchone():
            setup = SetupDialog(connection, paths.backups)
            if setup.exec() != SetupDialog.Accepted:
                return 0
        try:
            create_daily_backup_if_needed(connection, paths=paths)
        except Exception as exc:
            QMessageBox.warning(None, "自动备份失败", f"今日自动备份未完成：{exc}\n请在设置中手动备份。")

        def restore_callback(backup_path: Path) -> None:
            nonlocal connection
            try:
                safety_backup = create_manual_backup(connection, paths=paths)
                validate_backup(safety_backup)
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                connection.close()
                connection = None
                recovery = restore_backup_in_place(backup_path, paths)
            except Exception as exc:
                QMessageBox.critical(None, "恢复失败", f"未完成数据切换：{exc}")
                return
            QMessageBox.information(
                None,
                "恢复完成",
                f"数据已恢复。原数据保留在：\n{recovery}\n\n应用现在退出，请重新启动。",
            )
            app.quit()

        window = MainWindow(connection, paths, restore_callback)
        window.show()
        return app.exec()
    except (MigrationError, BackupValidationError, OSError, sqlite3.Error) as exc:
        QMessageBox.critical(
            None, "账本无法启动",
            f"账本位置：{paths.root}\n\n{exc}\n\n请核对账本位置和软件版本，保留数据库和备份。",
        )
        return 2
    finally:
        if connection is not None:
            connection.close()
        instance_lock.release()
