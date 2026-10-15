from __future__ import annotations


APP_STYLE_SHEET = """
QMainWindow, QWidget#appRoot, QStackedWidget#contentStack, QDialog {
    background: #F4F7FB;
    color: #19324A;
    font-family: "Microsoft YaHei UI", "Microsoft YaHei";
    font-size: 14px;
}

QWidget#sidebar {
    background: #123247;
    border: none;
}

QLabel#brandMark {
    background: #25A18E;
    color: white;
    border-radius: 10px;
    font-size: 20px;
    font-weight: 700;
    qproperty-alignment: AlignCenter;
}

QLabel#brandTitle {
    color: #FFFFFF;
    font-size: 19px;
    font-weight: 700;
}

QLabel#brandSubtitle, QLabel#sidebarFooter {
    color: #AFC4D2;
    font-size: 12px;
}

QListWidget#navigation {
    background: transparent;
    color: #DCE8EF;
    border: none;
    outline: none;
    padding: 8px 12px;
}

QListWidget#navigation::item {
    padding: 0 16px;
    border-radius: 9px;
}

QListWidget#navigation::item:hover {
    background: #1A425A;
    color: #FFFFFF;
}

QListWidget#navigation::item:selected {
    background: #E5F7F2;
    color: #087A67;
    font-weight: 700;
}

QLabel#heading {
    color: #102A43;
    font-size: 27px;
    font-weight: 700;
}

QLabel#pageSubtitle, QLabel#muted, QLabel#metricLabel {
    color: #6B7F93;
}

QFrame#balanceCard {
    background: #0C6E61;
    border: 1px solid #0A6257;
    border-radius: 16px;
}

QLabel#heroEyebrow {
    color: #BFE9DF;
    font-size: 13px;
    font-weight: 600;
}

QLabel#ledgerName {
    color: #FFFFFF;
    font-size: 17px;
    font-weight: 600;
}

QLabel#balanceValue {
    color: #FFFFFF;
    font-size: 36px;
    font-weight: 700;
}

QLabel#heroCaption {
    color: #D5F1EA;
    font-size: 13px;
}

QFrame#metricCard, QFrame#filterPanel, QFrame#card {
    background: #FFFFFF;
    border: 1px solid #DDE6EE;
    border-radius: 12px;
}

QLabel#metricValue {
    color: #173B57;
    font-size: 22px;
    font-weight: 700;
}

QLabel#sectionTitle {
    color: #17324D;
    font-size: 18px;
    font-weight: 700;
}

QPushButton {
    min-height: 34px;
    padding: 0 15px;
    color: #24435E;
    background: #FFFFFF;
    border: 1px solid #C9D7E3;
    border-radius: 8px;
    font-weight: 600;
}

QPushButton:hover {
    background: #F0F6FA;
    border-color: #91AABE;
}

QPushButton:pressed {
    background: #E4EDF4;
}

QPushButton:disabled {
    color: #9AAABC;
    background: #EDF2F6;
    border-color: #D9E2EA;
}

QPushButton#primaryButton {
    color: #FFFFFF;
    background: #0C7C6C;
    border-color: #0C7C6C;
}

QPushButton#primaryButton:hover {
    background: #096A5D;
    border-color: #096A5D;
}

QPushButton#dangerButton {
    color: #B42318;
    background: #FFF7F6;
    border-color: #F3C8C3;
}

QPushButton#dangerButton:hover {
    background: #FDEBE9;
    border-color: #E99B93;
}

QLineEdit, QComboBox, QDateEdit {
    min-height: 34px;
    padding: 0 10px;
    color: #17324D;
    background: #FFFFFF;
    border: 1px solid #C9D7E3;
    border-radius: 7px;
    selection-background-color: #BFE9DF;
}

QLineEdit:focus, QComboBox:focus, QDateEdit:focus {
    border: 2px solid #159A85;
}

QComboBox::drop-down, QDateEdit::drop-down {
    width: 26px;
    border: none;
}

QCheckBox {
    spacing: 7px;
    color: #405C73;
}

QTableWidget {
    background: #FFFFFF;
    alternate-background-color: #F7FAFC;
    color: #203A52;
    border: 1px solid #DDE6EE;
    border-radius: 10px;
    gridline-color: transparent;
    selection-background-color: #DDF3ED;
    selection-color: #0B594E;
    outline: none;
}

QTableWidget::item {
    padding: 7px 8px;
    border-bottom: 1px solid #EDF2F6;
}

QHeaderView::section {
    color: #526A7E;
    background: #F2F6F9;
    border: none;
    border-bottom: 1px solid #D8E2EA;
    padding: 9px 8px;
    font-weight: 700;
}

QScrollBar:vertical {
    width: 10px;
    margin: 4px 2px;
    background: transparent;
}

QScrollBar::handle:vertical {
    min-height: 28px;
    background: #B8C7D3;
    border-radius: 4px;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QToolTip {
    color: #FFFFFF;
    background: #17324D;
    border: none;
    padding: 6px;
}
"""
