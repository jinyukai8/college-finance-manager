from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from college_finance_manager.infrastructure.database import apply_migrations, connect_database
from college_finance_manager.infrastructure.paths import AppPaths, default_app_paths
from college_finance_manager.ui.main_window import MainWindow, SetupDialog


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="学院组织资金管理助手")
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="显式数据目录；仅用于开发或测试隔离，不要指向正式目录",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = AppPaths.from_root(args.data_dir) if args.data_dir else default_app_paths()
    paths.ensure_directories()
    connection = connect_database(paths.database)
    try:
        apply_migrations(connection)
        app = QApplication.instance() or QApplication(sys.argv[:1])
        if not connection.execute("SELECT 1 FROM ledgers LIMIT 1").fetchone():
            setup = SetupDialog(connection, paths.backups)
            if setup.exec() != SetupDialog.Accepted:
                return 0
        window = MainWindow(connection)
        window.show()
        return app.exec()
    finally:
        connection.close()
