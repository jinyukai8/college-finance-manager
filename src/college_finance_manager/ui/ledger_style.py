"""Small, resolution-independent artwork and table accents for the ledger UI."""
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QStyledItemDelegate, QStyle, QStyleOptionViewItem


PATHS = {
    "flask": "M9 3h6m-5 0v7l-5 8a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-8V3M8 15h8",
    "home": "M3 11l9-8 9 8M6 10v11h5v-6h3v6h4V10",
    "cash": "M4 6c0-4 16-4 16 0s-16 4-16 0v12c0 4 16 4 16 0V6M4 12c0 4 16 4 16 0",
    "history": "M3 9a9 9 0 1 1 0 6m0-12v6h6m3-2v6l4 2",
    "trash": "M4 6h16M9 6V3h6v3m3 0-1 15H7L6 6m4 4v7m4-7v7",
    "settings": "M10 3h4l1 3 3 1 3 3v4l-3 3-3 1-1 3h-4l-1-3-3-1-3-3v-4l3-3 3-1zM15 12a3 3 0 1 0-6 0 3 3 0 0 0 6 0",
    "plus": "M12 4v16M4 12h16",
    "download": "M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5",
    "layers": "M12 3l9 5-9 5-9-5zm-9 9 9 5 9-5M3 16l9 5 9-5",
    "file": "M6 3h8l4 4v14H6zM14 3v5h4M9 12h6m-6 4h6",
    "edit": "M4 16 16 4l4 4L8 20H4zm10-10 4 4M4 22h16",
    "filter": "M3 4h18l-7 8v6l-4 2v-8z",
    "left": "M15 5l-7 7 7 7",
    "right": "M9 5l7 7-7 7",
}


def ledger_icon(name, color="#08775D"):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="{PATHS[name]}" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def campus_banner():
    """Decorative campus linework, kept separate from the live title and controls."""
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 440 54">
      <defs><linearGradient id="glass" x2="0" y2="1">
        <stop stop-color="#D6EDEB"/><stop offset="1" stop-color="#83C4BE"/>
      </linearGradient></defs>
      <path d="M50 34q11-16 26-5 9-15 23 4h38M169 20q16-17 32-3 9-12 20 3h23"
        fill="none" stroke="#FFF" stroke-width="3" opacity=".8"/>
      <path d="M126 54q14-16 34-8 20-16 42-5 22-14 51 2 24-11 55 11z" fill="#CCE7D8"/>
      <path d="M205 54V33l78-20 68 15v26z" fill="#D8E7E0"/>
      <path d="M283 13l69 15v26h-69z" fill="#B5D4CB"/>
      <path d="M213 36l64-17v35h-64zm77-16 55 12v22h-55z" fill="url(#glass)"/>
      <path d="M210 34l73-20 67 14M218 44l57-14m16 1 53 11M219 51l55-9m18-1 52 9M227 32v22m13-25v25m13-29v29m13-33v33m35-30v30m12-28v28m13-26v26m12-23v23"
        fill="none" stroke="#F5FBF8" stroke-width="1.8"/>
      <path d="M205 33l78-21 71 16" fill="none" stroke="#609B91" stroke-width="2.8"/>
      <path d="M187 54q-4-8 7-11 8-6 13 3 10-3 12 8m116 0q1-9 12-8 4-10 15-4 7 0 8 12" fill="#9CCCAD"/>
      <path d="M3 0q17 8 40 8t41 7m289-15q20 10 43 7t22 10" fill="none" stroke="#C7A966" stroke-width="1.5"/>
      <path d="M14 3q13-4 15 7-10 5-15-7m21 4q13-4 15 8-10 5-15-8m21 2q12-3 15 8-12 5-15-8m327-6q12-4 14 7-11 6-14-7m21 4q13-3 15 7-12 6-15-7m19 3q13-3 15 8-11 4-15-8" fill="#E6C777"/>
    </svg>
    """
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pixmap = QPixmap(880, 108)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return pixmap


class BadgeDelegate(QStyledItemDelegate):
    COLORS = {
        "收入": ("#E3F4DA", "#28652D"), "支出": ("#FCE4E1", "#A52F28"),
        "有效": ("#E2F3D5", "#316523"), "未提交": ("#EEF1F0", "#43544F"),
    }

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        bg, fg = self.COLORS.get(text, ("#DFEDFF", "#245CB5"))
        opt.text = ""
        opt.widget.style().drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        width = min(opt.rect.width() - 6, opt.fontMetrics.horizontalAdvance(text) + 12)
        rect = QRectF(opt.rect.x() + (opt.rect.width() - width) / 2,
                      opt.rect.center().y() - 11, width, 23)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(bg))
        painter.drawRoundedRect(rect, 5, 5)
        painter.setPen(QColor(fg))
        painter.setFont(opt.font)
        painter.drawText(rect, Qt.AlignCenter, opt.fontMetrics.elidedText(text, Qt.ElideRight, max(0, int(width) - 5)))
        painter.restore()
