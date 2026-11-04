from datetime import date

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from college_finance_manager.application.initialize_ledger import InitializeLedgerCommand, initialize_ledger
from college_finance_manager.application.read_models import list_categories
from college_finance_manager.application.transactions import CreateTransactionCommand, create_direct_transaction
from college_finance_manager.infrastructure.paths import AppPaths
from college_finance_manager.ui.main_window import MainWindow


def test_ledger_footer_filters_pagination_and_compact_columns(database, tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    paths = AppPaths.from_root(tmp_path)
    ledger = initialize_ledger(database, InitializeLedgerCommand("测试账本", date.today(), 99_000, str(paths.backups)))
    purpose = "实验室采购材料——" * 100
    for direction, count, amount in (("expense", 11, 1200), ("income", 1, 25000)):
        category = list_categories(database, ledger, direction)[0]["id"]
        for _ in range(count):
            create_direct_transaction(database, CreateTransactionCommand(
                ledger, date.today(), direction, amount, category, purpose,
                handler="陈同学", payment_method="转账", note="完整备注内容",
            ))
    window = MainWindow(database, paths, lambda _: None)
    window.resize(1024, 680)
    window.navigation.setCurrentRow(1)
    window.show()
    app.processEvents()
    page = window.transaction_page
    assert page.table.rowCount() == 10
    assert page.result_count.text() == "共 12 条记录，已选择 0 条"
    assert not {"本期收入", "本期支出", "结余", "记录总数"} & {
        label.text() for label in page.findChildren(QLabel)
    }
    note = page.table.cellWidget(0, 9)
    assert note.width() >= note.fontMetrics().horizontalAdvance("查看") + 8
    assert page.table.item(0, 6).toolTip() == purpose
    assert page.table.columnWidth(6) == 92
    assert page.table.horizontalScrollBar().maximum() == 0
    assert "支付方式" not in [page.table.horizontalHeaderItem(i).text() for i in range(page.table.columnCount())]
    assert database.execute("SELECT DISTINCT payment_method FROM transactions").fetchone()[0] == "转账"
    page.next_page.click()
    assert page.table.rowCount() == 2
    assert page.result_count.text() == "共 12 条记录，已选择 0 条"
    page.direction_filter.setCurrentIndex(2)
    page._apply_filters()
    assert page.result_count.text() == "共 11 条记录，已选择 0 条"
    assert page.page_label.text() == "1 / 2"
    page._check_page(True)
    assert page.result_count.text() == "共 11 条记录，已选择 10 条"
    exported = []
    monkeypatch.setattr(page, "_export_rows", lambda rows: exported.extend(rows))
    page._export_selected()
    assert len(exported) == 10 and all(row["direction"] == "expense" for row in exported)
    page._reset_filters()
    assert page.result_count.text() == "共 12 条记录，已选择 0 条"
    assert window.windowFlags() & Qt.FramelessWindowHint
    assert not window.window_bar.findChildren(QLabel)
    QTest.mouseDClick(window.window_bar, Qt.LeftButton, pos=QPoint(40, 14))
    app.processEvents()
    assert window.isMaximized()
    window.window_bar.maximize_button.click()
    app.processEvents()
    assert not window.isMaximized()
    window.window_bar.minimize_button.click()
    assert window.isMinimized()
    window.showNormal()
    window.window_bar.close_button.click()
    assert not window.isVisible()
    window.close()
    app.processEvents()
