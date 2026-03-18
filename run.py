import sys
import os
from PyQt6.QtWidgets import QApplication, QInputDialog, QMessageBox, QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton
from qt_material import apply_stylesheet

from linux_admin.core.security import SecurityManager
from linux_admin.core.database import DatabaseManager
from linux_admin.ui.main_window import MainWindow

class LoginDialog(QDialog):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        self.setWindowTitle("Linux Admin - Secure Login")
        self.setFixedSize(350, 150)
        
        layout = QVBoxLayout(self)
        
        if not self.sec_mgr.is_initialized():
            self.label = QLabel("Welcome! Please set a Master Password to encrypt your data:")
        else:
            self.label = QLabel("Enter your Master Password:")
            
        layout.addWidget(self.label)
        
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.password_input)
        
        self.login_btn = QPushButton("Login / Setup")
        self.login_btn.clicked.connect(self.authenticate)
        layout.addWidget(self.login_btn)
        
    def authenticate(self):
        pwd = self.password_input.text()
        if not pwd:
            QMessageBox.warning(self, "Error", "Password cannot be empty.")
            return
            
        if not self.sec_mgr.is_initialized():
            self.sec_mgr.setup_master_password(pwd)
            self.db_mgr.init_db()
            self.accept()
        else:
            if self.sec_mgr.verify_and_load(pwd):
                self.db_mgr.init_db()
                self.accept()
            else:
                QMessageBox.critical(self, "Error", "Incorrect Master Password.")
                self.password_input.clear()

def main():
    app = QApplication(sys.argv)
    apply_stylesheet(app, theme='dark_teal.xml')
    
    # Ensure app directory exists
    os.makedirs(os.path.expanduser("~/.linux_admin_app"), exist_ok=True)
    
    sec_mgr = SecurityManager()
    db_mgr = DatabaseManager()
    
    login = LoginDialog(sec_mgr, db_mgr)
    if login.exec() == QDialog.DialogCode.Accepted:
        window = MainWindow(sec_mgr, db_mgr)
        window.show()
        sys.exit(app.exec())
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
