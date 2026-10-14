from __future__ import annotations

import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from college_finance_manager.application.initialize_ledger import InitializeLedgerCommand, initialize_ledger
from college_finance_manager.ui.main_window import (
    CorrectTransactionDateDialog,
    MainWindow,
    SetupDialog,
    TransactionDialog,
)
from college_finance_manager.infrastructure.paths import AppPaths


def test_main_window_can_be_constructed_offscreen(database, tmp_path):
    initialize_ledger(database, InitializeLedgerCommand("测试账本", date.today(), 0, str(tmp_path)))
    app = QApplication.instance() or QApplication([])
    paths = AppPaths.from_root(tmp_path / "app")
    paths.ensure_directories()
    window = MainWindow(database, paths, lambda _path: None)
    assert window.windowTitle() == "实验室账本"
    assert window.minimumWidth() == 1024
    assert window.navigation.count() == 7
    assert window.pages.count() == 7
    assert window.pages.widget(2).__class__.__name__ == "ReimbursementPage"
    assert window.pages.widget(3).__class__.__name__ == "AdvancePage"
    assert window.pages.widget(4).__class__.__name__ == "ReportsPage"
    assert window.pages.widget(5).__class__.__name__ == "SettingsPage"
    assert window.pages.widget(6).__class__.__name__ == "RecycleBinPage"
    dialog = TransactionDialog(database, paths, window._ledger_row()["id"])
    assert hasattr(dialog, "item")
    assert hasattr(dialog, "invoice_summary")
    assert "*" in dialog.layout().labelForField(dialog.amount).text()
    dialog.close()
    window.close()
    app.processEvents()


def test_new_ledger_defaults_to_laboratory_ledger(database, tmp_path):
    app = QApplication.instance() or QApplication([])
    dialog = SetupDialog(database, tmp_path)
    assert dialog.name_edit.text() == "实验室账本"
    dialog.close()
    app.processEvents()


def test_date_correction_dialog_uses_calendar_and_reason(database):
    app = QApplication.instance() or QApplication([])
    dialog = CorrectTransactionDateDialog(date(2026, 10, 14))
    assert dialog.date_edit.date().toPython() == date(2026, 10, 14)
    assert dialog.date_edit.calendarPopup() is True
    assert dialog.reason_edit.placeholderText()
    dialog.close()
    app.processEvents()
