from datetime import date

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QPushButton

from college_finance_manager.application.initialize_ledger import InitializeLedgerCommand, initialize_ledger
from college_finance_manager.application.read_models import list_categories
from college_finance_manager.application.transactions import CreateTransactionCommand, create_direct_transaction
from college_finance_manager.infrastructure.paths import AppPaths
from college_finance_manager.ui.main_window import TransactionDialog, TransactionPage
from college_finance_manager.ui.operations_pages import AttachmentManagerDialog


@pytest.fixture
def ui_context(database, tmp_path):
    app = QApplication.instance() or QApplication([])
    paths = AppPaths.from_root(tmp_path / "isolated-app")
    paths.ensure_directories()
    ledger = initialize_ledger(database, InitializeLedgerCommand("测试账本", date.today(), 0, str(paths.backups)))
    return app, paths, ledger


def send_file_drop(widget, urls):
    mime = QMimeData()
    mime.setUrls(urls)
    enter = QDragEnterEvent(QPoint(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(widget, enter)
    if not enter.isAccepted():
        return False
    drop = QDropEvent(QPointF(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(widget, drop)
    return drop.isAccepted()


def test_note_can_be_opened_from_transaction_column_without_writing(database, ui_context, monkeypatch):
    from college_finance_manager.ui.note_viewer import NoteDialog

    app, paths, ledger = ui_context
    note = "采购说明 <不是HTML>\n" + "完整备注内容 " * 200
    category = list_categories(database, ledger, "expense")[0]["id"]
    create_direct_transaction(database, CreateTransactionCommand(
        ledger, date.today(), "expense", 123, category, "测试采购", note=note,
    ))
    before = database.total_changes
    observed = []

    def inspect(dialog):
        editor = dialog.findChild(QPlainTextEdit)
        assert editor.isReadOnly()
        observed.append(editor.toPlainText())
        return 0

    monkeypatch.setattr(NoteDialog, "exec", inspect)
    page = TransactionPage(database, paths, ledger)
    column = next(i for i in range(page.table.columnCount()) if page.table.horizontalHeaderItem(i).text() == "备注")
    button = page.table.cellWidget(0, column)
    assert isinstance(button, QPushButton)
    button.click()
    assert observed == [note.strip()]
    assert database.total_changes == before
    page.close()
    app.processEvents()


def test_new_entry_drop_accumulates_deduplicates_and_saves_invoices(database, ui_context, tmp_path):
    app, paths, ledger = ui_context
    first = tmp_path / "第一张发票.png"
    first.write_bytes(b"\x89PNG\r\n\x1a\n" + b"first")
    second = tmp_path / "second.pdf"
    second.write_bytes(b"%PDF-1.7\nsecond")
    dialog = TransactionDialog(database, paths, ledger)
    dialog.show()
    app.processEvents()
    assert send_file_drop(dialog.invoice_drop_area, [QUrl.fromLocalFile(str(first))])
    assert send_file_drop(dialog.invoice_drop_area, [QUrl.fromLocalFile(str(first)), QUrl.fromLocalFile(str(second))])
    assert dialog.invoice_paths == [first.resolve(), second.resolve()]
    assert database.execute("SELECT count(*) FROM attachments").fetchone()[0] == 0
    dialog.direction.setCurrentIndex(1)
    dialog.amount.setText("1.23")
    dialog.purpose.setText("拖入发票测试")
    dialog._save()
    assert database.execute("SELECT count(*) FROM transactions").fetchone()[0] == 1
    assert database.execute("SELECT count(*) FROM attachments").fetchone()[0] == 2
    assert first.exists() and second.exists()
    dialog.close()


@pytest.mark.parametrize("kind", ["reimbursement", "advance"])
def test_business_notes_are_clickable_and_empty_notes_are_explicit(database, ui_context, monkeypatch, kind):
    from college_finance_manager.application.advances import create_advance
    from college_finance_manager.application.reimbursements import create_reimbursement
    from college_finance_manager.ui.note_viewer import NoteDialog
    from college_finance_manager.ui.operations_pages import AdvancePage, ReimbursementPage

    app, paths, ledger = ui_context
    if kind == "advance":
        create_advance(database, ledger_id=ledger, recipient="张同学", amount_cents=100,
                       purpose="采购", requested_on=date.today(), note="预付采购备注")
        page = AdvancePage(database, paths, ledger)
        expected = "预付采购备注"
    else:
        create_reimbursement(database, ledger_id=ledger, applicant="李同学", amount_cents=100,
                             purpose="报销", applied_on=date.today(), note="报销备注")
        page = ReimbursementPage(database, paths, ledger)
        expected = "报销备注"
    observed = []
    monkeypatch.setattr(NoteDialog, "exec", lambda dialog: observed.append(dialog.findChild(QPlainTextEdit).toPlainText()))
    column = page.table.columnCount() - 1
    assert page.table.horizontalHeaderItem(column).text() == "备注"
    page.table.cellWidget(0, column).click()
    assert observed == [expected]
    # Reloading a blank cell must not retain another record's note button.
    from college_finance_manager.ui.note_viewer import set_note_cell
    set_note_cell(page.table, 0, column, None)
    assert page.table.cellWidget(0, column) is None
    assert page.table.item(0, column).text() == "—"
    page.close()
    app.processEvents()


def test_cancel_and_clear_staged_invoices_do_not_write(database, ui_context, tmp_path):
    app, paths, ledger = ui_context
    source = tmp_path / "invoice.pdf"
    source.write_bytes(b"%PDF-1.7\ntest")
    dialog = TransactionDialog(database, paths, ledger)
    dialog.show()
    app.processEvents()
    assert send_file_drop(dialog.invoice_drop_area, [QUrl.fromLocalFile(str(source))])
    dialog.clear_invoices_button.click()
    assert dialog.invoice_paths == []
    assert send_file_drop(dialog.invoice_drop_area, [QUrl.fromLocalFile(str(source))])
    dialog.reject()
    assert database.execute("SELECT count(*) FROM transactions").fetchone()[0] == 0
    assert database.execute("SELECT count(*) FROM attachments").fetchone()[0] == 0
    assert not list(paths.attachments.iterdir())


def test_attachment_manager_drop_uses_existing_validation(database, ui_context, tmp_path, monkeypatch):
    app, paths, ledger = ui_context
    category = list_categories(database, ledger, "expense")[0]["id"]
    transaction = create_direct_transaction(database, CreateTransactionCommand(
        ledger, date.today(), "expense", 123, category, "测试采购",
    ))
    source = tmp_path / "valid.pdf"
    source.write_bytes(b"%PDF-1.7\nvalid")
    fake = tmp_path / "fake.png"
    fake.write_bytes(b"not a png")
    warnings = []
    monkeypatch.setattr("college_finance_manager.ui.operations_pages.QMessageBox.warning", lambda *args: warnings.append(args))
    dialog = AttachmentManagerDialog(database, paths, ledger, "transaction", transaction)
    dialog.show()
    app.processEvents()
    assert send_file_drop(dialog.drop_area, [QUrl.fromLocalFile(str(source)), QUrl.fromLocalFile(str(fake))])
    assert dialog.table.rowCount() == 1
    assert database.execute("SELECT count(*) FROM attachments").fetchone()[0] == 1
    assert len(list(paths.attachments.iterdir())) == 1
    assert warnings and "fake.png" in warnings[0][-1]
    assert not send_file_drop(dialog.drop_area, [QUrl("https://example.com/invoice.pdf")])
    assert not send_file_drop(dialog.drop_area, [QUrl.fromLocalFile(str(tmp_path))])
    assert not send_file_drop(dialog.drop_area, [QUrl.fromLocalFile(str(tmp_path / "unsupported.exe"))])
    dialog.close()
