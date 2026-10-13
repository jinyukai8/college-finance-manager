from __future__ import annotations

import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from college_finance_manager.application.initialize_ledger import InitializeLedgerCommand, initialize_ledger
from college_finance_manager.ui.main_window import MainWindow


def test_main_window_can_be_constructed_offscreen(database, tmp_path):
    initialize_ledger(database, InitializeLedgerCommand("测试账本", date.today(), 0, str(tmp_path)))
    app = QApplication.instance() or QApplication([])
    window = MainWindow(database)
    assert window.minimumWidth() == 1024
    assert window.navigation.count() == 6
    window.close()
    app.processEvents()
