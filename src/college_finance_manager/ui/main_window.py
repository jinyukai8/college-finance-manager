from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QDate, QSize, QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCheckBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from college_finance_manager.application.initialize_ledger import (
    InitializeLedgerCommand,
    initialize_ledger,
)
from college_finance_manager.application.file_operations import add_attachment, backup_before_change, export_filtered_transactions
from college_finance_manager.application.record_management import edit_transaction
from college_finance_manager.application.read_models import (
    get_dashboard_data,
    get_ledger,
    get_transaction,
    list_categories,
)
from college_finance_manager.domain.money import parse_yuan_to_cents
from college_finance_manager.domain.money import format_cents
from college_finance_manager.application.transactions import (
    CreateTransactionCommand,
    TransactionFilter,
    correct_transaction_date,
    create_direct_transaction,
    get_cash_totals,
    list_transactions,
    reverse_transaction,
    void_unrealized_transaction,
)
from college_finance_manager.infrastructure.paths import AppPaths
from college_finance_manager.ui.theme import APP_STYLE_SHEET
from college_finance_manager.ui.app_icon import create_app_icon
from college_finance_manager.ui.file_drop_area import FileDropArea
from college_finance_manager.ui.note_viewer import set_note_cell
from college_finance_manager.ui.transaction_management import ReversalPage, TransactionDetailDialog, TransactionEditDialog
from college_finance_manager.ui.operations_pages import (
    AdvancePage,
    AttachmentManagerDialog,
    ReimbursementPage,
    ReportsPage,
    RecycleBinPage,
    SettingsPage,
)


class SetupDialog(QDialog):
    def __init__(self, connection: sqlite3.Connection, default_backup_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self.connection = connection
        self.setWindowTitle("首次设置")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        intro = QLabel("创建本地辅助账本。确认后期初金额不能在已有正式流水时直接覆盖。")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self.name_edit = QLineEdit("实验室账本")
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.balance_edit = QLineEdit("0.00")
        self.balance_edit.setPlaceholderText("例如：1000.00")
        backup_row = QWidget()
        backup_layout = QHBoxLayout(backup_row)
        backup_layout.setContentsMargins(0, 0, 0, 0)
        self.backup_edit = QLineEdit(str(default_backup_dir))
        browse = QPushButton("选择…")
        browse.clicked.connect(self._choose_backup)
        backup_layout.addWidget(self.backup_edit)
        backup_layout.addWidget(browse)
        form.addRow("账本名称", self.name_edit)
        form.addRow("期初日期", self.date_edit)
        form.addRow("期初金额", self.balance_edit)
        form.addRow("备份位置", backup_row)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _choose_backup(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择备份位置", self.backup_edit.text())
        if selected:
            self.backup_edit.setText(selected)

    def _save(self) -> None:
        try:
            initialize_ledger(
                self.connection,
                InitializeLedgerCommand(
                    name=self.name_edit.text(),
                    opening_date=self.date_edit.date().toPython(),
                    opening_balance_cents=parse_yuan_to_cents(
                        self.balance_edit.text(), allow_zero=True, allow_negative=True
                    ),
                    backup_directory=self.backup_edit.text(),
                ),
            )
        except Exception as exc:
            QMessageBox.critical(self, "无法创建账本", str(exc))
            return
        self.accept()


class TransactionDialog(QDialog):
    def __init__(self, connection: sqlite3.Connection, paths: AppPaths, ledger_id: str, parent=None) -> None:
        super().__init__(parent)
        self.connection = connection
        self.paths = paths
        self.ledger_id = ledger_id
        self.idempotency_key = str(uuid4())
        self.invoice_paths: list[Path] = []
        self.setWindowTitle("新增收支")
        self.setMinimumWidth(480)
        layout = QFormLayout(self)
        self.direction = QComboBox()
        self.direction.addItem("收入", "income")
        self.direction.addItem("支出", "expense")
        self.occurred_on = QDateEdit(QDate.currentDate())
        self.occurred_on.setCalendarPopup(True)
        self.amount = QLineEdit()
        self.amount.setPlaceholderText("例如：128.50")
        self.category = QComboBox()
        self.purpose = QLineEdit()
        self.item = QLineEdit()
        self.handler = QLineEdit()
        self.payment_method = QLineEdit()
        self.note = QLineEdit()
        invoice_row = QWidget()
        invoice_layout = QVBoxLayout(invoice_row)
        invoice_layout.setContentsMargins(0, 0, 0, 0)
        self.invoice_drop_area = FileDropArea("将发票/凭证文件拖到这里，保存收支时一并提交")
        self.invoice_drop_area.files_dropped.connect(self._append_invoices)
        invoice_layout.addWidget(self.invoice_drop_area)
        invoice_actions = QHBoxLayout()
        choose_invoice = QPushButton("选择发票…")
        choose_invoice.clicked.connect(self._choose_invoices)
        self.clear_invoices_button = QPushButton("清空选择")
        self.clear_invoices_button.setEnabled(False)
        self.clear_invoices_button.clicked.connect(self._clear_invoices)
        invoice_actions.addWidget(choose_invoice)
        invoice_actions.addWidget(self.clear_invoices_button)
        invoice_actions.addStretch()
        invoice_layout.addLayout(invoice_actions)
        self.invoice_summary = QLabel("未选择")
        self.invoice_summary.setWordWrap(True)
        self.invoice_summary.setMaximumHeight(64)
        invoice_layout.addWidget(self.invoice_summary)
        layout.addRow("类型 *", self.direction)
        layout.addRow("发生日期 *", self.occurred_on)
        layout.addRow("金额（元）*", self.amount)
        layout.addRow("类别 *", self.category)
        layout.addRow("用途/来源 *", self.purpose)
        layout.addRow("物品（可选）", self.item)
        layout.addRow("经办人（可选）", self.handler)
        layout.addRow("支付方式（可选）", self.payment_method)
        layout.addRow("备注（可选）", self.note)
        layout.addRow("发票（可选）", invoice_row)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        self.direction.currentIndexChanged.connect(self._load_categories)
        self._load_categories()

    def _choose_invoices(self) -> None:
        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            "选择发票或凭证",
            "",
            "发票或凭证 (*.jpg *.jpeg *.png *.pdf)",
        )
        if not filenames:
            return
        self._append_invoices([Path(filename) for filename in filenames])

    def _append_invoices(self, paths: list[Path]) -> None:
        for path in paths:
            resolved = path.resolve()
            if resolved not in self.invoice_paths:
                self.invoice_paths.append(resolved)
        self._refresh_invoice_summary()

    def _clear_invoices(self) -> None:
        self.invoice_paths.clear()
        self._refresh_invoice_summary()

    def _refresh_invoice_summary(self) -> None:
        names = "、".join(path.name for path in self.invoice_paths[:3])
        if len(self.invoice_paths) > 3:
            names += "…"
        self.invoice_summary.setText(f"待提交 {len(self.invoice_paths)} 个：{names}" if self.invoice_paths else "未选择")
        self.invoice_summary.setToolTip("\n".join(str(path) for path in self.invoice_paths))
        self.clear_invoices_button.setEnabled(bool(self.invoice_paths))

    def _load_categories(self) -> None:
        selected = self.category.currentData()
        self.category.clear()
        rows = list_categories(self.connection, self.ledger_id, self.direction.currentData())
        for row in rows:
            if row["is_active"]:
                self.category.addItem(row["name"], row["id"])
        if selected:
            index = self.category.findData(selected)
            if index >= 0:
                self.category.setCurrentIndex(index)

    def _save(self) -> None:
        try:
            transaction_id = create_direct_transaction(
                self.connection,
                CreateTransactionCommand(
                    ledger_id=self.ledger_id,
                    occurred_on=self.occurred_on.date().toPython(),
                    direction=self.direction.currentData(),
                    amount_cents=parse_yuan_to_cents(self.amount.text()),
                    category_id=self.category.currentData() or "",
                    purpose=self.purpose.text(),
                    item=self.item.text(),
                    handler=self.handler.text(),
                    payment_method=self.payment_method.text(),
                    note=self.note.text(),
                    idempotency_key=self.idempotency_key,
                ),
            )
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        failed: list[str] = []
        for invoice_path in self.invoice_paths:
            try:
                add_attachment(
                    self.connection,
                    paths=self.paths,
                    ledger_id=self.ledger_id,
                    entity_type="transaction",
                    entity_id=transaction_id,
                    source_path=invoice_path,
                )
            except Exception as exc:
                failed.append(f"{invoice_path.name}：{exc}")
        if failed:
            QMessageBox.warning(
                self,
                "流水已保存，部分发票未导入",
                "\n".join(failed),
            )
        self.accept()


class CorrectTransactionDateDialog(QDialog):
    def __init__(self, current_date: date, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("更正流水日期")
        self.setMinimumWidth(420)
        layout = QFormLayout(self)
        self.date_edit = QDateEdit(QDate(current_date.year, current_date.month, current_date.day))
        self.date_edit.setCalendarPopup(True)
        self.reason_edit = QLineEdit()
        self.reason_edit.setPlaceholderText("例如：录入时误选了日期")
        layout.addRow("正确日期 *", self.date_edit)
        layout.addRow("更正原因 *", self.reason_edit)
        note = QLabel("原流水不会被删除；系统会保留原记录，并生成关联的冲销和更正记录。")
        note.setWordWrap(True)
        layout.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("确认更正")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _accept_if_valid(self) -> None:
        if not self.reason_edit.text().strip():
            QMessageBox.warning(self, "请填写原因", "日期更正原因不能为空。")
            return
        self.accept()

    def corrected_on(self) -> date:
        return self.date_edit.date().toPython()

    def reason(self) -> str:
        return self.reason_edit.text().strip()


class TransactionPage(QWidget):
    changed = Signal()
    INLINE_FIELDS = {1: "occurred_on", 3: "amount_cents", 5: "item", 6: "purpose", 10: "handler", 11: "payment_method"}
    FORM_FIELDS = {2: "direction", 4: "category_id", 9: "note"}

    def __init__(self, connection: sqlite3.Connection, paths: AppPaths, ledger_id: str, parent=None) -> None:
        super().__init__(parent)
        self.connection = connection
        self.paths = paths
        self.ledger_id = ledger_id
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        top = QHBoxLayout()
        heading = QLabel("收支流水")
        heading.setObjectName("heading")
        top.addWidget(heading)
        top.addStretch()
        add_button = QPushButton("新增收支")
        add_button.setObjectName("primaryButton")
        add_button.clicked.connect(self._add)
        top.addWidget(add_button)
        layout.addLayout(top)

        filter_panel = QFrame()
        filter_panel.setObjectName("filterPanel")
        filter_panel_layout = QVBoxLayout(filter_panel)
        filter_panel_layout.setContentsMargins(16, 14, 16, 14)
        filter_panel_layout.setSpacing(10)
        filters = QHBoxLayout()
        self.direction_filter = QComboBox()
        self.direction_filter.addItem("全部类型", None)
        self.direction_filter.addItem("收入", "income")
        self.direction_filter.addItem("支出", "expense")
        self.use_dates = QCheckBox("日期")
        self.date_from = QDateEdit(QDate(QDate.currentDate().year(), 1, 1))
        self.date_to = QDateEdit(QDate.currentDate())
        self.date_from.setCalendarPopup(True)
        self.date_to.setCalendarPopup(True)
        self.category_filter = QComboBox()
        self.category_filter.addItem("全部类别", None)
        for category in list_categories(connection, ledger_id):
            self.category_filter.addItem(category["name"], category["id"])
        self.min_amount = QLineEdit()
        self.min_amount.setPlaceholderText("最低金额")
        self.max_amount = QLineEdit()
        self.max_amount.setPlaceholderText("最高金额")
        self.handler_filter = QLineEdit()
        self.handler_filter.setPlaceholderText("经办人")
        self.keyword_filter = QLineEdit()
        self.keyword_filter.setPlaceholderText("搜索用途或备注")
        search_button = QPushButton("筛选")
        search_button.clicked.connect(self.reload)
        filters.addWidget(self.direction_filter)
        filters.addWidget(self.use_dates)
        filters.addWidget(self.date_from)
        filters.addWidget(self.date_to)
        filters.addStretch()
        filter_panel_layout.addLayout(filters)
        advanced_filters = QHBoxLayout()
        advanced_filters.addWidget(self.category_filter)
        advanced_filters.addWidget(self.min_amount)
        advanced_filters.addWidget(self.max_amount)
        advanced_filters.addWidget(self.handler_filter)
        advanced_filters.addWidget(self.keyword_filter, 1)
        advanced_filters.addWidget(search_button)
        filter_panel_layout.addLayout(advanced_filters)
        layout.addWidget(filter_panel)

        self.table = QTableWidget(0, 12)
        self.table.setHorizontalHeaderLabels(
            ("编号", "日期", "类型", "金额", "类别", "物品", "用途/来源", "发票", "状态", "备注", "经办人", "支付方式")
        )
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.itemChanged.connect(self._inline_changed)
        self.table.cellDoubleClicked.connect(self._double_click_cell)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        for label, handler in (("详情", self._details), ("编辑", self._edit_selected)):
            button = QPushButton(label)
            button.clicked.connect(handler)
            actions.addWidget(button)
        correct_date_button = QPushButton("更正日期")
        correct_date_button.clicked.connect(self._correct_date)
        reverse_button = QPushButton("冲销所选")
        reverse_button.clicked.connect(self._reverse)
        void_button = QPushButton("作废误录")
        void_button.setObjectName("dangerButton")
        void_button.clicked.connect(self._void)
        actions.addWidget(correct_date_button)
        actions.addWidget(reverse_button)
        actions.addWidget(void_button)
        attachment_button = QPushButton("查看发票/凭证")
        attachment_button.clicked.connect(self._attachments)
        actions.addWidget(attachment_button)
        export_button = QPushButton("导出筛选结果")
        export_button.setObjectName("primaryButton")
        export_button.clicked.connect(self._export)
        actions.addWidget(export_button)
        layout.addLayout(actions)
        self.reload()

    def reload_categories(self) -> None:
        selected = self.category_filter.currentData()
        self.category_filter.clear()
        self.category_filter.addItem("全部类别", None)
        for category in list_categories(self.connection, self.ledger_id):
            self.category_filter.addItem(category["name"], category["id"])
        index = self.category_filter.findData(selected)
        self.category_filter.setCurrentIndex(index if index >= 0 else 0)

    def reload(self) -> None:
        try:
            minimum = parse_yuan_to_cents(self.min_amount.text(), allow_zero=True) if self.min_amount.text().strip() else None
            maximum = parse_yuan_to_cents(self.max_amount.text(), allow_zero=True) if self.max_amount.text().strip() else None
        except Exception as exc:
            QMessageBox.warning(self, "筛选金额无效", str(exc))
            return
        rows = list_transactions(
            self.connection,
            self.ledger_id,
            TransactionFilter(
                date_from=self.date_from.date().toPython() if self.use_dates.isChecked() else None,
                date_to=self.date_to.date().toPython() if self.use_dates.isChecked() else None,
                direction=self.direction_filter.currentData(),
                category_id=self.category_filter.currentData(),
                amount_min_cents=minimum,
                amount_max_cents=maximum,
                handler=self.handler_filter.text(),
                keyword=self.keyword_filter.text(),
            ),
        )
        blocker = QSignalBlocker(self.table)
        self.table.setRowCount(len(rows))
        direction_names = {"income": "收入", "expense": "支出"}
        status_names = {"active": "有效", "voided": "已作废", "reversed": "已冲销"}
        for index, row in enumerate(rows):
            values = (
                row["transaction_no"], row["occurred_on"], direction_names[row["direction"]],
                format_cents(row["amount_cents"]), row["category_name_snapshot"] or "—",
                row["item"] or "—", row["purpose"],
                f"已提交（{row['attachment_count']}）" if row["attachment_count"] else "未提交",
                status_names[row["status"]],
                "", row["handler"] or "—", row["payment_method"] or "—",
            )
            editable = row["source"] in {"direct", "correction"} and row["status"] == "active"
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if not editable or column not in self.INLINE_FIELDS:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                else:
                    item.setData(Qt.UserRole, str(value))
                if column == 0:
                    item.setData(Qt.UserRole, row["id"])
                self.table.setItem(index, column, item)
            set_note_cell(self.table, index, 9, row["note"],
                          (lambda tx=row["id"]: self._edit(tx, "note")) if editable else None)
        del blocker

    def _details(self) -> None:
        if transaction_id := self._selected_id():
            TransactionDetailDialog(self.connection, transaction_id, self, paths=self.paths).exec()

    def _edit_selected(self) -> None:
        if transaction_id := self._selected_id():
            self._edit(transaction_id)

    def _double_click_cell(self, row, column) -> None:
        if column in self.FORM_FIELDS:
            self._edit(self.table.item(row, 0).data(Qt.UserRole), self.FORM_FIELDS[column])
        elif column in (0, 8):
            TransactionDetailDialog(self.connection, self.table.item(row, 0).data(Qt.UserRole), self, paths=self.paths).exec()

    def _edit(self, transaction_id, field=None) -> None:
        row = get_transaction(self.connection, transaction_id)
        if not row or row["source"] not in {"direct", "correction"} or row["status"] != "active":
            QMessageBox.information(self, "不能编辑", "仅可编辑有效的直接收支；报销或预付款流水请通过对应业务处理。")
            return
        dialog = TransactionEditDialog(self.connection, row, field, self)
        if dialog.exec() == QDialog.Accepted:
            self._save_edit(transaction_id, dialog.changes, dialog.reason.text())

    def _inline_changed(self, item) -> None:
        field = self.INLINE_FIELDS.get(item.column())
        if field is None or not (item.flags() & Qt.ItemIsEditable) or item.text() == item.data(Qt.UserRole):
            return
        transaction_id = self.table.item(item.row(), 0).data(Qt.UserRole)
        try:
            value = item.text().strip()
            if field == "amount_cents":
                value = parse_yuan_to_cents(value)
            elif field == "occurred_on":
                value = date.fromisoformat(value)
            elif field == "purpose" and not value:
                raise ValueError("用途不能为空")
        except ValueError as exc:
            QMessageBox.warning(self, "输入无效", str(exc))
            self.reload()
            return
        reason, accepted = QInputDialog.getText(
            self, "确认保存更正", "填写修改原因。保存前会验证备份，原流水会保留：",
        )
        if accepted:
            self._save_edit(transaction_id, {field: value}, reason)
        else:
            self.reload()

    def _save_edit(self, transaction_id, changes, reason) -> None:
        try:
            edit_transaction(self.connection, self.paths, transaction_id, changes, reason)
        except Exception as exc:
            QMessageBox.critical(self, "更正失败", str(exc))
        else:
            self.changed.emit()
        self.reload()

    def _selected_id(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "请选择流水", "请先选择一条流水。")
            return None
        return self.table.item(row, 0).data(Qt.UserRole)

    def _add(self) -> None:
        dialog = TransactionDialog(self.connection, self.paths, self.ledger_id, self)
        if dialog.exec() == QDialog.Accepted:
            self.reload()
            self.changed.emit()

    def _reverse(self) -> None:
        transaction_id = self._selected_id()
        if not transaction_id:
            return
        reason, accepted = QInputDialog.getText(self, "冲销流水", "冲销原因（原记录和冲销记录都将保留）：")
        if not accepted:
            return
        try:
            backup_before_change(self.connection, self.paths)
            reverse_transaction(
                self.connection, transaction_id, reason,
                idempotency_key=str(uuid4()), occurred_on=date.today(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "冲销失败", str(exc))
            return
        self.reload()
        self.changed.emit()

    def _correct_date(self) -> None:
        transaction_id = self._selected_id()
        if not transaction_id:
            return
        transaction = get_transaction(self.connection, transaction_id)
        if not transaction:
            QMessageBox.critical(self, "更正失败", "所选流水不存在。")
            return
        dialog = CorrectTransactionDateDialog(date.fromisoformat(transaction["occurred_on"]), self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            backup_before_change(self.connection, self.paths)
            correct_transaction_date(
                self.connection,
                transaction_id,
                dialog.corrected_on(),
                dialog.reason(),
                idempotency_key=str(uuid4()),
            )
        except Exception as exc:
            QMessageBox.critical(self, "更正失败", str(exc))
            return
        self.reload()
        self.changed.emit()

    def _void(self) -> None:
        transaction_id = self._selected_id()
        if not transaction_id:
            return
        reason, accepted = QInputDialog.getText(self, "作废误录", "仅限确认从未发生的交易，请填写原因：")
        if not accepted:
            return
        try:
            backup_before_change(self.connection, self.paths)
            void_unrealized_transaction(self.connection, transaction_id, reason)
        except Exception as exc:
            QMessageBox.critical(self, "作废失败", str(exc))
            return
        self.reload()
        self.changed.emit()

    def _attachments(self) -> None:
        transaction_id = self._selected_id()
        if transaction_id:
            AttachmentManagerDialog(
                self.connection, self.paths, self.ledger_id,
                "transaction", transaction_id, self,
            ).exec()
            self.reload()

    def _export(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, "导出实验室账本", "实验室账本.xlsx", "Excel (*.xlsx)")
        if not filename:
            return
        filters = TransactionFilter(
            date_from=self.date_from.date().toPython() if self.use_dates.isChecked() else None,
            date_to=self.date_to.date().toPython() if self.use_dates.isChecked() else None,
            direction=self.direction_filter.currentData(), category_id=self.category_filter.currentData(),
            amount_min_cents=parse_yuan_to_cents(self.min_amount.text(), allow_zero=True) if self.min_amount.text().strip() else None,
            amount_max_cents=parse_yuan_to_cents(self.max_amount.text(), allow_zero=True) if self.max_amount.text().strip() else None,
            handler=self.handler_filter.text(), keyword=self.keyword_filter.text(),
        )
        try:
            rows = list_transactions(self.connection, self.ledger_id, filters, limit=100000)
            ledger = get_ledger(self.connection)
            export_filtered_transactions(
                rows,
                Path(filename),
                ledger_name=ledger["name"] if ledger else "实验室账本",
            )
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        QMessageBox.information(self, "导出完成", filename)


class MainWindow(QMainWindow):
    NAVIGATION = ("总览", "收支流水", "报销", "预付款", "报表", "设置", "回收站", "冲销记录")

    def __init__(
        self,
        connection: sqlite3.Connection,
        paths: AppPaths,
        restore_callback,
    ) -> None:
        super().__init__()
        self.connection = connection
        self.paths = paths
        self.setWindowTitle("实验室账本")
        self.setWindowIcon(create_app_icon())
        self.setMinimumSize(1024, 680)
        container = QWidget()
        container.setObjectName("appRoot")
        root = QHBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(224)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 20)
        sidebar_layout.setSpacing(0)

        brand = QWidget()
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(18, 24, 16, 20)
        brand_layout.setSpacing(12)
        brand_mark = QLabel("账")
        brand_mark.setObjectName("brandMark")
        brand_mark.setFixedSize(42, 42)
        brand_copy = QVBoxLayout()
        brand_copy.setSpacing(2)
        self.brand_title = QLabel("实验室账本")
        self.brand_title.setObjectName("brandTitle")
        self.brand_subtitle = QLabel("本地离线 · 安全记账")
        self.brand_subtitle.setObjectName("brandSubtitle")
        brand_copy.addWidget(self.brand_title)
        brand_copy.addWidget(self.brand_subtitle)
        brand_layout.addWidget(brand_mark)
        brand_layout.addLayout(brand_copy, 1)
        sidebar_layout.addWidget(brand)

        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setFixedWidth(224)
        self.navigation.addItems(self.NAVIGATION)
        # QListWidget's delegate must reserve the same height that QSS paints.
        # A stylesheet min-height alone can paint outside the allocated row.
        for index in range(self.navigation.count()):
            self.navigation.item(index).setSizeHint(QSize(180, 48))
        self.navigation.setUniformItemSizes(True)
        self.navigation.setSpacing(4)
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sidebar_layout.addWidget(self.navigation, 1)
        footer = QLabel("数据仅保存在你选择的位置")
        footer.setObjectName("sidebarFooter")
        footer.setContentsMargins(20, 10, 16, 0)
        footer.setWordWrap(True)
        sidebar_layout.addWidget(footer)

        self.pages = QStackedWidget()
        self.pages.setObjectName("contentStack")
        self.overview = self._build_overview()
        self.pages.addWidget(self.overview)
        ledger = self._ledger_row()
        self.transaction_page = TransactionPage(connection, paths, ledger["id"], self) if ledger else self._build_placeholder("收支流水")
        if isinstance(self.transaction_page, TransactionPage):
            self.transaction_page.changed.connect(self._refresh_overview)
        self.pages.addWidget(self.transaction_page)
        if ledger:
            reimbursement_page = ReimbursementPage(connection, paths, ledger["id"], self)
            advance_page = AdvancePage(connection, paths, ledger["id"], self)
            reimbursement_page.changed.connect(self._refresh_overview)
            advance_page.changed.connect(self._refresh_overview)
            self.pages.addWidget(reimbursement_page)
            self.pages.addWidget(advance_page)
            self.pages.addWidget(ReportsPage(connection, ledger["id"], self))
            settings_page = SettingsPage(connection, paths, ledger["id"], restore_callback, self)
            settings_page.categories_changed.connect(self.transaction_page.reload_categories)
            settings_page.ledger_renamed.connect(self._refresh_ledger_name)
            self.pages.addWidget(settings_page)
            self.recycle_bin_page = RecycleBinPage(connection, ledger["id"], self)
            self.transaction_page.changed.connect(self.recycle_bin_page.reload)
            reimbursement_page.changed.connect(self.recycle_bin_page.reload)
            advance_page.changed.connect(self.recycle_bin_page.reload)
            self.pages.addWidget(self.recycle_bin_page)
            reversal_page = ReversalPage(connection, ledger["id"], self, paths=paths)
            self.transaction_page.changed.connect(reversal_page.reload)
            self.pages.addWidget(reversal_page)
        else:
            for title in self.NAVIGATION[2:]:
                self.pages.addWidget(self._build_placeholder(title))
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)
        root.addWidget(self.sidebar)
        root.addWidget(self.pages, 1)
        self.setCentralWidget(container)
        self._configure_tables()
        self.setStyleSheet(APP_STYLE_SHEET)

    def _configure_tables(self) -> None:
        for table in self.findChildren(QTableWidget):
            table.setAlternatingRowColors(True)
            table.setShowGrid(False)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setSelectionMode(QAbstractItemView.SingleSelection)
            table.verticalHeader().setVisible(False)
            table.verticalHeader().setDefaultSectionSize(42)
            table.horizontalHeader().setMinimumHeight(42)
            table.horizontalHeader().setHighlightSections(False)

    def _ledger_row(self):
        return get_ledger(self.connection)

    def _build_overview(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(36, 28, 36, 32)
        layout.setSpacing(18)

        header = QVBoxLayout()
        header.setSpacing(3)
        heading = QLabel("总览")
        heading.setObjectName("heading")
        subtitle = QLabel(f"{date.today().year} 年 {date.today().month} 月 {date.today().day} 日 · 掌握每一笔资金去向")
        subtitle.setObjectName("pageSubtitle")
        header.addWidget(heading)
        header.addWidget(subtitle)
        layout.addLayout(header)

        ledger = self._ledger_row()
        card = QFrame()
        card.setObjectName("balanceCard")
        card.setMinimumHeight(154)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(7)
        if ledger:
            eyebrow = QLabel("当前可用余额")
            eyebrow.setObjectName("heroEyebrow")
            card_layout.addWidget(eyebrow)
            self.ledger_name_label = QLabel(ledger["name"])
            self.ledger_name_label.setObjectName("ledgerName")
            card_layout.addWidget(self.ledger_name_label)
            totals = get_cash_totals(self.connection, ledger["id"])
            self.balance_value = QLabel(f"¥ {format_cents(totals.balance_cents)}")
            self.balance_value.setObjectName("balanceValue")
            value = self.balance_value
            card_layout.addWidget(value)
            self.balance_caption = QLabel(
                f"期初日 {ledger['opening_date']} · 收入 ¥ {format_cents(totals.income_cents)} · "
                f"支出 ¥ {format_cents(totals.expense_cents)}"
            )
            caption = self.balance_caption
            caption.setObjectName("heroCaption")
            if totals.is_negative:
                value.setStyleSheet("color: #FFD1CC;")
        else:
            card_layout.addWidget(QLabel("尚未创建账本"))
            caption = QLabel("空账本不会显示模拟数据。")
            caption.setObjectName("heroCaption")
        card_layout.addWidget(caption)
        layout.addWidget(card)

        if ledger:
            dashboard = get_dashboard_data(self.connection, ledger["id"], date.today().strftime("%Y-%m"))
            metric_row = QHBoxLayout()
            metric_row.setSpacing(12)
            income_card, self.month_income_value = self._make_metric_card(
                "本月收入", f"¥ {format_cents(dashboard['month_income_cents'])}", "#087A67"
            )
            expense_card, self.month_expense_value = self._make_metric_card(
                "本月支出", f"¥ {format_cents(dashboard['month_expense_cents'])}", "#C76535"
            )
            reimbursement_card, self.pending_reimbursement_value = self._make_metric_card(
                "待付款报销", f"{dashboard['pending_reimbursements']} 笔", "#4668A8"
            )
            advance_card, self.open_advance_value = self._make_metric_card(
                "未结清预付款", f"{dashboard['open_advances']} 笔", "#7A5AA6"
            )
            for metric_card in (income_card, expense_card, reimbursement_card, advance_card):
                metric_row.addWidget(metric_card, 1)
            layout.addLayout(metric_row)

            recent_header = QHBoxLayout()
            recent_label = QLabel("最近 10 笔流水")
            recent_label.setObjectName("sectionTitle")
            recent_hint = QLabel("按发生日期倒序展示")
            recent_hint.setObjectName("muted")
            recent_header.addWidget(recent_label)
            recent_header.addStretch()
            recent_header.addWidget(recent_hint)
            layout.addLayout(recent_header)
            self.recent_table = QTableWidget(0, 5)
            self.recent_table.setHorizontalHeaderLabels(("日期", "编号", "类型", "金额", "用途/来源"))
            self.recent_table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.recent_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
            self.recent_table.setMinimumHeight(260)
            self._fill_recent(dashboard["recent"])
            layout.addWidget(self.recent_table, 1)
        return page

    @staticmethod
    def _make_metric_card(title: str, value: str, accent: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("metricCard")
        card.setMinimumHeight(92)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 13, 16, 13)
        card_layout.setSpacing(6)
        title_label = QLabel(title)
        title_label.setObjectName("metricLabel")
        value_label = QLabel(value)
        value_label.setObjectName("metricValue")
        value_label.setStyleSheet(f"color: {accent};")
        card_layout.addWidget(title_label)
        card_layout.addWidget(value_label)
        return card, value_label

    def _fill_recent(self, rows) -> None:
        if not hasattr(self, "recent_table"):
            return
        self.recent_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            values = (row["occurred_on"], row["transaction_no"], "收入" if row["direction"] == "income" else "支出", format_cents(row["amount_cents"]), row["purpose"])
            for j, value in enumerate(values):
                self.recent_table.setItem(i, j, QTableWidgetItem(str(value)))

    def _refresh_overview(self) -> None:
        ledger = self._ledger_row()
        if not ledger or not hasattr(self, "balance_value"):
            return
        totals = get_cash_totals(self.connection, ledger["id"])
        self.balance_value.setText(f"¥ {format_cents(totals.balance_cents)}")
        self.balance_caption.setText(
            f"期初日 {ledger['opening_date']} · 收入 ¥ {format_cents(totals.income_cents)} · "
            f"支出 ¥ {format_cents(totals.expense_cents)}"
        )
        color = "#FFD1CC" if totals.is_negative else "#FFFFFF"
        self.balance_value.setStyleSheet(f"color: {color};")
        dashboard = get_dashboard_data(self.connection, ledger["id"], date.today().strftime("%Y-%m"))
        self.month_income_value.setText(f"¥ {format_cents(dashboard['month_income_cents'])}")
        self.month_expense_value.setText(f"¥ {format_cents(dashboard['month_expense_cents'])}")
        self.pending_reimbursement_value.setText(f"{dashboard['pending_reimbursements']} 笔")
        self.open_advance_value.setText(f"{dashboard['open_advances']} 笔")
        self._fill_recent(dashboard["recent"])

    def _refresh_ledger_name(self, name: str) -> None:
        if hasattr(self, "ledger_name_label"):
            self.ledger_name_label.setText(name)

    @staticmethod
    def _build_placeholder(title: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        heading = QLabel(title)
        heading.setObjectName("heading")
        layout.addWidget(heading)
        message = QLabel("请先完成账本初始化。")
        message.setWordWrap(True)
        message.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        message.setObjectName("muted")
        layout.addWidget(message)
        layout.addStretch()
        return page
