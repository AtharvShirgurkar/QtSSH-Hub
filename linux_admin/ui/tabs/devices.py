from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, 
                             QInputDialog, QMessageBox, QComboBox, QLineEdit, QLabel, QFormLayout, QDialog, QHeaderView,
                             QSplitter, QTextEdit, QFileDialog)
from PyQt6.QtCore import pyqtSignal, Qt
import os

class DeviceDialog(QDialog):
    def __init__(self, db_mgr, sec_mgr, device_data=None, parent=None):
        super().__init__(parent)
        self.db_mgr = db_mgr
        self.sec_mgr = sec_mgr
        self.setWindowTitle("Edit Device" if device_data else "Add Device")
        self.layout = QFormLayout(self)
        
        self.name_in = QLineEdit()
        self.ip_in = QLineEdit()
        self.port_in = QLineEdit("22")
        self.user_in = QLineEdit("root")
        
        # Strictly restricted to password or key
        self.auth_type = QComboBox()
        self.auth_type.addItems(["password", "key"])
        
        self.cred_in = QLineEdit()
        self.cred_in.setEchoMode(QLineEdit.EchoMode.Password)
        
        self._key_content = None # Store multi-line key securely in memory
        
        # Browse Button for SSH Key
        self.btn_browse = QPushButton("Browse File...")
        self.btn_browse.clicked.connect(self.browse_key_file)
        self.btn_browse.setVisible(False)
        
        # Layout for credential field + browse button
        cred_layout = QHBoxLayout()
        cred_layout.setContentsMargins(0,0,0,0)
        cred_layout.addWidget(self.cred_in)
        cred_layout.addWidget(self.btn_browse)
        
        # Update UI dynamically based on Auth Type
        self.auth_type.currentTextChanged.connect(self.on_auth_type_changed)
        
        # Only loads actual existing groups from Database
        self.group_combo = QComboBox()
        self.group_combo.addItem("None", None)
        for g in self.db_mgr.get_groups():
            self.group_combo.addItem(g['name'], g['id'])
            
        self.layout.addRow("Name:", self.name_in)
        self.layout.addRow("IP Address:", self.ip_in)
        self.layout.addRow("SSH Port:", self.port_in)
        self.layout.addRow("Username:", self.user_in)
        self.layout.addRow("Auth Type:", self.auth_type)
        self.layout.addRow("Password / Key:", cred_layout)
        self.layout.addRow("Group:", self.group_combo)
        
        # If Editing, pre-fill data
        if device_data:
            self.name_in.setText(device_data['name'])
            self.ip_in.setText(device_data['ip'])
            self.port_in.setText(str(device_data['port']))
            self.user_in.setText(device_data['username'])
            self.auth_type.setCurrentText(device_data['auth_type'])
            
            try:
                decrypted_cred = self.sec_mgr.decrypt(device_data['credential'])
                if device_data['auth_type'] == 'key':
                    self._key_content = decrypted_cred
                    self.cred_in.setText("<EXISTING_KEY_LOADED>")
                else:
                    self.cred_in.setText(decrypted_cred)
            except:
                pass
                
            idx = self.group_combo.findData(device_data['group_id'])
            if idx >= 0:
                self.group_combo.setCurrentIndex(idx)
        
        # Ensure correct visibility on launch
        self.on_auth_type_changed(self.auth_type.currentText())
        
        self.btn = QPushButton("Save" if device_data else "Add")
        self.btn.clicked.connect(self.accept)
        self.layout.addRow(self.btn)

    def on_auth_type_changed(self, text):
        if text == "key":
            self.btn_browse.setVisible(True)
            self.cred_in.setPlaceholderText("Use Browse to select your private key...")
        else:
            self.btn_browse.setVisible(False)
            self.cred_in.setPlaceholderText("Enter SSH Password...")

    def browse_key_file(self):
        # Open file browser starting at ~/.ssh if it exists
        start_dir = os.path.expanduser("~/.ssh") if os.path.exists(os.path.expanduser("~/.ssh")) else ""
        file_path, _ = QFileDialog.getOpenFileName(self, "Select SSH Private Key", start_dir, "All Files (*)")
        
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    self._key_content = f.read()
                # Use a placeholder in the UI so QLineEdit doesn't strip newlines from the actual key
                self.cred_in.setText("<KEY_FILE_LOADED>") 
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to read key file:\n{str(e)}")

    def get_data(self):
        cred = self.cred_in.text()
        # If the user used the file browser or left the existing key untouched, use the stored memory string
        if self.auth_type.currentText() == "key" and cred in ["<KEY_FILE_LOADED>", "<EXISTING_KEY_LOADED>"]:
            cred = self._key_content
            
        return {
            "name": self.name_in.text(), "ip": self.ip_in.text(), "port": int(self.port_in.text()),
            "username": self.user_in.text(), "auth_type": self.auth_type.currentText(),
            "credential": cred, "group_id": self.group_combo.currentData()
        }

class BulkAddDialog(QDialog):
    def __init__(self, db_mgr, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bulk Add Devices")
        self.resize(600, 400)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Target Group (Optional):"))
        self.group_combo = QComboBox()
        self.group_combo.addItem("None", None)
        for g in db_mgr.get_groups():
            self.group_combo.addItem(g['name'], g['id'])
        layout.addWidget(self.group_combo)

        instructions = QLabel("Paste CSV data below. One device per line.\nFormat: Name, IP, Port, Username, Auth Type (password/key), Credential")
        layout.addWidget(instructions)
        
        self.text_area = QTextEdit()
        self.text_area.setPlaceholderText("Web Server 1, 192.168.1.10, 22, root, password, mysecretpass\nDB Server, 10.0.0.5, 2222, admin, key, -----BEGIN RSA PRIVATE KEY-----...")
        layout.addWidget(self.text_area)

        btns = QHBoxLayout()
        btn_ok = QPushButton("Import Devices")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_ok)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    def get_data(self):
        return self.text_area.toPlainText(), self.group_combo.currentData()

class DevicesTab(QWidget):
    devices_changed = pyqtSignal()

    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        self.current_group_filter = None
        
        layout = QVBoxLayout(self)
        
        # Visual Splitter for Groups vs Devices
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(self.splitter)
        
        # --- GROUPS WIDGET (Left Side) ---
        groups_widget = QWidget()
        groups_layout = QVBoxLayout(groups_widget)
        groups_layout.setContentsMargins(0, 0, 10, 0)
        
        g_controls = QHBoxLayout()
        self.btn_add_group = QPushButton("Add Group")
        self.btn_remove_group = QPushButton("Remove Group")
        g_controls.addWidget(self.btn_add_group)
        g_controls.addWidget(self.btn_remove_group)
        groups_layout.addLayout(g_controls)
        
        self.groups_table = QTableWidget()
        self.groups_table.setColumnCount(2)
        self.groups_table.setHorizontalHeaderLabels(["ID", "Group Name"])
        self.groups_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.groups_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.groups_table.itemSelectionChanged.connect(self.on_group_selected)
        groups_layout.addWidget(self.groups_table)
        
        self.splitter.addWidget(groups_widget)
        
        # --- DEVICES WIDGET (Right Side) ---
        devices_widget = QWidget()
        devices_layout = QVBoxLayout(devices_widget)
        devices_layout.setContentsMargins(10, 0, 0, 0)
        
        d_controls = QHBoxLayout()
        self.btn_add_device = QPushButton("Add Device")
        self.btn_edit_device = QPushButton("Edit Device")
        self.btn_remove_device = QPushButton("Remove Device")
        self.btn_bulk_add = QPushButton("Bulk Add")
        self.btn_refresh = QPushButton("Refresh All")
        
        d_controls.addWidget(self.btn_add_device)
        d_controls.addWidget(self.btn_edit_device)
        d_controls.addWidget(self.btn_remove_device)
        d_controls.addWidget(self.btn_bulk_add)
        d_controls.addWidget(self.btn_refresh)
        devices_layout.addLayout(d_controls)
        
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "IP", "Username", "Auth Type", "Group"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        devices_layout.addWidget(self.table)
        
        self.splitter.addWidget(devices_widget)
        self.splitter.setSizes([350, 850]) # 30% / 70% width split roughly
        
        # Connect Signals
        self.btn_add_group.clicked.connect(self.add_group)
        self.btn_remove_group.clicked.connect(self.remove_group)
        self.btn_add_device.clicked.connect(self.add_device)
        self.btn_edit_device.clicked.connect(self.edit_device)
        self.btn_remove_device.clicked.connect(self.remove_device)
        self.btn_bulk_add.clicked.connect(self.bulk_add)
        self.btn_refresh.clicked.connect(self.load_data)
        
        self.load_data()

    def load_data(self):
        # Refresh Groups
        self.groups_table.blockSignals(True)
        self.groups_table.setRowCount(0)
        groups = self.db_mgr.get_groups()
        
        # Default top row for "All Devices"
        self.groups_table.insertRow(0)
        self.groups_table.setItem(0, 0, QTableWidgetItem("-"))
        self.groups_table.setItem(0, 1, QTableWidgetItem("View All Devices"))
        self.groups_table.item(0, 0).setData(Qt.ItemDataRole.UserRole, None)
        
        for i, g in enumerate(groups, start=1):
            self.groups_table.insertRow(i)
            id_item = QTableWidgetItem(str(g['id']))
            id_item.setData(Qt.ItemDataRole.UserRole, g['id'])
            self.groups_table.setItem(i, 0, id_item)
            self.groups_table.setItem(i, 1, QTableWidgetItem(g['name']))
            
        self.groups_table.blockSignals(False)
        self.load_devices()

    def load_devices(self):
        self.table.setRowCount(0)
        devices = self.db_mgr.get_devices(self.current_group_filter)
        for i, dev in enumerate(devices):
            self.table.insertRow(i)
            
            id_item = QTableWidgetItem(str(dev['id']))
            id_item.setData(Qt.ItemDataRole.UserRole, dev) 
            
            self.table.setItem(i, 0, id_item)
            self.table.setItem(i, 1, QTableWidgetItem(dev['name']))
            self.table.setItem(i, 2, QTableWidgetItem(dev['ip']))
            self.table.setItem(i, 3, QTableWidgetItem(dev['username']))
            self.table.setItem(i, 4, QTableWidgetItem(dev['auth_type']))
            self.table.setItem(i, 5, QTableWidgetItem(str(dev['group'] or 'None')))
            
        self.devices_changed.emit()

    def on_group_selected(self):
        rows = self.groups_table.selectedItems()
        if rows:
            row = rows[0].row()
            group_id = self.groups_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            self.current_group_filter = group_id
            self.load_devices()

    def add_group(self):
        name, ok = QInputDialog.getText(self, "Add Group", "Group Name:")
        if ok and name:
            self.db_mgr.add_group(name)
            self.load_data()
            
    def remove_group(self):
        row = self.groups_table.currentRow()
        if row <= 0: 
            QMessageBox.warning(self, "Warning", "Please select a valid custom group to remove.")
            return
            
        group_id = self.groups_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        group_name = self.groups_table.item(row, 1).text()
        
        reply = QMessageBox.question(self, "Confirm Delete", f"Remove group '{group_name}'? (Devices inside will NOT be deleted, they will just lose their group assignment).", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.db_mgr.delete_group(group_id)
            self.current_group_filter = None
            self.load_data()

    def add_device(self):
        dlg = DeviceDialog(self.db_mgr, self.sec_mgr, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            if not data['name'] or not data['ip'] or not data['credential']:
                QMessageBox.warning(self, "Error", "Name, IP, and Credential cannot be empty!")
                return
            enc_cred = self.sec_mgr.encrypt(data['credential'])
            self.db_mgr.add_device(
                data['name'], data['ip'], data['port'], data['username'],
                data['auth_type'], enc_cred, data['group_id']
            )
            self.load_devices()

    def edit_device(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Warning", "Please select a device to edit.")
            return
            
        device_data = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        dlg = DeviceDialog(self.db_mgr, self.sec_mgr, device_data, self)
        
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            enc_cred = self.sec_mgr.encrypt(data['credential'])
            self.db_mgr.update_device(
                device_data['id'], data['name'], data['ip'], data['port'], data['username'],
                data['auth_type'], enc_cred, data['group_id']
            )
            self.load_devices()

    def remove_device(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Warning", "Please select a device to remove.")
            return
            
        device_data = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(self, "Confirm Delete", f"Are you sure you want to remove device '{device_data['name']}' ({device_data['ip']})?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self.db_mgr.delete_device(device_data['id'])
            self.load_devices()

    def bulk_add(self):
        dlg = BulkAddDialog(self.db_mgr, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            text_data, target_group_id = dlg.get_data()
            lines = text_data.strip().split('\n')
            
            added_count = 0
            for line in lines:
                if not line.strip(): continue
                parts = [p.strip() for p in line.split(',')]
                
                if len(parts) >= 6:
                    name, ip, port, username, auth_type, credential = parts[0], parts[1], parts[2], parts[3], parts[4], ','.join(parts[5:])
                    
                    try: port = int(port)
                    except: port = 22
                    
                    if auth_type not in ["password", "key"]: auth_type = "password"
                    
                    enc_cred = self.sec_mgr.encrypt(credential)
                    self.db_mgr.add_device(name, ip, port, username, auth_type, enc_cred, target_group_id)
                    added_count += 1
            
            if added_count > 0:
                QMessageBox.information(self, "Success", f"Successfully imported {added_count} devices in bulk!")
            else:
                QMessageBox.warning(self, "Warning", "No valid devices found. Check the CSV format.")
                
            self.load_devices()
