import json
from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView,
)

from college_finance_manager.application.read_models import (
    get_transaction, list_categories, list_reversals, related_transactions, transaction_history,
)
from college_finance_manager.domain.money import format_cents, parse_yuan_to_cents
from college_finance_manager.ui.operations_pages import AttachmentManagerDialog
from college_finance_manager.ui.window_controls import LedgerComboBox as QComboBox, LedgerDateEdit as QDateEdit


LABELS = {
    "occurred_on": "日期", "direction": "类型", "amount_cents": "金额",
    "category_id": "类别", "purpose": "用途/来源", "item": "物品",
    "handler": "经办人", "payment_method": "支付方式", "note": "备注",
}
DIRECTIONS = {"income": "收入", "expense": "支出"}


class TransactionEditDialog(QDialog):
    def __init__(self, connection, row, field=None, parent=None):
        super().__init__(parent)
        self.row = row
        self.setWindowTitle(f"编辑流水 {row['transaction_no']}")
        self.setMinimumWidth(450)
        form = QFormLayout(self)
        self.fields = {
            "occurred_on": QDateEdit(QDate.fromString(row["occurred_on"], Qt.ISODate)),
            "direction": QComboBox(),
            "amount_cents": QLineEdit(format_cents(row["amount_cents"])),
            "category_id": QComboBox(),
            **{key: QLineEdit(row[key] or "") for key in ("purpose", "item", "handler", "payment_method")},
            "note": QPlainTextEdit(row["note"] or ""),
        }
        self.fields["note"].setMaximumHeight(84)
        self.fields["occurred_on"].setCalendarPopup(True)
        self.fields["occurred_on"].setDisplayFormat("yyyy-MM-dd")
        for value, label in DIRECTIONS.items():
            self.fields["direction"].addItem(label, value)
        direction = self.fields["direction"]
        direction.setCurrentIndex(direction.findData(row["direction"]))

        def reload_categories():
            combo = self.fields["category_id"]
            combo.clear()
            category_type = direction.currentData()
            if category_type == row["direction"]:
                combo.addItem(row["category_name_snapshot"] or "原类别", row["category_id"])
            else:
                combo.addItem("请选择类别", None)
            for category in list_categories(connection, row["ledger_id"], category_type):
                if category["is_active"] and combo.findData(category["id"]) < 0:
                    combo.addItem(category["name"], category["id"])

        direction.currentIndexChanged.connect(reload_categories)
        reload_categories()
        for key, widget in self.fields.items():
            form.addRow(LABELS[key], widget)
        self.reason = QLineEdit()
        self.reason.setPlaceholderText("必填，例如：录入有误")
        form.addRow("修改原因", self.reason)
        hint = QLabel("保存前备份；原流水保留，系统生成关联冲销和更正记录。")
        hint.setWordWrap(True)
        form.addRow(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("确认保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._confirm)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        if field in self.fields:
            self.fields[field].setFocus()

    def _confirm(self):
        try:
            values = {
                "occurred_on": self.fields["occurred_on"].date().toPython(),
                "direction": self.fields["direction"].currentData(),
                "amount_cents": parse_yuan_to_cents(self.fields["amount_cents"].text()),
                "category_id": self.fields["category_id"].currentData(),
                **{key: self.fields[key].text().strip() for key in ("purpose", "item", "handler", "payment_method")},
                "note": self.fields["note"].toPlainText().strip(),
            }
            if not values["purpose"] or not self.reason.text().strip():
                raise ValueError("用途和修改原因不能为空")
            if values["direction"] != self.row["direction"] and not values["category_id"]:
                raise ValueError("请选择与新收支方向匹配的类别")
            self.changes = {
                key: value for key, value in values.items()
                if (value.isoformat() if type(value) is date else value or None) != self.row[key]
            }
            if not self.changes:
                raise ValueError("没有需要保存的修改")
        except ValueError as exc:
            QMessageBox.warning(self, "请检查输入", str(exc))
            return
        self.accept()


def _display(key, value):
    if key == "amount_cents" and value is not None:
        return format_cents(value)
    if key == "direction":
        return DIRECTIONS.get(value, value)
    return value if value is not None and value != "" else "—"


class TransactionDetailDialog(QDialog):
    def __init__(self, connection, transaction_id, parent=None, *, paths=None):
        super().__init__(parent)
        self.connection = connection
        self.paths = paths
        self.resize(650, 570)
        layout = QVBoxLayout(self)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text, 1)
        layout.addWidget(QLabel("关联流水 · 双击查看"))
        self.related = QListWidget()
        self.related.setMaximumHeight(130)
        self.related.itemDoubleClicked.connect(lambda item: self.load(item.data(Qt.UserRole)))
        layout.addWidget(self.related)
        actions = QHBoxLayout()
        if paths is not None:
            attachments = QPushButton("查看关联凭证")
            attachments.clicked.connect(self._attachments)
            actions.addWidget(attachments)
        actions.addStretch()
        close = QPushButton("关闭")
        close.clicked.connect(self.reject)
        actions.addWidget(close)
        layout.addLayout(actions)
        self.load(transaction_id)

    def _attachments(self):
        AttachmentManagerDialog(
            self.connection, self.paths, self.row["ledger_id"], "transaction", self.row["id"], self, read_only=True,
        ).exec()

    def load(self, transaction_id):
        row = get_transaction(self.connection, transaction_id)
        if row is None:
            return
        self.row = row
        self.setWindowTitle(f"流水详情 · {row['transaction_no']}")
        lines = [f"编号：{row['transaction_no']}", f"创建时间：{row['created_at']}",
                 f"状态：{ {'active': '有效', 'reversed': '已冲销', 'voided': '已作废'}[row['status']] }"]
        for key, label in LABELS.items():
            lines.append(f"{label}：{_display(key, row['category_name_snapshot'] if key == 'category_id' else row[key])}")
        history = transaction_history(self.connection, transaction_id)
        if history:
            lines.append("\n修改历史")
            for entry in history:
                lines.append(f"{entry['created_at']} · {entry['reason'] or '—'}")
                summary = json.loads(entry["change_summary"])
                if "before" in summary and "after" in summary:
                    for key, label in LABELS.items():
                        lookup = "category_name" if key == "category_id" else key
                        before, after = summary["before"].get(lookup), summary["after"].get(lookup)
                        if before != after:
                            lines.append(f"  {label}：{_display(key, before)} → {_display(key, after)}")
                elif "from" in summary:
                    lines.append(f"  日期：{summary['from']} → {summary['to']}")
        self.text.setPlainText("\n".join(lines))
        self.related.clear()
        for linked in related_transactions(self.connection, transaction_id):
            role = "原流水" if linked["id"] in (row["reversal_of_id"], row["correction_of_id"]) else (
                "冲销流水" if linked["source"] == "reversal" else "更正流水"
            )
            item = QListWidgetItem(f"{role} · {linked['transaction_no']} · {linked['occurred_on']}")
            item.setData(Qt.UserRole, linked["id"])
            self.related.addItem(item)


class ReversalPage(QWidget):
    def __init__(self, connection, ledger_id, parent=None, *, paths=None):
        super().__init__(parent)
        self.connection, self.ledger_id = connection, ledger_id
        self.paths = paths
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        heading = QLabel("冲销记录")
        heading.setObjectName("heading")
        layout.addWidget(heading)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(("冲销编号", "原流水编号", "日期", "金额", "经办人", "原因"))
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.cellDoubleClicked.connect(lambda *_: self._view(False))
        layout.addWidget(self.table)
        actions = QHBoxLayout()
        for label, original in (("查看冲销详情", False), ("查看原流水", True)):
            button = QPushButton(label)
            button.clicked.connect(lambda _, original=original: self._view(original))
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        self.reload()

    def reload(self):
        rows = list_reversals(self.connection, self.ledger_id)
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            for col, value in enumerate((row["transaction_no"], row["original_no"], row["occurred_on"],
                                         format_cents(row["amount_cents"]), row["handler"] or "—", row["note"] or "—")):
                item = QTableWidgetItem(value)
                if col in (0, 1):
                    item.setData(Qt.UserRole, row["id"] if col == 0 else row["reversal_of_id"])
                self.table.setItem(index, col, item)

    def _view(self, original):
        index = self.table.currentRow()
        if index >= 0:
            TransactionDetailDialog(self.connection, self.table.item(index, int(original)).data(Qt.UserRole),
                                    self, paths=self.paths).exec()
