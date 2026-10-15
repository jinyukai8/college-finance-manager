"""Code-drawn ledger icon shared by the window and Windows executable."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


def create_app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.scale(size / 64, size / 64)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#0C7C6C"))
        painter.drawRoundedRect(QRectF(1, 1, 62, 62), 13, 13)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawRoundedRect(QRectF(16, 12, 34, 40), 4, 4)
        painter.setPen(QPen(QColor("#BDE7DE"), 3))
        painter.drawLine(23, 14, 23, 50)
        painter.setPen(QPen(QColor("#0C7C6C"), 3, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(30, 24, 42, 24)
        painter.drawLine(30, 32, 42, 32)
        painter.drawLine(30, 40, 38, 40)
        painter.end()
        icon.addPixmap(pixmap)
    return icon
