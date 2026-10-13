from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Callable
from uuid import uuid4

from PySide6.QtCore import QDate, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from college_finance_manager.application.advances import (
    cancel_advance,
    create_advance,
    pay_advance,
    record_refund,
    record_settlement,
)
from college_finance_manager.application.file_operations import (
    add_attachment,
    create_manual_backup,
    export_attachment,
    export_report,
    resolve_verified_attachment,
    verify_backup,
)
from college_finance_manager.application.read_models import (
    list_advances,
    list_attachments,
    list_categories,
    list_reconciliations,
    list_recycle_bin_records,
    list_reimbursements,
)
from college_finance_manager.application.reconciliation import record_reconciliation
from college_finance_manager.application.reimbursements import (
    cancel_reimbursement,
    create_reimbursement,
    mark_awaiting_payment,
    pay_reimbursement,
    reject_reimbursement,
)
from college_finance_manager.application.transactions import (
    create_category,
    rename_category,
    set_category_active,
)
from college_finance_manager.domain.money import format_cents, parse_yuan_to_cents
from college_finance_manager.infrastructure.paths import AppPaths


def _heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("heading")
    return label


def _selected_id(table: QTableWidget) -> str | None:
    row = table.currentRow()
    if row < 0:
        QMessageBox.information(table, "请选择记录", "请先选择一条记录。")
        return None
    return table.item(row, 0).data(Qt.UserRole)


def _choose_category(parent, connection, ledger_id, category_type, title) -> str | None:
    rows = [row for row in list_categories(connection, ledger_id, category_type) if row["is_active"]]
    if not rows:
        QMessageBox.warning(parent, title, "没有可用类别，请先在设置中配置类别。")
        return None
    names = [row["name"] for row in rows]
    selected, accepted = QInputDialog.getItem(parent, title, "类别", names, 0, False)
    if not accepted:
        return None
    return rows[names.index(selected)]["id"]


class BusinessEntryDialog(QDialog):
    def __init__(self, title: str, person_label: str, purpose_label: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        layout = QFormLayout(self)
        self.person = QLineEdit()
        self.amount = QLineEdit()
        self.amount.setPlaceholderText("例如：300.00")
        self.purpose = QLineEdit()
        self.occurred_on = QDateEdit(QDate.currentDate())
        self.occurred_on.setCalendarPopup(True)
        self.note = QLineEdit()
        layout.addRow(person_label, self.person)
        layout.addRow("金额（元）", self.amount)
        layout.addRow(purpose_label, self.purpose)
        layout.addRow("日期", self.occurred_on)
        layout.addRow("备注（可选）", self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> tuple[str, int, str, date, str]:
        return (
            self.person.text(), parse_yuan_to_cents(self.amount.text()), self.purpose.text(),
            self.occurred_on.date().toPython(), self.note.text(),
        )


class AttachmentManagerDialog(QDialog):
    def __init__(self, connection, paths, ledger_id, entity_type, entity_id, parent=None) -> None:
        super().__init__(parent)
        self.connection = connection
        self.paths = paths
        self.ledger_id = ledger_id
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.setWindowTitle("凭证管理")
        self.resize(700, 420)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(("文件名", "类型", "大小", "导入时间"))
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        layout.addWidget(self.table)
        actions = QHBoxLayout()
        add = QPushButton("导入凭证")
        add.clicked.connect(self._add)
        open_button = QPushButton("打开")
        open_button.clicked.connect(self._open)
        export_button = QPushButton("导出副本")
        export_button.clicked.connect(self._export)
        actions.addWidget(add)
        actions.addStretch()
        actions.addWidget(open_button)
        actions.addWidget(export_button)
        layout.addLayout(actions)
        self.reload()

    def reload(self) -> None:
        rows = list_attachments(self.connection, self.entity_type, self.entity_id)
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (row["original_name"], row["media_type"], f"{row['size_bytes'] / 1024:.1f} KB", row["imported_at"])
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.UserRole, row["id"])
                self.table.setItem(index, column, item)

    def _attachment_id(self) -> str | None:
        return _selected_id(self.table)

    def _add(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "选择凭证", "", "凭证 (*.jpg *.jpeg *.png *.pdf)")
        if not filename:
            return
        try:
            add_attachment(
                self.connection, paths=self.paths, ledger_id=self.ledger_id,
                entity_type=self.entity_type, entity_id=self.entity_id, source_path=Path(filename),
            )
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        self.reload()

    def _open(self) -> None:
        attachment_id = self._attachment_id()
        if not attachment_id:
            return
        try:
            path = resolve_verified_attachment(self.connection, paths=self.paths, attachment_id=attachment_id)
        except Exception as exc:
            QMessageBox.critical(self, "无法打开", str(exc))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _export(self) -> None:
        attachment_id = self._attachment_id()
        if not attachment_id:
            return
        row = self.table.currentRow()
        original_name = self.table.item(row, 0).text()
        filename, _ = QFileDialog.getSaveFileName(self, "导出凭证", original_name)
        if not filename:
            return
        try:
            export_attachment(
                self.connection, paths=self.paths, attachment_id=attachment_id, destination=Path(filename)
            )
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))


class ReimbursementPage(QWidget):
    changed = Signal()

    def __init__(self, connection, paths: AppPaths, ledger_id: str, parent=None) -> None:
        super().__init__(parent)
        self.connection, self.paths, self.ledger_id = connection, paths, ledger_id
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        top = QHBoxLayout()
        top.addWidget(_heading("报销"))
        top.addStretch()
        add = QPushButton("新增申请")
        add.clicked.connect(self._add)
        top.addWidget(add)
        layout.addLayout(top)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(("申请人", "申请日期", "金额", "用途", "状态", "关联流水"))
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        layout.addWidget(self.table)
        actions = QHBoxLayout()
        for text, handler in (("通过", self._approve), ("确认付款", self._pay), ("驳回", self._reject), ("取消", self._cancel), ("凭证", self._attachments)):
            button = QPushButton(text)
            button.clicked.connect(handler)
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        self.reload()

    def reload(self):
        rows = list_reimbursements(self.connection, self.ledger_id)
        names = {"pending": "待处理", "awaiting_payment": "待付款", "completed": "已完成", "rejected": "已驳回", "cancelled": "已取消"}
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            values = (row["applicant"], row["applied_on"], format_cents(row["amount_cents"]), row["purpose"], names[row["status"]], row["transaction_no"] or "—")
            for j, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if j == 0:
                    item.setData(Qt.UserRole, row["id"])
                    item.setData(Qt.UserRole + 1, row["status"])
                self.table.setItem(i, j, item)

    def _id(self):
        return _selected_id(self.table)

    def _run(self, action, success=True):
        try:
            action()
        except Exception as exc:
            QMessageBox.critical(self, "操作失败", str(exc))
            return
        self.reload()
        if success:
            self.changed.emit()

    def _add(self):
        dialog = BusinessEntryDialog("新增报销", "申请人", "用途", self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            person, amount, purpose, day, note = dialog.values()
        except Exception as exc:
            QMessageBox.critical(self, "输入无效", str(exc))
            return
        self._run(lambda: create_reimbursement(self.connection, ledger_id=self.ledger_id, applicant=person, amount_cents=amount, purpose=purpose, applied_on=day, note=note))

    def _approve(self):
        item = self._id()
        if item:
            self._run(lambda: mark_awaiting_payment(self.connection, item))

    def _pay(self):
        item = self._id()
        if not item:
            return
        category = _choose_category(self, self.connection, self.ledger_id, "expense", "报销付款")
        if category:
            self._run(lambda: pay_reimbursement(self.connection, item, category_id=category, paid_on=date.today(), idempotency_key=str(uuid4())))

    def _reason_action(self, title, label, function):
        item = self._id()
        if not item:
            return
        reason, ok = QInputDialog.getText(self, title, label)
        if ok:
            self._run(lambda: function(self.connection, item, reason))

    def _reject(self):
        self._reason_action("驳回报销", "原因", reject_reimbursement)

    def _cancel(self):
        self._reason_action("取消报销", "原因", cancel_reimbursement)

    def _attachments(self):
        item = self._id()
        if item:
            AttachmentManagerDialog(self.connection, self.paths, self.ledger_id, "reimbursement", item, self).exec()


class AdvancePage(QWidget):
    changed = Signal()

    def __init__(self, connection, paths: AppPaths, ledger_id: str, parent=None) -> None:
        super().__init__(parent)
        self.connection, self.paths, self.ledger_id = connection, paths, ledger_id
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        top = QHBoxLayout()
        top.addWidget(_heading("预付款"))
        top.addStretch()
        add = QPushButton("新增预付款")
        add.clicked.connect(self._add)
        top.addWidget(add)
        layout.addLayout(top)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(("收款人", "申请日期", "预付金额", "已核销", "已退款", "待结清", "状态"))
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)
        actions = QHBoxLayout()
        for text, handler in (("确认支付", self._pay), ("费用核销", self._settle), ("收到退款", self._refund), ("取消", self._cancel), ("凭证", self._attachments)):
            button = QPushButton(text)
            button.clicked.connect(handler)
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        self.reload()

    def reload(self):
        rows = list_advances(self.connection, self.ledger_id)
        names = {"pending_payment": "待支付", "pending_settlement": "待核销", "partially_settled": "部分核销", "settled": "已结清", "cancelled": "已取消"}
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            remaining = row["amount_cents"] - row["settled_cents"] - row["refunded_cents"]
            values = (row["recipient"], row["requested_on"], format_cents(row["amount_cents"]), format_cents(row["settled_cents"]), format_cents(row["refunded_cents"]), format_cents(remaining), names[row["status"]])
            for j, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if j == 0:
                    item.setData(Qt.UserRole, row["id"])
                self.table.setItem(i, j, item)

    def _id(self):
        return _selected_id(self.table)

    def _run(self, action):
        try:
            action()
        except Exception as exc:
            QMessageBox.critical(self, "操作失败", str(exc))
            return
        self.reload()
        self.changed.emit()

    def _add(self):
        dialog = BusinessEntryDialog("新增预付款", "收款人", "用途", self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            person, amount, purpose, day, note = dialog.values()
        except Exception as exc:
            QMessageBox.critical(self, "输入无效", str(exc))
            return
        self._run(lambda: create_advance(self.connection, ledger_id=self.ledger_id, recipient=person, amount_cents=amount, purpose=purpose, requested_on=day, note=note))

    def _pay(self):
        item = self._id()
        if not item:
            return
        category = _choose_category(self, self.connection, self.ledger_id, "expense", "支付预付款")
        if category:
            self._run(lambda: pay_advance(self.connection, item, category_id=category, paid_on=date.today(), idempotency_key=str(uuid4())))

    def _amount(self, title):
        text, ok = QInputDialog.getText(self, title, "金额（元）")
        if not ok:
            return None
        try:
            return parse_yuan_to_cents(text)
        except Exception as exc:
            QMessageBox.critical(self, "输入无效", str(exc))
            return None

    def _settle(self):
        item = self._id()
        if not item:
            return
        amount = self._amount("费用核销")
        category = _choose_category(self, self.connection, self.ledger_id, "expense", "费用核销") if amount else None
        if amount and category:
            self._run(lambda: record_settlement(self.connection, item, amount_cents=amount, occurred_on=date.today(), category_id=category, note="界面核销", idempotency_key=str(uuid4())))

    def _refund(self):
        item = self._id()
        if not item:
            return
        amount = self._amount("收到退款")
        category = _choose_category(self, self.connection, self.ledger_id, "income", "收到退款") if amount else None
        if amount and category:
            self._run(lambda: record_refund(self.connection, item, amount_cents=amount, occurred_on=date.today(), income_category_id=category, note="实际收到退款", idempotency_key=str(uuid4())))

    def _cancel(self):
        item = self._id()
        if not item:
            return
        reason, ok = QInputDialog.getText(self, "取消预付款", "原因")
        if ok:
            self._run(lambda: cancel_advance(self.connection, item, reason))

    def _attachments(self):
        item = self._id()
        if item:
            AttachmentManagerDialog(self.connection, self.paths, self.ledger_id, "advance", item, self).exec()


class ReportsPage(QWidget):
    def __init__(self, connection, ledger_id: str, parent=None) -> None:
        super().__init__(parent)
        self.connection, self.ledger_id = connection, ledger_id
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.addWidget(_heading("报表与核对"))
        controls = QHBoxLayout()
        self.date_from = QDateEdit(QDate(QDate.currentDate().year(), 1, 1))
        self.date_to = QDateEdit(QDate.currentDate())
        self.date_from.setCalendarPopup(True)
        self.date_to.setCalendarPopup(True)
        export_button = QPushButton("导出 Excel")
        export_button.clicked.connect(self._export)
        reconcile_button = QPushButton("新增余额核对")
        reconcile_button.clicked.connect(self._reconcile)
        controls.addWidget(QLabel("开始"))
        controls.addWidget(self.date_from)
        controls.addWidget(QLabel("结束"))
        controls.addWidget(self.date_to)
        controls.addWidget(export_button)
        controls.addWidget(reconcile_button)
        controls.addStretch()
        layout.addLayout(controls)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(("核对日期", "账面金额", "人工金额", "差额", "备注"))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)
        self.reload()

    def reload(self):
        rows = list_reconciliations(self.connection, self.ledger_id)
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate((row["reconciled_on"], format_cents(row["book_balance_cents"]), format_cents(row["actual_balance_cents"]), format_cents(row["difference_cents"]), row["note"] or "")):
                self.table.setItem(i, j, QTableWidgetItem(str(value)))

    def _export(self):
        filename, _ = QFileDialog.getSaveFileName(self, "导出 Excel", "资金报表.xlsx", "Excel (*.xlsx)")
        if not filename:
            return
        try:
            export_report(self.connection, ledger_id=self.ledger_id, date_from=self.date_from.date().toPython(), date_to=self.date_to.date().toPython(), destination=Path(filename))
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        QMessageBox.information(self, "导出完成", filename)

    def _reconcile(self):
        amount, ok = QInputDialog.getText(self, "余额核对", "人工核对金额（元）")
        if not ok:
            return
        note, accepted = QInputDialog.getText(self, "余额核对", "备注（可选）")
        if not accepted:
            return
        try:
            record_reconciliation(self.connection, ledger_id=self.ledger_id, reconciled_on=date.today(), actual_balance_cents=parse_yuan_to_cents(amount, allow_zero=True, allow_negative=True), note=note)
        except Exception as exc:
            QMessageBox.critical(self, "核对失败", str(exc))
            return
        self.reload()


class SettingsPage(QWidget):
    categories_changed = Signal()

    def __init__(self, connection, paths: AppPaths, ledger_id: str, restore_callback: Callable[[Path], None], parent=None) -> None:
        super().__init__(parent)
        self.connection, self.paths, self.ledger_id, self.restore_callback = connection, paths, ledger_id, restore_callback
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.addWidget(_heading("设置与备份"))
        info = QLabel(f"数据目录：{paths.root}\n凭证目录：{paths.attachments}\n备份目录：{paths.backups}")
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(info)
        backup = QPushButton("立即创建完整备份")
        backup.clicked.connect(self._backup)
        verify = QPushButton("验证备份文件")
        verify.clicked.connect(self._verify)
        restore = QPushButton("从备份恢复…")
        restore.clicked.connect(self._restore)
        layout.addWidget(backup)
        layout.addWidget(verify)
        layout.addWidget(restore)
        warning = QLabel("恢复前会自动创建并验证当前数据备份；原数据库与凭证会保留在恢复回滚目录。")
        warning.setWordWrap(True)
        warning.setObjectName("muted")
        layout.addWidget(warning)
        category_title = QLabel("收支类别")
        category_title.setStyleSheet("font-size: 18px; font-weight: 600; margin-top: 12px;")
        layout.addWidget(category_title)
        self.category_table = QTableWidget(0, 3)
        self.category_table.setHorizontalHeaderLabels(("类型", "名称", "状态"))
        self.category_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.category_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.category_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.category_table)
        category_actions = QHBoxLayout()
        add_category = QPushButton("新增类别")
        add_category.clicked.connect(self._add_category)
        rename = QPushButton("重命名")
        rename.clicked.connect(self._rename_category)
        toggle = QPushButton("启用/停用")
        toggle.clicked.connect(self._toggle_category)
        category_actions.addWidget(add_category)
        category_actions.addWidget(rename)
        category_actions.addWidget(toggle)
        category_actions.addStretch()
        layout.addLayout(category_actions)
        layout.addStretch()
        self._reload_categories()
        self.categories_changed.emit()

    def _reload_categories(self):
        rows = list_categories(self.connection, self.ledger_id)
        self.category_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            values = ("收入" if row["type"] == "income" else "支出", row["name"], "启用" if row["is_active"] else "停用")
            for j, value in enumerate(values):
                item = QTableWidgetItem(value)
                if j == 0:
                    item.setData(Qt.UserRole, row["id"])
                    item.setData(Qt.UserRole + 1, bool(row["is_active"]))
                self.category_table.setItem(i, j, item)

    def _category_id(self):
        return _selected_id(self.category_table)

    def _add_category(self):
        kind_name, ok = QInputDialog.getItem(self, "新增类别", "类型", ["收入", "支出"], 0, False)
        if not ok:
            return
        name, ok = QInputDialog.getText(self, "新增类别", "名称")
        if not ok:
            return
        try:
            create_category(self.connection, self.ledger_id, "income" if kind_name == "收入" else "expense", name)
        except Exception as exc:
            QMessageBox.critical(self, "新增失败", str(exc))
            return
        self._reload_categories()
        self.categories_changed.emit()

    def _rename_category(self):
        category_id = self._category_id()
        if not category_id:
            return
        name, ok = QInputDialog.getText(self, "重命名类别", "新名称")
        if not ok:
            return
        try:
            rename_category(self.connection, category_id, name)
        except Exception as exc:
            QMessageBox.critical(self, "重命名失败", str(exc))
            return
        self._reload_categories()
        self.categories_changed.emit()

    def _toggle_category(self):
        category_id = self._category_id()
        if not category_id:
            return
        active = self.category_table.item(self.category_table.currentRow(), 0).data(Qt.UserRole + 1)
        try:
            set_category_active(self.connection, category_id, not active)
        except Exception as exc:
            QMessageBox.critical(self, "更新失败", str(exc))
            return
        self._reload_categories()
        self.categories_changed.emit()

    def _backup(self):
        try:
            path = create_manual_backup(self.connection, paths=self.paths)
        except Exception as exc:
            QMessageBox.critical(self, "备份失败", str(exc))
            return
        QMessageBox.information(self, "备份完成", str(path))

    def _select_backup(self) -> Path | None:
        filename, _ = QFileDialog.getOpenFileName(self, "选择备份", str(self.paths.backups), "资金管理备份 (*.cfmbackup)")
        return Path(filename) if filename else None

    def _verify(self):
        path = self._select_backup()
        if not path:
            return
        try:
            manifest = verify_backup(path)
        except Exception as exc:
            QMessageBox.critical(self, "验证失败", str(exc))
            return
        QMessageBox.information(self, "验证通过", f"备份时间：{manifest['created_at']}\n文件数：{len(manifest['files'])}")

    def _restore(self):
        path = self._select_backup()
        if not path:
            return
        try:
            verify_backup(path)
        except Exception as exc:
            QMessageBox.critical(self, "备份无效", str(exc))
            return
        answer = QMessageBox.question(
            self, "确认恢复",
            "应用将先备份当前数据，再切换到所选备份并退出。请重新启动应用完成恢复。是否继续？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.restore_callback(path)


class RecycleBinPage(QWidget):
    """只读展示作废、驳回和取消记录；不物理删除财务历史。"""

    def __init__(self, connection: sqlite3.Connection, ledger_id: str, parent=None) -> None:
        super().__init__(parent)
        self.connection = connection
        self.ledger_id = ledger_id
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        top = QHBoxLayout()
        top.addWidget(_heading("回收站"))
        top.addStretch()
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.reload)
        top.addWidget(refresh)
        layout.addLayout(top)
        explanation = QLabel(
            "这里集中保留作废流水、已驳回或已取消的业务记录。"
            "为保护财务历史，记录不会被物理删除，也不会在这里直接恢复余额。"
        )
        explanation.setWordWrap(True)
        explanation.setObjectName("muted")
        layout.addWidget(explanation)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(("类型", "编号", "日期", "摘要", "状态", "原因"))
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        layout.addWidget(self.table, 1)
        self.reload()

    def reload(self) -> None:
        records = list_recycle_bin_records(self.connection, self.ledger_id)
        self.table.setRowCount(len(records))
        entity_names = {
            "transaction": "收支流水",
            "reimbursement": "报销",
            "advance": "预付款",
        }
        status_names = {
            "voided": "已作废",
            "rejected": "已驳回",
            "cancelled": "已取消",
        }
        for index, record in enumerate(records):
            values = (
                entity_names.get(record["entity_type"], record["entity_type"]),
                record["record_no"],
                record["record_date"],
                record["summary"],
                status_names.get(record["status"], record["status"]),
                record["reason"] or "—",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.UserRole, record["entity_id"])
                self.table.setItem(index, column, item)
