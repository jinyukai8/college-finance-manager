import json
from datetime import date

import pytest

from college_finance_manager.application.initialize_ledger import InitializeLedgerCommand, initialize_ledger
from college_finance_manager.application.read_models import get_transaction, list_attachments, list_categories, list_reversals
from college_finance_manager.application.transactions import CreateTransactionCommand, create_direct_transaction, get_cash_totals
from college_finance_manager.application.file_operations import add_attachment, change_attachment
from college_finance_manager.application.record_management import edit_transaction
from college_finance_manager.infrastructure.backup import validate_backup
from college_finance_manager.infrastructure.paths import AppPaths


@pytest.fixture
def entry(database, tmp_path):
    paths = AppPaths.from_root(tmp_path / "isolated")
    paths.ensure_directories()
    ledger = initialize_ledger(database, InitializeLedgerCommand("测试账本", date.today(), 1000, str(paths.backups)))
    category = list_categories(database, ledger, "expense")[0]["id"]
    transaction = create_direct_transaction(database, CreateTransactionCommand(
        ledger, date.today(), "expense", 100, category, "材料", handler="原经办人",
    ))
    for name in ("first.pdf", "second.pdf"):
        source = tmp_path / name
        source.write_bytes(b"%PDF-1.7\n" + name.encode())
        add_attachment(database, paths=paths, ledger_id=ledger, entity_type="transaction", entity_id=transaction, source_path=source)
    return paths, ledger, transaction


def test_edit_retains_original_balances_history_and_attachments(database, entry):
    paths, ledger, original = entry
    correction = edit_transaction(database, paths, original, {"amount_cents": 250, "handler": "新经办人"}, "录入有误")
    assert get_transaction(database, original)["amount_cents"] == 100
    assert get_transaction(database, original)["status"] == "reversed"
    assert get_transaction(database, correction)["handler"] == "新经办人"
    assert get_cash_totals(database, ledger).balance_cents == 750
    assert len(list_attachments(database, "transaction", correction)) == 2
    assert len(list_attachments(database, "transaction", original, include_historical_links=True)) == 2
    assert list_reversals(database, ledger)[0]["reversal_of_id"] == original
    audit = database.execute("SELECT change_summary, created_at FROM audit_logs WHERE action='edited'").fetchone()
    assert audit["created_at"]
    assert json.loads(audit["change_summary"])["before"]["amount_cents"] == 100
    assert json.loads(audit["change_summary"])["after"]["amount_cents"] == 250
    validate_backup(next(paths.backups.glob("before-*.cfmbackup")))


def test_edit_stops_when_backup_fails(database, entry, monkeypatch):
    paths, _, original = entry
    def fail(*args, **kwargs):
        raise OSError("backup failed")
    monkeypatch.setattr("college_finance_manager.application.record_management.backup_before_change", fail)
    with pytest.raises(OSError):
        edit_transaction(database, paths, original, {"amount_cents": 250}, "测试")
    assert get_transaction(database, original)["status"] == "active"


def test_replace_rename_and_remove_preserve_other_attachment(database, entry, tmp_path):
    paths, _, transaction = entry
    rows = list_attachments(database, "transaction", transaction)
    selected, other = rows[0], rows[1]
    replacement = tmp_path / "replacement.pdf"
    replacement.write_bytes(b"invalid")
    with pytest.raises(ValueError):
        change_attachment(database, paths, selected["id"], replacement=replacement)
    assert {row["id"] for row in list_attachments(database, "transaction", transaction)} == {selected["id"], other["id"]}
    replacement.write_bytes(b"%PDF-1.7\nreplacement")
    new_id = change_attachment(database, paths, selected["id"], replacement=replacement)
    change_attachment(database, paths, new_id, name="更正发票.pdf")
    change_attachment(database, paths, new_id, remove=True)
    assert [row["id"] for row in list_attachments(database, "transaction", transaction)] == [other["id"]]
    assert (paths.attachments / selected["internal_path"]).is_file()
    assert database.execute("SELECT count(*) FROM transactions").fetchone()[0] == 1


def test_edit_changes_direction_and_category_together_and_rejects_system_fields(database, entry):
    from college_finance_manager.application.transactions import TransactionRuleError

    paths, ledger, original = entry
    income_category = list_categories(database, ledger, "income")[0]["id"]
    with pytest.raises(TransactionRuleError, match="有效类别"):
        edit_transaction(database, paths, original, {"direction": "income"}, "更正方向")
    with pytest.raises(TransactionRuleError, match="业务字段"):
        edit_transaction(database, paths, original, {"transaction_no": "伪造编号"}, "测试")
    assert get_transaction(database, original)["status"] == "active"
    updated = edit_transaction(database, paths, original, {
        "direction": "income", "category_id": income_category, "occurred_on": date(2026, 11, 1),
        "amount_cents": 200, "purpose": "更正用途", "item": "新物品",
        "handler": "新经办人", "payment_method": "转账", "note": "更正说明",
    }, "录错方向及其他字段")
    row = get_transaction(database, updated)
    assert (row["direction"], row["category_id"], row["occurred_on"]) == ("income", income_category, "2026-11-01")
    assert (row["purpose"], row["item"], row["payment_method"], row["note"]) == ("更正用途", "新物品", "转账", "更正说明")
    assert get_cash_totals(database, ledger).balance_cents == 1200


def test_old_database_upgrade_preserves_rows_and_verified_files(tmp_path, monkeypatch):
    from college_finance_manager.infrastructure import database as db
    from college_finance_manager.infrastructure.backup import create_complete_backup
    from college_finance_manager.application.file_operations import resolve_verified_attachment

    paths = AppPaths.from_root(tmp_path / "old-ledger")
    paths.ensure_directories()
    connection = db.connect_database(paths.database)
    resources = db._migration_resources()
    with monkeypatch.context() as patch:
        patch.setattr(db, "_migration_resources", lambda: resources[:3])
        db.apply_migrations(connection)
    ledger = initialize_ledger(connection, InitializeLedgerCommand("旧账本", date.today(), 1000, str(paths.backups)))
    category = list_categories(connection, ledger, "expense")[0]["id"]
    transaction = create_direct_transaction(connection, CreateTransactionCommand(
        ledger, date.today(), "expense", 100, category, "旧流水", handler="原经办人",
    ))
    source = tmp_path / "old.pdf"
    source.write_bytes(b"%PDF-1.7\nold invoice")
    attachment = add_attachment(connection, paths=paths, ledger_id=ledger, entity_type="transaction",
                                entity_id=transaction, source_path=source)
    before = dict(get_transaction(connection, transaction))
    old_attachment = dict(connection.execute("SELECT * FROM attachments").fetchone())
    backup = paths.backups / "before-migration.cfmbackup"
    create_complete_backup(connection, attachments_root=paths.attachments, destination=backup)
    validate_backup(backup)
    db.apply_migrations(connection)
    assert dict(get_transaction(connection, transaction)) == before
    current_attachment = dict(connection.execute("SELECT * FROM attachments").fetchone())
    assert current_attachment.pop("archived_at") is None
    assert current_attachment == old_attachment
    assert resolve_verified_attachment(connection, paths=paths, attachment_id=attachment).read_bytes() == source.read_bytes()
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    connection.close()


def test_inline_edit_cancel_validation_and_confirmation(database, entry, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from college_finance_manager.ui.main_window import TransactionPage
    from college_finance_manager.ui.transaction_management import ReversalPage, TransactionDetailDialog

    app = QApplication.instance() or QApplication([])
    paths, ledger, original = entry
    page = TransactionPage(database, paths, ledger)
    assert not page.table.item(0, 0).flags() & Qt.ItemIsEditable
    monkeypatch.setattr("college_finance_manager.ui.main_window.QMessageBox.warning", lambda *args: None)
    page.table.item(0, 3).setText("1e100")
    assert page.table.item(0, 3).text() == "1.00"
    monkeypatch.setattr("college_finance_manager.ui.main_window.QInputDialog.getText", lambda *args: ("", False))
    page.table.item(0, 10).setText("取消修改")
    assert page.table.item(0, 10).text() == "原经办人"
    monkeypatch.setattr("college_finance_manager.ui.main_window.QInputDialog.getText", lambda *args: ("补填", True))
    page.table.item(0, 10).setText("新经办人")
    assert page.table.item(0, 10).text() == "新经办人"
    reversals = ReversalPage(database, ledger)
    assert reversals.table.rowCount() == 1
    assert reversals.table.item(0, 1).data(Qt.UserRole) == original
    detail = TransactionDetailDialog(database, original)
    assert "原经办人 → 新经办人" in detail.text.toPlainText()
    assert detail.related.count() == 2
    page.close()
    detail.close()
    reversals.close()
    app.processEvents()
