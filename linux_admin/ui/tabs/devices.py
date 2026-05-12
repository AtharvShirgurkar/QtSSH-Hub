from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, 
                             QInputDialog, QMessageBox, QComboBox, QLineEdit, QLabel, QFormLayout, QDialog, QHeaderView,
                             QSplitter, QTextEdit, QFileDialog, QGroupBox, QCheckBox)
from PyQt6.QtCore import pyqtSignal, Qt
import os
import csv
from linux_admin.ui.workers import SSHWorker

class DeviceDialog(QDialog):
    def __init__(self, db_mgr, sec_mgr, device_data=None, parent=None):
        super().__init__(parent)
        self.db_mgr = db_mgr
        self.sec_mgr = sec_mgr
        self.setWindowTitle("Edit Device" if device_data else "Add Device")
        self.resize(500, 450)
        self.layout = QFormLayout(self)
        
        self.name_in = QLineEdit()
        self.ip_in = QLineEdit()
        self.port_in = QLineEdit("22")
        self.user_in = QLineEdit("root")
        
        self.auth_type = QComboBox()
        self.auth_type.addItems(["password", "key"])
        
        self.cred_in = QLineEdit()
        self.cred_in.setEchoMode(QLineEdit.EchoMode.Password)
        
        self.key_in = QTextEdit()
        self.key_in.setPlaceholderText("Paste private SSH key here (e.g. -----BEGIN OPENSSH PRIVATE KEY-----)")
        self.key_in.setVisible(False)
        self.key_in.setMaximumHeight(100)
        
        self._key_content = None 
        
        self.btn_browse = QPushButton("Browse File...")
        self.btn_browse.clicked.connect(self.browse_key_file)
        self.btn_browse.setVisible(False)
        
        cred_layout = QHBoxLayout()
        cred_layout.setContentsMargins(0,0,0,0)
        cred_layout.addWidget(self.cred_in)
        cred_layout.addWidget(self.key_in)
        cred_layout.addWidget(self.btn_browse)
        
        self.auth_type.currentTextChanged.connect(self.on_auth_type_changed)
        
        self.group_combo = QComboBox()
        self.group_combo.addItem("None", None)
        for g in self.db_mgr.get_groups():
            self.group_combo.addItem(g['name'], g['id'])
            
        self.gpu_check = QCheckBox("Node has NVIDIA GPU(s)")
            
        self.layout.addRow("Display Name:", self.name_in)
        self.layout.addRow("IP Address / Host:", self.ip_in)
        self.layout.addRow("SSH Port:", self.port_in)
        self.layout.addRow("Username:", self.user_in)
        self.layout.addRow("Auth Type:", self.auth_type)
        self.layout.addRow("Credential:", cred_layout)
        self.layout.addRow("Group:", self.group_combo)
        self.layout.addRow("", self.gpu_check)
        
        if device_data:
            self.name_in.setText(device_data['name'])
            self.ip_in.setText(device_data['ip'])
            self.port_in.setText(str(device_data['port']))
            self.user_in.setText(device_data['username'])
            self.auth_type.setCurrentText(device_data['auth_type'])
            self.gpu_check.setChecked(bool(device_data.get('has_gpu', 0)))
            
            try:
                decrypted_cred = self.sec_mgr.decrypt(device_data['credential'])
                if device_data['auth_type'] == 'key':
                    self._key_content = decrypted_cred
                    self.key_in.setPlainText("<EXISTING_KEY_LOADED>")
                else:
                    self.cred_in.setText(decrypted_cred)
            except:
                pass
                
            idx = self.group_combo.findData(device_data['group_id'])
            if idx >= 0:
                self.group_combo.setCurrentIndex(idx)
        
        self.on_auth_type_changed(self.auth_type.currentText())
        
        self.btn = QPushButton("Save Details" if device_data else "Add Server")
        self.btn.setObjectName("PrimaryBtn")
        self.btn.clicked.connect(self.accept)
        self.layout.addRow(self.btn)

    def on_auth_type_changed(self, text):
        if text == "key":
            self.btn_browse.setVisible(True)
            self.cred_in.setVisible(False)
            self.key_in.setVisible(True)
        else:
            self.btn_browse.setVisible(False)
            self.cred_in.setVisible(True)
            self.key_in.setVisible(False)
            self.cred_in.setPlaceholderText("Enter SSH Password...")

    def browse_key_file(self):
        start_dir = os.path.expanduser("~/.ssh") if os.path.exists(os.path.expanduser("~/.ssh")) else ""
        file_path, _ = QFileDialog.getOpenFileName(self, "Select SSH Private Key", start_dir, "All Files (*)")
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    self._key_content = f.read()
                self.key_in.setPlainText("<KEY_FILE_LOADED>") 
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to read key file:\n{str(e)}")

    def get_data(self):
        if self.auth_type.currentText() == "key":
            cred = self.key_in.toPlainText()
            if cred in ["<KEY_FILE_LOADED>", "<EXISTING_KEY_LOADED>"]:
                cred = self._key_content
        else:
            cred = self.cred_in.text()
            
        return {
            "name": self.name_in.text(), "ip": self.ip_in.text(), "port": int(self.port_in.text()),
            "username": self.user_in.text(), "auth_type": self.auth_type.currentText(),
            "credential": cred, "group_id": self.group_combo.currentData(),
            "has_gpu": 1 if self.gpu_check.isChecked() else 0
        }

class DevicesTab(QWidget):
    devices_changed = pyqtSignal()

    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        self.current_group_filter = None
        self.active_workers = []
        self.pending_tests = 0
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        title = QLabel("Devices & Server Groups")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)
        
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(self.splitter)
        
        # --- GROUPS WIDGET ---
        groups_group = QGroupBox("Groups Filter")
        groups_layout = QVBoxLayout(groups_group)
        
        g_controls = QHBoxLayout()
        self.btn_add_group = QPushButton("Add Group")
        self.btn_remove_group = QPushButton("Remove")
        g_controls.addWidget(self.btn_add_group)
        g_controls.addWidget(self.btn_remove_group)
        groups_layout.addLayout(g_controls)
        
        self.groups_table = QTableWidget()
        self.groups_table.setColumnCount(2)
        self.groups_table.setHorizontalHeaderLabels(["ID", "Group Name"])
        self.groups_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.groups_table.setColumnWidth(0, 50)
        self.groups_table.verticalHeader().setVisible(False)
        self.groups_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.groups_table.itemSelectionChanged.connect(self.on_group_selected)
        groups_layout.addWidget(self.groups_table)
        
        self.splitter.addWidget(groups_group)
        
        # --- DEVICES WIDGET ---
        devices_group = QGroupBox("Server Inventory")
        devices_layout = QVBoxLayout(devices_group)
        
        d_controls = QHBoxLayout()
        self.btn_add_device = QPushButton("Add Server")
        
        self.btn_bulk_import = QPushButton("Bulk Import CSV")
        
        self.btn_edit_device = QPushButton("Edit")
        self.btn_remove_device = QPushButton("Remove")
        self.btn_remove_device.setObjectName("DangerBtn")
        
        self.status_filter_combo = QComboBox()
        self.status_filter_combo.addItems(["All", "Reachable", "Unreachable", "Unknown"])
        self.status_filter_combo.currentTextChanged.connect(self.load_devices)
        
        self.btn_test_conn = QPushButton("Test Selected")
        self.btn_test_all = QPushButton("Test All Connections") 
        self.btn_test_all.setObjectName("PrimaryBtn")
        
        d_controls.addWidget(self.btn_add_device)
        d_controls.addWidget(self.btn_bulk_import)
        d_controls.addWidget(self.btn_edit_device)
        d_controls.addWidget(self.btn_remove_device)
        d_controls.addStretch()
        d_controls.addWidget(QLabel("Filter Status:"))
        d_controls.addWidget(self.status_filter_combo)
        d_controls.addWidget(self.btn_test_conn)
        d_controls.addWidget(self.btn_test_all)
        devices_layout.addLayout(d_controls)
        
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "IP Address", "User", "Auth", "Group", "GPU", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        devices_layout.addWidget(self.table)
        
        self.splitter.addWidget(devices_group)
        self.splitter.setSizes([350, 850]) 
        
        self.btn_add_group.clicked.connect(self.add_group)
        self.btn_remove_group.clicked.connect(self.remove_group)
        self.btn_add_device.clicked.connect(self.add_device)
        self.btn_bulk_import.clicked.connect(self.bulk_import_csv)
        self.btn_edit_device.clicked.connect(self.edit_device)
        self.btn_remove_device.clicked.connect(self.remove_device)
        self.btn_test_conn.clicked.connect(self.test_connection)
        self.btn_test_all.clicked.connect(self.test_all_connections)
        
        self.load_data()

    def load_data(self):
        self.groups_table.blockSignals(True)
        self.groups_table.setRowCount(0)
        groups = self.db_mgr.get_groups()
        
        self.groups_table.insertRow(0)
        self.groups_table.setItem(0, 0, QTableWidgetItem("-"))
        self.groups_table.setItem(0, 1, QTableWidgetItem("All Servers"))
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
        status_filter = self.status_filter_combo.currentText()
        
        filtered_devices = []
        for dev in devices:
            stat = self.db_mgr.device_status.get(dev['id'], "Unknown")
            if status_filter == "All" or status_filter == stat:
                dev['_status'] = stat
                filtered_devices.append(dev)

        for i, dev in enumerate(filtered_devices):
            self.table.insertRow(i)
            
            id_item = QTableWidgetItem(str(dev['id']))
            id_item.setData(Qt.ItemDataRole.UserRole, dev) 
            
            self.table.setItem(i, 0, id_item)
            self.table.setItem(i, 1, QTableWidgetItem(dev['name']))
            self.table.setItem(i, 2, QTableWidgetItem(dev['ip']))
            self.table.setItem(i, 3, QTableWidgetItem(dev['username']))
            self.table.setItem(i, 4, QTableWidgetItem("Key" if dev['auth_type']=='key' else "Pass"))
            self.table.setItem(i, 5, QTableWidgetItem(str(dev['group'] or 'None')))
            
            gpu_item = QTableWidgetItem("Yes" if dev.get('has_gpu', 0) == 1 else "No")
            if dev.get('has_gpu', 0) == 1: gpu_item.setForeground(Qt.GlobalColor.cyan)
            self.table.setItem(i, 6, gpu_item)
            
            stat_item = QTableWidgetItem(dev['_status'])
            if dev['_status'] == "Reachable":
                stat_item.setForeground(Qt.GlobalColor.green)
            elif dev['_status'] == "Unreachable":
                stat_item.setForeground(Qt.GlobalColor.red)
            else:
                stat_item.setForeground(Qt.GlobalColor.gray)
            
            self.table.setItem(i, 7, stat_item)
            
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
        if row <= 0: return
            
        group_id = self.groups_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        group_name = self.groups_table.item(row, 1).text()
        
        reply = QMessageBox.question(self, "Confirm Delete", f"Remove group '{group_name}'? Devices will NOT be deleted.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.db_mgr.delete_group(group_id)
            self.current_group_filter = None
            self.load_data()

    def add_device(self):
        dlg = DeviceDialog(self.db_mgr, self.sec_mgr, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            enc_cred = self.sec_mgr.encrypt(data['credential'])
            self.db_mgr.add_device(
                data['name'], data['ip'], data['port'], data['username'],
                data['auth_type'], enc_cred, data['group_id'], data['has_gpu']
            )
            self.load_devices()

    def bulk_import_csv(self):
        QMessageBox.information(self, "CSV Format Required",
            "Please ensure your CSV is formatted as follows (no headers needed):\n\n"
            "Name, IP, Port, Username, Auth Type (password/key), Credential, Group Name, Has GPU (0/1)\n\n"
            "Note: Missing groups will automatically be created."
        )
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Devices CSV", "", "CSV Files (*.csv);;All Files (*)")
        if not file_path: return

        success_count = 0
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                groups_map = {g['name']: g['id'] for g in self.db_mgr.get_groups()}

                for row in reader:
                    if not row or len(row) < 6: continue
                    name = row[0].strip()
                    ip = row[1].strip()
                    port = int(row[2].strip() if row[2].strip().isdigit() else 22)
                    username = row[3].strip()
                    auth_type = row[4].strip().lower()
                    credential = row[5].strip()

                    # If auth is 'key' and the string provided is a valid file path, read the file
                    if auth_type == 'key' and os.path.isfile(credential):
                        try:
                            with open(credential, 'r', encoding='utf-8') as key_file:
                                credential = key_file.read()
                        except Exception as e:
                            QMessageBox.warning(self, "Key Import Error", f"Failed to read key file for {name} at {credential}:\n{str(e)}")
                            continue # Skip importing this device if the key file can't be read

                    group_name = row[6].strip() if len(row) > 6 else ""
                    group_id = None
                    if group_name:
                        if group_name not in groups_map:
                            self.db_mgr.add_group(group_name)
                            groups_map = {g['name']: g['id'] for g in self.db_mgr.get_groups()}
                        group_id = groups_map[group_name]

                    has_gpu = int(row[7].strip()) if len(row) > 7 and row[7].strip().isdigit() else 0

                    enc_cred = self.sec_mgr.encrypt(credential)
                    self.db_mgr.add_device(name, ip, port, username, auth_type, enc_cred, group_id, has_gpu)
                    success_count += 1

            self.load_data()
            QMessageBox.information(self, "Success", f"Successfully imported {success_count} devices.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to import CSV:\n{str(e)}")

    def edit_device(self):
        row = self.table.currentRow()
        if row < 0: return
            
        device_data = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        dlg = DeviceDialog(self.db_mgr, self.sec_mgr, device_data, self)
        
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            enc_cred = self.sec_mgr.encrypt(data['credential'])
            self.db_mgr.update_device(
                device_data['id'], data['name'], data['ip'], data['port'], data['username'],
                data['auth_type'], enc_cred, data['group_id'], data['has_gpu']
            )
            self.load_devices()

    def remove_device(self):
        row = self.table.currentRow()
        if row < 0: return
        device_data = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(self, "Confirm Delete", f"Remove device '{device_data['name']}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.db_mgr.delete_device(device_data['id'])
            self.load_devices()

    def test_connection(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Select Device", "Please select a device to test.")
            return
        
        device_data = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        self.btn_test_conn.setEnabled(False)
        self.btn_test_conn.setText("Testing...")
        
        self.test_worker = SSHWorker(device_data, "echo 'Connection Successful!'", self.sec_mgr)
        self.test_worker.finished.connect(self.on_test_finished)
        self.test_worker.error.connect(lambda err_msg, d=device_data: self.on_test_error(err_msg, d))
        self.test_worker.start()

    def on_test_finished(self, result):
        self.btn_test_conn.setEnabled(True)
        self.btn_test_conn.setText("Test Selected")
        dev_id = result['device']['id']
        
        if result['code'] == 0:
            self.db_mgr.device_status[dev_id] = "Reachable"
            QMessageBox.information(self, "Success", f"Successfully connected to {result['device']['name']}!")
        else:
            self.db_mgr.device_status[dev_id] = "Unreachable"
            QMessageBox.warning(self, "Failed", f"Connected, but command failed:\n{result['stderr']}")
        self.load_devices()

    def on_test_error(self, err_msg, dev):
        self.btn_test_conn.setEnabled(True)
        self.btn_test_conn.setText("Test Selected")
        self.db_mgr.device_status[dev['id']] = "Unreachable"
        QMessageBox.critical(self, "Connection Error", f"Failed to connect to {dev['name']}:\n{err_msg}")
        self.load_devices()

    def test_all_connections(self):
        devices = self.db_mgr.get_devices()
        if not devices: return
        
        self.btn_test_all.setEnabled(False)
        self.btn_test_all.setText("Testing All...")
        self.active_workers = []
        self.pending_tests = len(devices)
        
        for dev in devices:
            worker = SSHWorker(dev, "echo 1", self.sec_mgr)
            worker.finished.connect(self.on_test_all_finished)
            worker.error.connect(lambda err_msg, d=dev: self.on_test_all_error(err_msg, d))
            self.active_workers.append(worker)
            worker.start()

    def on_test_all_finished(self, result):
        dev_id = result['device']['id']
        self.db_mgr.device_status[dev_id] = "Reachable" if result['code'] == 0 else "Unreachable"
        self._check_test_all_done()

    def on_test_all_error(self, err_msg, dev):
        self.db_mgr.device_status[dev['id']] = "Unreachable"
        self._check_test_all_done()

    def _check_test_all_done(self):
        self.pending_tests -= 1
        self.load_devices()
        if self.pending_tests <= 0:
            self.btn_test_all.setEnabled(True)
            self.btn_test_all.setText("Test All Connections")
            self.devices_changed.emit()
