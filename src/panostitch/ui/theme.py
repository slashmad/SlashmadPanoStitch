DARK_THEME_QSS = """
QWidget {
    background: #141618;
    color: #e4e7ea;
    font-family: "Noto Sans", "DejaVu Sans", sans-serif;
    font-size: 12px;
}

QMainWindow {
    background: #111315;
}

QLabel {
    background: transparent;
}

QFrame#Sidebar {
    background: #171a1d;
    border-right: 1px solid #262c31;
}

QFrame#PanelCard {
    background: #1a1e22;
    border: 1px solid #283039;
    border-radius: 10px;
}

QFrame#DialogCard {
    background: #1a1e22;
    border: 1px solid #283039;
    border-radius: 14px;
}

QLabel#AppTitle {
    font-size: 18px;
    font-weight: 700;
    color: #f4f7fa;
    background: transparent;
}

QLabel#AppSubtitle {
    color: #94a0aa;
}

QLabel#PanelTitle {
    font-size: 13px;
    font-weight: 700;
    color: #f0f3f6;
    background: transparent;
}

QLabel#SectionTitle {
    font-size: 12px;
    font-weight: 700;
    color: #d7dde3;
    background: transparent;
}

QLabel#InlineValue {
    color: #f4f7fa;
    font-size: 13px;
    font-weight: 700;
    font-family: "JetBrains Mono", "Noto Sans Mono", "DejaVu Sans Mono", monospace;
    background: transparent;
    padding: 0;
    min-width: 78px;
}

QLabel#DialogTitle {
    font-size: 17px;
    font-weight: 700;
    color: #f4f7fa;
}

QPushButton {
    background: #20252a;
    border: 1px solid #303840;
    border-radius: 8px;
    padding: 7px 10px;
}

QPushButton:hover {
    background: #262d34;
}

QPushButton:checked {
    background: #263445;
    border: 1px solid #5b8fd9;
    color: #f5f8fb;
}

QPushButton#SidebarNavButton {
    text-align: center;
    padding: 9px 12px;
    margin: 0;
}

QToolButton#DisclosureArrow {
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0;
    min-width: 18px;
    min-height: 18px;
}

QToolButton#DisclosureArrow:hover {
    background: transparent;
    border: none;
}

QToolButton#DisclosureArrow:checked {
    background: transparent;
    border: none;
}

QToolTip {
    background: #1a1f25;
    color: #eef2f6;
    border: 1px solid #42566a;
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 12px;
}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget {
    background: #101214;
    border: 1px solid #2b333a;
    border-radius: 8px;
    padding: 6px 8px;
}

QSlider::groove:horizontal {
    background: #0e1012;
    height: 5px;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background: #7fb2ff;
    width: 16px;
    margin: -6px 0;
    border-radius: 8px;
}

QTextEdit {
    background: #101214;
    border: 1px solid #2b333a;
    border-radius: 8px;
    padding: 8px;
}

QScrollArea#AdjustScrollArea {
    background: transparent;
    border: none;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 6px 0 6px 8px;
}

QScrollBar::handle:vertical {
    background: #32414f;
    border: 1px solid #4d6174;
    border-radius: 5px;
    min-height: 44px;
}

QScrollBar::handle:vertical:hover {
    background: #42566a;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
    border: none;
    height: 0px;
}

QProgressBar {
    background: #101214;
    border: 1px solid #2b333a;
    border-radius: 8px;
    padding: 2px;
    min-height: 24px;
    text-align: center;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5a91db, stop:1 #7fb2ff);
    border-radius: 6px;
}

QLabel#PreviewCanvas {
    background: transparent;
    color: #9ba6b0;
    font-size: 14px;
    border-radius: 10px;
}
"""
