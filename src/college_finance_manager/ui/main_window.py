from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
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
from college_finance_manager.domain.money import parse_yuan_to_cents
from college_finance_manager.domain.money import format_cents
from college_finance_manager.application.transactions import (
    CreateTransactionCommand,
    TransactionFilter,
    create_direct_transaction,
    get_cash_totals,
    list_transactions,
    reverse_transaction,
    void_unrealized_transaction,
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
        self.name_edit = QLineEdit("学院组织账本")
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
    def __init__(self, connection: sqlite3.Connection, ledger_id: str, parent=None) -> None:
        super().__init__(parent)
        self.connection = connection
        self.ledger_id = ledger_id
        self.idempotency_key = str(uuid4())
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
        self.handler = QLineEdit()
        self.payment_method = QLineEdit()
        self.note = QLineEdit()
        layout.addRow("类型", self.direction)
        layout.addRow("发生日期", self.occurred_on)
        layout.addRow("金额（元）", self.amount)
        layout.addRow("类别", self.category)
        layout.addRow("用途/来源", self.purpose)
        layout.addRow("经办人（可选）", self.handler)
        layout.addRow("支付方式（可选）", self.payment_method)
        layout.addRow("备注（可选）", self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        self.direction.currentIndexChanged.connect(self._load_categories)
        self._load_categories()

    def _load_categories(self) -> None:
        selected = self.category.currentData()
        self.category.clear()
        rows = self.connection.execute(
            """SELECT id, name FROM categories
               WHERE ledger_id = ? AND type = ? AND is_active = 1 ORDER BY name""",
            (self.ledger_id, self.direction.currentData()),
        )
        for row in rows:
            self.category.addItem(row["name"], row["id"])
        if selected:
            index = self.category.findData(selected)
            if index >= 0:
                self.category.setCurrentIndex(index)

    def _save(self) -> None:
        try:
            create_direct_transaction(
                self.connection,
                CreateTransactionCommand(
                    ledger_id=self.ledger_id,
                    occurred_on=self.occurred_on.date().toPython(),
                    direction=self.direction.currentData(),
                    amount_cents=parse_yuan_to_cents(self.amount.text()),
                    category_id=self.category.currentData() or "",
                    purpose=self.purpose.text(),
                    handler=self.handler.text(),
                    payment_method=self.payment_method.text(),
                    note=self.note.text(),
                    idempotency_key=self.idempotency_key,
                ),
            )
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self.accept()


class TransactionPage(QWidget):
    changed = Signal()

    def __init__(self, connection: sqlite3.Connection, ledger_id: str, parent=None) -> None:
        super().__init__(parent)
        self.connection = connection
        self.ledger_id = ledger_id
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        top = QHBoxLayout()
        heading = QLabel("收支流水")
        heading.setObjectName("heading")
        top.addWidget(heading)
        top.addStretch()
        add_button = QPushButton("新增收支")
        add_button.clicked.connect(self._add)
        top.addWidget(add_button)
        layout.addLayout(top)

        filters = QHBoxLayout()
        self.direction_filter = QComboBox()
        self.direction_filter.addItem("全部类型", None)
        self.direction_filter.addItem("收入", "income")
        self.direction_filter.addItem("支出", "expense")
        self.keyword_filter = QLineEdit()
        self.keyword_filter.setPlaceholderText("搜索用途或备注")
        search_button = QPushButton("筛选")
        search_button.clicked.connect(self.reload)
        filters.addWidget(self.direction_filter)
        filters.addWidget(self.keyword_filter, 1)
        filters.addWidget(search_button)
        layout.addLayout(filters)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(("编号", "日期", "类型", "金额", "类别", "用途/来源", "状态"))
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        reverse_button = QPushButton("冲销所选")
        reverse_button.clicked.connect(self._reverse)
        void_button = QPushButton("作废误录")
        void_button.clicked.connect(self._void)
        actions.addWidget(reverse_button)
        actions.addWidget(void_button)
        layout.addLayout(actions)
        self.reload()

    def reload(self) -> None:
        rows = list_transactions(
            self.connection,
            self.ledger_id,
            TransactionFilter(direction=self.direction_filter.currentData(), keyword=self.keyword_filter.text()),
        )
        self.table.setRowCount(len(rows))
        direction_names = {"income": "收入", "expense": "支出"}
        status_names = {"active": "有效", "voided": "已作废", "reversed": "已冲销"}
        for index, row in enumerate(rows):
            values = (
                row["transaction_no"], row["occurred_on"], direction_names[row["direction"]],
                format_cents(row["amount_cents"]), row["category_name_snapshot"] or "—",
                row["purpose"], status_names[row["status"]],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.UserRole, row["id"])
                self.table.setItem(index, column, item)

    def _selected_id(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "请选择流水", "请先选择一条流水。")
            return None
        return self.table.item(row, 0).data(Qt.UserRole)

    def _add(self) -> None:
        dialog = TransactionDialog(self.connection, self.ledger_id, self)
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
            reverse_transaction(
                self.connection, transaction_id, reason,
                idempotency_key=str(uuid4()), occurred_on=date.today(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "冲销失败", str(exc))
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
            void_unrealized_transaction(self.connection, transaction_id, reason)
        except Exception as exc:
            QMessageBox.critical(self, "作废失败", str(exc))
            return
        self.reload()
        self.changed.emit()


class MainWindow(QMainWindow):
    NAVIGATION = ("总览", "收支流水", "报销", "预付款", "报表", "设置")

    def __init__(self, connection: sqlite3.Connection) -> None:
        super().__init__()
        self.connection = connection
        self.setWindowTitle("学院组织资金管理助手")
        self.setMinimumSize(1024, 680)
        container = QWidget()
        root = QHBoxLayout(container)
        self.navigation = QListWidget()
        self.navigation.setFixedWidth(180)
        self.navigation.addItems(self.NAVIGATION)
        self.pages = QStackedWidget()
        self.overview = self._build_overview()
        self.pages.addWidget(self.overview)
        ledger = self._ledger_row()
        self.transaction_page = TransactionPage(connection, ledger["id"], self) if ledger else self._build_placeholder("收支流水")
        if isinstance(self.transaction_page, TransactionPage):
            self.transaction_page.changed.connect(self._refresh_overview)
        self.pages.addWidget(self.transaction_page)
        for title in self.NAVIGATION[2:]:
            self.pages.addWidget(self._build_placeholder(title))
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)
        root.addWidget(self.navigation)
        root.addWidget(self.pages, 1)
        self.setCentralWidget(container)
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #f5f7fa; color: #1f2937; font-size: 14px; }
            QListWidget { background: #ffffff; border: none; padding: 12px; }
            QListWidget::item { padding: 12px; border-radius: 8px; margin: 2px; }
            QListWidget::item:selected { background: #e7f0ff; color: #165dff; }
            QFrame#card { background: white; border: 1px solid #e5e7eb; border-radius: 12px; }
            QLabel#heading { font-size: 24px; font-weight: 600; }
            QLabel#muted { color: #6b7280; }
            """
        )

    def _ledger_row(self):
        return self.connection.execute(
            "SELECT id, name, opening_balance_cents, opening_date FROM ledgers LIMIT 1"
        ).fetchone()

    def _build_overview(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        heading = QLabel("总览")
        heading.setObjectName("heading")
        layout.addWidget(heading)
        ledger = self._ledger_row()
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        if ledger:
            card_layout.addWidget(QLabel(ledger["name"]))
            totals = get_cash_totals(self.connection, ledger["id"])
            self.balance_value = QLabel(f"¥ {format_cents(totals.balance_cents)}")
            value = self.balance_value
            value.setStyleSheet("font-size: 30px; font-weight: 600;")
            card_layout.addWidget(value)
            self.balance_caption = QLabel(
                f"期初日 {ledger['opening_date']} · 收入 ¥ {format_cents(totals.income_cents)} · "
                f"支出 ¥ {format_cents(totals.expense_cents)}"
            )
            caption = self.balance_caption
            if totals.is_negative:
                value.setStyleSheet("font-size: 30px; font-weight: 600; color: #c2410c;")
        else:
            card_layout.addWidget(QLabel("尚未创建账本"))
            caption = QLabel("空账本不会显示模拟数据。")
        caption.setObjectName("muted")
        card_layout.addWidget(caption)
        layout.addWidget(card)
        layout.addStretch()
        return page

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
        color = "#c2410c" if totals.is_negative else "#1f2937"
        self.balance_value.setStyleSheet(f"font-size: 30px; font-weight: 600; color: {color};")

    @staticmethod
    def _build_placeholder(title: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        heading = QLabel(title)
        heading.setObjectName("heading")
        layout.addWidget(heading)
        message = QLabel("此模块尚未开放。当前版本仅用于验证阶段 A 的基础设施，不能用于正式记账。")
        message.setWordWrap(True)
        message.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        message.setObjectName("muted")
        layout.addWidget(message)
        layout.addStretch()
        return page
