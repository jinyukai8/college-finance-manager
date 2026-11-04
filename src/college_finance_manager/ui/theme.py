from __future__ import annotations


APP_STYLE_SHEET = """
QMainWindow, QWidget#appRoot, QStackedWidget#contentStack, QDialog {
    background: #F6F8F7;
    color: #142822;
    font-family: "Microsoft YaHei UI", "Microsoft YaHei";
    font-size: 14px;
}

QWidget#sidebar {
    background: #FDFEFD;
    border-right: 1px solid #DDE7E2;
}

QLabel#brandMark {
    background: #08775D;
    color: white;
    border-radius: 10px;
    font-size: 20px;
    font-weight: 700;
    qproperty-alignment: AlignCenter;
}

QLabel#brandTitle {
    color: #172D27;
    font-size: 17px;
    font-weight: 700;
}

QLabel#brandSubtitle, QLabel#sidebarFooter {
    color: #65756F;
    font-size: 12px;
}

QListWidget#navigation {
    background: transparent;
    color: #263C35;
    border: none;
    outline: none;
    padding: 12px 11px;
}

QListWidget#navigation::item {
    padding: 0 16px;
    border-radius: 9px;
}

QListWidget#navigation::item:hover {
    background: #EDF6F2;
    color: #124D3E;
}

QListWidget#navigation::item:selected {
    background: #08775D;
    color: #FFFFFF;
    font-weight: 700;
}

QLabel#heading {
    color: #172D27;
    font-size: 25px;
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

QLineEdit, QComboBox, QDateEdit, QPlainTextEdit {
    min-height: 34px;
    padding: 0 10px;
    color: #17324D;
    background: #FFFFFF;
    border: 1px solid #C9D7E3;
    border-radius: 7px;
    selection-background-color: #BFE9DF;
}

QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QPlainTextEdit:focus {
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
    color: #253E36;
    background: #EDF4F0;
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

QFrame#fileDropArea {
    background: #F0FAF7;
    border: 2px dashed #A6CFC4;
    border-radius: 10px;
}

QFrame#fileDropArea[dragActive="true"] {
    background: #DDF3ED;
    border-color: #0C7C6C;
}

QPushButton#noteButton {
    min-height: 28px;
    padding: 0 2px;
    color: #087A67;
    border: none;
    background: transparent;
}

QPushButton#noteButton:hover {
    background: #DDF3ED;
}

QFrame#sidebarSeparator { background: #E5ECE8; }
QFrame#headingMarker { background: #08775D; border-radius: 2px; }
QFrame#ledgerBanner {
    border-radius: 10px;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #F6F8F7,stop:0.65 #E7F3F2,stop:1 #F3F8F2);
    min-height: 44px;
}
QComboBox[ledgerChevron="true"]::down-arrow, QDateEdit[ledgerChevron="true"]::down-arrow,
QPushButton[ledgerChevron="true"]::menu-indicator { image: none; width: 0; height: 0; }
QComboBox[ledgerChevron="true"], QDateEdit[ledgerChevron="true"],
QPushButton[ledgerChevron="true"] { padding-right: 26px; }
QWidget#windowBar { background: #F6F8F7; border-bottom: 1px solid #E4EBE7; }
QPushButton#windowControl, QPushButton#windowCloseButton {
    min-height: 0; padding: 0; border: none; border-radius: 0;
    background: transparent; color: #253E36; font-size: 16px; font-weight: 400;
}
QPushButton#windowControl:hover { background: #E4EFEA; }
QPushButton#windowCloseButton:hover { background: #BD3633; color: white; }
QFrame#ledgerTableCard { background: white; border: 1px solid #E0E9E3; border-radius: 12px; }
QTableWidget#ledgerTable { border: none; border-radius: 0; alternate-background-color: #FBFDFC; }
QTableWidget#ledgerTable::item { padding: 3px; border-bottom: 1px solid #EDF2EF; }
QTableWidget#ledgerTable::item:hover:!selected { background: #F0F8F4; }
QTableWidget#ledgerTable QHeaderView::section { padding: 5px 2px; }
QPushButton#rowAction {
    padding: 0; min-height: 23px; border: none; background: transparent; border-radius: 4px;
}
QPushButton#rowAction:hover { background: #E3F3EC; }
QMenu {
    background: white; border: 1px solid #DDE7E2; padding: 4px; color: #243B33;
}
QMenu::item { padding: 7px 16px; }
QMenu::item:selected { background: #E4F3EC; }
"""
