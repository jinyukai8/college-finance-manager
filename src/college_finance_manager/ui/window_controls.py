"""Shared dropdown chevrons and the main window's compact caption bar."""
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QComboBox, QDateEdit, QHBoxLayout, QPushButton, QWidget


def _chevron(widget, expanded):
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor("#526A60" if widget.isEnabled() else "#9AA9A3"), 1.4)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    x, y = widget.width() - 13, widget.height() / 2
    dy = -2 if expanded else 2
    painter.drawLine(QPointF(x - 4, y - dy), QPointF(x, y + dy))
    painter.drawLine(QPointF(x, y + dy), QPointF(x + 4, y - dy))


class LedgerComboBox(QComboBox):
    def __init__(self, *args):
        super().__init__(*args)
        self.setProperty("ledgerChevron", True)
        self.view().installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Show, QEvent.Hide):
            self.update()
        return super().eventFilter(watched, event)

    def paintEvent(self, event):
        super().paintEvent(event)
        _chevron(self, self.view().isVisible())


class LedgerDateEdit(QDateEdit):
    def __init__(self, *args):
        super().__init__(*args)
        self.setProperty("ledgerChevron", True)

    def setCalendarPopup(self, enabled):
        super().setCalendarPopup(enabled)
        if enabled:
            self.calendarWidget().installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Show, QEvent.Hide):
            self.update()
        return super().eventFilter(watched, event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.calendarPopup():
            _chevron(self, self.calendarWidget().isVisible())


class LedgerMenuButton(QPushButton):
    def __init__(self, *args):
        super().__init__(*args)
        self.setProperty("ledgerChevron", True)

    def setMenu(self, menu):
        old = self.menu()
        if old is not None:
            old.removeEventFilter(self)
        super().setMenu(menu)
        if menu is not None:
            menu.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Show, QEvent.Hide):
            self.update()
        return super().eventFilter(watched, event)

    def paintEvent(self, event):
        super().paintEvent(event)
        menu = self.menu()
        if menu is not None:
            _chevron(self, menu.isVisible())


class WindowBar(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self._drag_offset = None
        self._drag_origin = None
        self.setObjectName("windowBar")
        self.setFixedHeight(33)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addStretch()
        self.minimize_button = self._button(layout, "—", "最小化", window.showMinimized)
        self.maximize_button = self._button(layout, "□", "最大化", self.toggle_maximized)
        self.close_button = self._button(layout, "×", "关闭", window.close)
        self.close_button.setObjectName("windowCloseButton")

    def _button(self, layout, text, label, action):
        button = QPushButton(text)
        button.setObjectName("windowControl")
        button.setFixedSize(46, 33)
        button.setAccessibleName(label)
        button.setToolTip(label)
        button.clicked.connect(action)
        layout.addWidget(button)
        return button

    def toggle_maximized(self):
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def sync(self):
        maximized = self._window.isMaximized()
        label = "还原窗口" if maximized else "最大化"
        self.maximize_button.setText("❐" if maximized else "□")
        self.maximize_button.setAccessibleName(label)
        self.maximize_button.setToolTip(label)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_origin = event.globalPosition().toPoint()
            self._drag_offset = self._drag_origin - self._window.pos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            position = event.globalPosition().toPoint()
            if self._drag_origin is not None:
                if (position - self._drag_origin).manhattanLength() < QApplication.startDragDistance():
                    return
                self._drag_origin = None
                handle = self._window.windowHandle()
                if handle is not None and handle.startSystemMove():
                    self._drag_offset = None
                    return
            if not self._window.isMaximized():
                self._window.move(position - self._drag_offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        self._drag_origin = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = None
            self._drag_origin = None
            self.toggle_maximized()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)
