from datetime import date
from pathlib import Path

from openpyxl import load_workbook

from college_finance_manager.application.initialize_ledger import InitializeLedgerCommand, initialize_ledger
from college_finance_manager.application.transactions import CreateTransactionCommand, create_direct_transaction
from college_finance_manager.infrastructure.backup import create_complete_backup, restore_backup_to_empty_directory, validate_backup
from college_finance_manager.infrastructure.database import connect_database
from college_finance_manager.infrastructure.reports import export_financial_report, export_transaction_rows
from college_finance_manager.application.transactions import list_transactions


def _data(database, tmp_path):
    ledger = initialize_ledger(database, InitializeLedgerCommand("账本", date(2026, 1, 1), 100_000, str(tmp_path)))
    category = database.execute("SELECT id FROM categories WHERE ledger_id=? AND type='income'", (ledger,)).fetchone()[0]
    create_direct_transaction(
        database,
        CreateTransactionCommand(
            ledger_id=ledger, occurred_on=date(2026, 1, 2), direction="income", amount_cents=100,
            category_id=category, purpose="=1+1", item="纪念徽章", idempotency_key="formula-text",
        ),
    )
    return ledger


def test_excel_has_required_sheets_and_formula_text_is_safe(database, tmp_path):
    ledger = _data(database, tmp_path)
    output = export_financial_report(
        database, ledger_id=ledger, date_from=date(2026, 1, 1), date_to=date(2026, 12, 31),
        destination=tmp_path / "report.xlsx",
    )
    workbook = load_workbook(output, data_only=False)
    assert workbook.sheetnames == ["资金汇总", "现金流水", "分类统计", "报销明细", "预付款明细"]
    purpose = workbook["现金流水"]["F2"]
    assert purpose.data_type == "s"
    assert purpose.value == "'=1+1"
    assert workbook["现金流水"]["G2"].value == "纪念徽章"
    assert workbook["现金流水"]["H2"].value == "未提交"
    assert workbook["资金汇总"]["B8"].value == 1001
    workbook.close()


def test_backup_restore_preserves_database_and_attachment_hash(database, tmp_path):
    ledger = _data(database, tmp_path)
    attachment_root = tmp_path / "attachments"
    attachment_root.mkdir()
    (attachment_root / "evidence.pdf").write_bytes(b"%PDF-test")
    backup = create_complete_backup(
        database, attachments_root=attachment_root, destination=tmp_path / "backups" / "complete.cfmbackup"
    )
    manifest = validate_backup(backup)
    assert "finance.db" in manifest["files"]
    assert "attachments/evidence.pdf" in manifest["files"]
    restored = tmp_path / "restored"
    restore_backup_to_empty_directory(backup, restored)
    restored_db = connect_database(restored / "finance.db")
    try:
        assert restored_db.execute("SELECT id FROM ledgers").fetchone()[0] == ledger
        assert restored_db.execute("SELECT count(*) FROM transactions").fetchone()[0] == 1
    finally:
        restored_db.close()
    assert (restored / "attachments" / "evidence.pdf").read_bytes() == b"%PDF-test"


def test_filtered_transaction_export_is_safe(database, tmp_path):
    ledger = _data(database, tmp_path)
    expense_category = database.execute(
        "SELECT id FROM categories WHERE ledger_id=? AND type='expense' LIMIT 1", (ledger,)
    ).fetchone()[0]
    create_direct_transaction(
        database,
        CreateTransactionCommand(
            ledger_id=ledger,
            occurred_on=date(2026, 1, 5),
            direction="expense",
            amount_cents=9_640,
            category_id=expense_category,
            purpose="@AC-TMR（电网）",
            item="+接线端子",
            idempotency_key="laboratory-export",
        ),
    )
    output = export_transaction_rows(
        list_transactions(database, ledger),
        tmp_path / "filtered.xlsx",
        ledger_name="实验室账单",
    )
    workbook = load_workbook(output, data_only=False)
    sheet = workbook["实验室账单"]
    assert sheet["A1"].value == "序号"
    assert sheet["D1"].value == "设备名称"
    assert sheet["J1"].value == "用途"
    assert sheet["O1"].value == "购买时间"
    assert sheet["R1"].value == "价格"
    assert sheet["T1"].value == "金额"
    assert sheet["V1"].value == "发票情况"
    assert sheet.auto_filter.ref == "A1:V2"
    assert {str(cell_range) for cell_range in sheet.merged_cells.ranges} == {
        "B2:F2", "G2:M2", "N2:P2", "Q2:R2", "S2:T2", "U2:V2",
    }
    assert sheet["A2"].value == 1
    assert sheet["B2"].value == "'+接线端子"
    assert sheet["G2"].value == "'@AC-TMR（电网）"
    assert sheet["N2"].value.date() == date(2026, 1, 5)
    assert sheet["N2"].number_format == 'yyyy"."m"."d'
    assert sheet["Q2"].value == 96.4
    assert sheet["Q2"].number_format == "#,##0.##"
    assert sheet["S2"].value is None
    assert sheet["U2"].value == "未提交"
    assert sheet["B2"].border.left.style == "thin"
    assert sheet["F2"].border.right.style == "thin"
    assert sheet.sheet_view.showGridLines is True
    assert sheet.freeze_panes == "A2"
    workbook.close()
