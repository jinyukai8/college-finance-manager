from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit, QPushButton, QTableWidget, QVBoxLayout


class NoteDialog(QDialog):
    def __init__(self, note: str, parent=None, editable=False) -> None:
        super().__init__(parent)
        self.setWindowTitle("查看备注")
        self.resize(560, 360)
        layout = QVBoxLayout(self)
        editor = QPlainTextEdit()
        editor.setPlainText(note)
        editor.setReadOnly(True)
        layout.addWidget(editor)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("关闭")
        if editable:
            edit = buttons.addButton("编辑备注", QDialogButtonBox.AcceptRole)
            edit.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


def set_note_cell(table: QTableWidget, row: int, column: int, note: str | None, edit=None) -> None:
    """Keep full note text selectable in a read-only viewer without widening rows."""
    from PySide6.QtWidgets import QTableWidgetItem

    if not note or not note.strip():
        table.removeCellWidget(row, column)
        table.setItem(row, column, QTableWidgetItem("—"))
        return
    item = QTableWidgetItem("")
    item.setSizeHint(QSize(64, 34))
    item.setData(Qt.UserRole, note)
    table.setItem(row, column, item)
    button = QPushButton("查看")
    button.setObjectName("noteButton")
    button.setToolTip(note[:200] + ("…" if len(note) > 200 else ""))
    def open_note():
        if NoteDialog(note, table, editable=edit is not None).exec() == QDialog.Accepted and edit:
            edit()
    button.clicked.connect(open_note)
    table.setCellWidget(row, column, button)
