from __future__ import annotations

import sqlite3
from copy import copy
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from college_finance_manager.application.transactions import get_cash_totals


_DANGEROUS_PREFIXES = ("=", "+", "-", "@")


def safe_excel_text(value: str | None) -> str:
    text = value or ""
    return "'" + text if text.startswith(_DANGEROUS_PREFIXES) else text


def export_financial_report(
    connection: sqlite3.Connection,
    *,
    ledger_id: str,
    date_from: date,
    date_to: date,
    destination: Path,
) -> Path:
    if date_from > date_to:
        raise ValueError("开始日期不能晚于结束日期")
    ledger = connection.execute("SELECT * FROM ledgers WHERE id = ?", (ledger_id,)).fetchone()
    if not ledger:
        raise ValueError("账本不存在")
    transactions = list(
        connection.execute(
            """SELECT t.*,
                      (SELECT COUNT(*) FROM attachments a
                       WHERE a.entity_type='transaction' AND a.entity_id=t.id) AS attachment_count
               FROM transactions t
               WHERE t.ledger_id = ? AND t.occurred_on BETWEEN ? AND ?
               ORDER BY occurred_on, transaction_no""",
            (ledger_id, date_from.isoformat(), date_to.isoformat()),
        )
    )
    totals = get_cash_totals(connection, ledger_id)
    workbook = Workbook()
    workbook.remove(workbook.active)
    summary = workbook.create_sheet("资金汇总")
    cash = workbook.create_sheet("现金流水")
    categories = workbook.create_sheet("分类统计")
    reimbursements = workbook.create_sheet("报销明细")
    advances = workbook.create_sheet("预付款明细")

    generated = datetime.now().astimezone().isoformat(timespec="seconds")
    summary_rows = [
        ("资金汇总", None),
        ("账本", safe_excel_text(ledger["name"])),
        ("统计区间", f"{date_from.isoformat()} 至 {date_to.isoformat()}"),
        ("生成时间", generated),
        ("期初金额（元）", Decimal(ledger["opening_balance_cents"]) / 100),
        ("累计现金收入（元）", Decimal(totals.income_cents) / 100),
        ("累计现金支出（元）", Decimal(totals.expense_cents) / 100),
        ("账面余额（元）", Decimal(totals.balance_cents) / 100),
        ("说明", "现金流水与预付款核销费用分开列示，核销不重复计入现金支出。"),
    ]
    for row in summary_rows:
        summary.append(row)

    cash.append((
        "编号", "发生日期", "类型", "金额（元）", "类别快照", "用途/来源", "物品",
        "发票状态", "经办人", "支付方式", "状态", "来源",
    ))
    for row in transactions:
        cash.append(
            (
                row["transaction_no"], date.fromisoformat(row["occurred_on"]),
                "收入" if row["direction"] == "income" else "支出",
                Decimal(row["amount_cents"]) / 100, safe_excel_text(row["category_name_snapshot"]),
                safe_excel_text(row["purpose"]), safe_excel_text(row["item"]),
                f"已提交（{row['attachment_count']}）" if row["attachment_count"] else "未提交",
                safe_excel_text(row["handler"]),
                safe_excel_text(row["payment_method"]), row["status"], row["source"],
            )
        )

    categories.append(("类型", "类别", "金额（元）"))
    for row in connection.execute(
        """SELECT direction, COALESCE(category_name_snapshot, '未分类') AS category_name,
                  SUM(amount_cents) AS total
           FROM transactions
           WHERE ledger_id=? AND occurred_on BETWEEN ? AND ? AND status <> 'voided'
           GROUP BY direction, category_name_snapshot ORDER BY direction, total DESC""",
        (ledger_id, date_from.isoformat(), date_to.isoformat()),
    ):
        categories.append(("收入" if row["direction"] == "income" else "支出", safe_excel_text(row["category_name"]), Decimal(row["total"]) / 100))

    reimbursements.append(("申请人", "金额（元）", "用途", "申请日期", "付款日期", "状态", "关联流水"))
    for row in connection.execute(
        """SELECT r.*, t.transaction_no FROM reimbursements r
           LEFT JOIN transactions t ON t.id=r.payment_transaction_id
           WHERE r.ledger_id=? AND r.applied_on BETWEEN ? AND ? ORDER BY r.applied_on""",
        (ledger_id, date_from.isoformat(), date_to.isoformat()),
    ):
        reimbursements.append((safe_excel_text(row["applicant"]), Decimal(row["amount_cents"]) / 100, safe_excel_text(row["purpose"]), date.fromisoformat(row["applied_on"]), date.fromisoformat(row["paid_on"]) if row["paid_on"] else None, row["status"], row["transaction_no"] or ""))

    advances.append(("收款人", "预付金额（元）", "用途", "申请日期", "状态", "已核销（元）", "已退款（元）", "待结清（元）"))
    for row in connection.execute(
        """SELECT a.*,
                  COALESCE(SUM(CASE WHEN e.event_type='settlement' THEN e.amount_cents ELSE 0 END),0) AS settled,
                  COALESCE(SUM(CASE WHEN e.event_type='refund' THEN e.amount_cents ELSE 0 END),0) AS refunded
           FROM advances a LEFT JOIN advance_events e ON e.advance_id=a.id
           WHERE a.ledger_id=? AND a.requested_on BETWEEN ? AND ?
           GROUP BY a.id ORDER BY a.requested_on""",
        (ledger_id, date_from.isoformat(), date_to.isoformat()),
    ):
        remaining = row["amount_cents"] - row["settled"] - row["refunded"]
        advances.append((safe_excel_text(row["recipient"]), Decimal(row["amount_cents"]) / 100, safe_excel_text(row["purpose"]), date.fromisoformat(row["requested_on"]), row["status"], Decimal(row["settled"]) / 100, Decimal(row["refunded"]) / 100, Decimal(remaining) / 100))

    for sheet in workbook.worksheets:
        sheet.sheet_view.showGridLines = False
        sheet.freeze_panes = "A2" if sheet is not summary else None
        max_column = sheet.max_column
        header_row = 1
        for cell in sheet[header_row]:
            cell.font = Font(name="Arial", bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F4E78")
            cell.alignment = Alignment(horizontal="center", vertical="center")
        for column_cells in sheet.columns:
            width = min(max(len(str(cell.value or "")) for cell in column_cells) + 2, 36)
            sheet.column_dimensions[column_cells[0].column_letter].width = max(width, 12)
        for row in sheet.iter_rows():
            for cell in row:
                font = copy(cell.font)
                font.name = "Arial"
                font.sz = 10
                cell.font = font
                if isinstance(cell.value, (Decimal, int, float)) and cell.row > 1:
                    cell.number_format = '#,##0.00;[Red](#,##0.00);-'
                if isinstance(cell.value, (date, datetime)):
                    cell.number_format = "yyyy-mm-dd"
    summary["A1"].font = Font(name="Arial", size=14, bold=True, color="FFFFFF")
    destination.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(destination)
    load_workbook(destination, read_only=True).close()
    return destination


def _safe_worksheet_title(value: str) -> str:
    title = value.strip()
    for character in "[]:*?/\\":
        title = title.replace(character, "-")
    return title[:31] or "实验室账单"


def export_transaction_rows(
    rows: list[sqlite3.Row],
    destination: Path,
    *,
    ledger_name: str = "实验室账单",
) -> Path:
    """Export filtered expense rows in the laboratory purchase-ledger layout."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = _safe_worksheet_title(ledger_name)
    sheet.sheet_view.showGridLines = True
    sheet.freeze_panes = "A2"
    headers: list[str | None] = [None] * 22
    for column, label in {
        1: "序号",
        4: "设备名称",
        10: "用途",
        15: "购买时间",
        18: "价格",
        20: "金额",
        22: "发票情况",
    }.items():
        headers[column - 1] = label
    sheet.append(headers)

    expense_rows = sorted(
        (row for row in rows if row["direction"] == "expense"),
        key=lambda row: (row["occurred_on"], row["transaction_no"]),
    )
    for sequence, row in enumerate(expense_rows, 1):
        output: list[object | None] = [None] * 22
        output[0] = sequence
        output[1] = safe_excel_text(row["item"])
        output[6] = safe_excel_text(row["purpose"])
        output[13] = date.fromisoformat(row["occurred_on"])
        output[16] = Decimal(row["amount_cents"]) / 100
        output[18] = None
        output[20] = (
            f"已提交（{row['attachment_count']}）"
            if row["attachment_count"]
            else "未提交"
        )
        sheet.append(output)
        excel_row = sequence + 1
        for cell_range in (
            f"B{excel_row}:F{excel_row}",
            f"G{excel_row}:M{excel_row}",
            f"N{excel_row}:P{excel_row}",
            f"Q{excel_row}:R{excel_row}",
            f"S{excel_row}:T{excel_row}",
            f"U{excel_row}:V{excel_row}",
        ):
            sheet.merge_cells(cell_range)

    thin = Side(style="thin", color="000000")
    group_left = {1, 2, 7, 14, 17, 19, 21}
    group_right = {1, 6, 13, 16, 18, 20, 22}
    for row in sheet.iter_rows(min_row=1, max_row=sheet.max_row, min_col=1, max_col=22):
        for cell in row:
            cell.font = Font(name="宋体", size=12)
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = Border(
                left=thin if cell.column in group_left else Side(style=None),
                right=thin if cell.column in group_right else Side(style=None),
                top=thin,
                bottom=thin,
            )
    for row_number in range(2, sheet.max_row + 1):
        sheet[f"N{row_number}"].number_format = 'yyyy"."m"."d'
        sheet[f"Q{row_number}"].number_format = "#,##0.##"

    sheet.row_dimensions[1].height = 24
    for row_number in range(2, sheet.max_row + 1):
        sheet.row_dimensions[row_number].height = 22
    sheet.column_dimensions["A"].width = 10
    for column in range(2, 23):
        sheet.column_dimensions[sheet.cell(1, column).column_letter].width = 10.5
    sheet.auto_filter.ref = f"A1:V{sheet.max_row}"
    sheet.print_title_rows = "1:1"
    sheet.print_area = f"A1:V{sheet.max_row}"
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    destination.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(destination)
    load_workbook(destination, read_only=True).close()
    return destination
