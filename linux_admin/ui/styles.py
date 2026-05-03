# Modern Dark Theme (Inspired by Catppuccin Mocha)
APP_STYLE = """
QMainWindow, QDialog {
    background-color: #1e1e2e;
}

QWidget {
    font-family: 'Segoe UI', 'Roboto', 'Helvetica', sans-serif;
    font-size: 10pt;
    color: #cdd6f4;
}

/* Side Navigation Bar */
QListWidget#Sidebar {
    background-color: #181825;
    border: none;
    border-right: 1px solid #313244;
    outline: none;
}
QListWidget#Sidebar::item {
    padding: 15px 20px;
    border-radius: 8px;
    margin: 5px 10px;
    color: #bac2de;
}
QListWidget#Sidebar::item:hover {
    background-color: #313244;
    color: #cdd6f4;
}
QListWidget#Sidebar::item:selected {
    background-color: #89b4fa;
    color: #11111b;
    font-weight: bold;
}

/* Buttons */
QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #45475a;
    border: 1px solid #585b70;
}
QPushButton:pressed {
    background-color: #585b70;
}
QPushButton#PrimaryBtn {
    background-color: #89b4fa;
    color: #11111b;
    border: none;
}
QPushButton#PrimaryBtn:hover {
    background-color: #b4befe;
}
QPushButton#DangerBtn {
    background-color: #f38ba8;
    color: #11111b;
    border: none;
}
QPushButton#DangerBtn:hover {
    background-color: #eba0ac;
}

/* Inputs & Comboboxes */
QLineEdit, QComboBox, QTextEdit {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 6px;
    padding: 8px;
    color: #cdd6f4;
    selection-background-color: #89b4fa;
}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus {
    border: 1px solid #89b4fa;
}

/* Tables */
QTableWidget {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 8px;
    gridline-color: #313244;
    selection-background-color: #313244;
    selection-color: #89b4fa;
}
QHeaderView::section {
    background-color: #1e1e2e;
    color: #bac2de;
    padding: 8px;
    border: none;
    border-bottom: 2px solid #313244;
    font-weight: bold;
}
QTableWidget::item {
    padding: 5px;
    border-bottom: 1px solid #313244;
}

/* Group Boxes (Cards) */
QGroupBox {
    background-color: #1e1e2e;
    border: 1px solid #313244;
    border-radius: 8px;
    margin-top: 1.5em;
    padding-top: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
    color: #89b4fa;
    font-weight: bold;
    left: 10px;
}

/* Tabs inside pages */
QTabWidget::pane {
    border: 1px solid #313244;
    border-radius: 8px;
    background-color: #181825;
}
QTabBar::tab {
    background-color: #1e1e2e;
    color: #bac2de;
    padding: 10px 20px;
    border: 1px solid #313244;
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #181825;
    color: #89b4fa;
    border-top: 2px solid #89b4fa;
}
QTabBar::tab:hover:!selected {
    background-color: #313244;
}
"""
