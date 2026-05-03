from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, 
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, 
                             QLineEdit, QSplitter, QTextEdit, QGroupBox, QMessageBox)
from PyQt6.QtCore import Qt
import base64
from linux_admin.ui.workers import SSHWorker

class ServicesTab(QWidget):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        title = QLabel("Systemd Unit & Service Manager")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)
        
        # --- Top Section: Target & Filters ---
        filter_grp = QGroupBox("Target Node & Filters")
        filter_lay = QVBoxLayout(filter_grp)
        
        row1 = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(250)
        self.device_combo.currentIndexChanged.connect(self.fetch_services)
        
        self.btn_fetch = QPushButton("Refresh Units")
        self.btn_fetch.clicked.connect(self.fetch_services)
        
        self.btn_daemon_reload = QPushButton("Global Daemon Reload")
        self.btn_daemon_reload.setObjectName("DangerBtn")
        self.btn_daemon_reload.setToolTip("Reload systemd manager configuration (systemctl daemon-reload)")
        self.btn_daemon_reload.clicked.connect(self.daemon_reload)
        
        row1.addWidget(QLabel("Target Node:"))
        row1.addWidget(self.device_combo)
        row1.addWidget(self.btn_fetch)
        row1.addStretch()
        row1.addWidget(self.btn_daemon_reload)
        
        row2 = QHBoxLayout()
        self.type_combo = QComboBox()
        self.type_combo.addItem("Services (.service)", "service")
        self.type_combo.addItem("Timers (.timer)", "timer")
        self.type_combo.addItem("Sockets (.socket)", "socket")
        self.type_combo.addItem("Mounts (.mount)", "mount")
        self.type_combo.addItem("Paths / Triggers (.path)", "path")
        self.type_combo.addItem("All Units", "all")
        self.type_combo.currentIndexChanged.connect(self.fetch_services)
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Filter by unit name or description...")
        self.search_bar.textChanged.connect(self.filter_table)
        
        row2.addWidget(QLabel("Unit Type:"))
        row2.addWidget(self.type_combo)
        row2.addWidget(QLabel("Search:"))
        row2.addWidget(self.search_bar)
        
        filter_lay.addLayout(row1)
        filter_lay.addLayout(row2)
        layout.addWidget(filter_grp)
        
        # --- Middle Section: Table & Logs Splitter ---
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Unit Name", "Load", "Active", "Sub State", "Description"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        splitter.addWidget(self.table)
        
        self.logs_view = QTextEdit()
        self.logs_view.setReadOnly(True)
        self.logs_view.setStyleSheet("background-color: #11111b; font-family: monospace;")
        self.logs_view.setPlaceholderText("Select a unit and click 'View Logs' to load journalctl data...")
        splitter.addWidget(self.logs_view)
        
        splitter.setSizes([500, 200])
        layout.addWidget(splitter)
        
        # --- Bottom Section: Unit Controls ---
        control_grp = QGroupBox("Selected Unit Controls")
        control_lay = QHBoxLayout(control_grp)
        
        # Action mappings with colors
        actions = [
            ("Start", "start", "#a6e3a1"), 
            ("Stop", "stop", "#f38ba8"), 
            ("Restart", "restart", "#fab387"),
            ("Reload", "reload", ""),
            ("Enable", "enable", "#a6e3a1"), 
            ("Disable", "disable", "#f38ba8"),
            ("Mask", "mask", "#bac2de"),
            ("Unmask", "unmask", "")
        ]
        
        for label, cmd_val, color in actions:
            btn = QPushButton(label)
            if color:
                btn.setStyleSheet(f"color: {color};")
            btn.clicked.connect(lambda checked, c=cmd_val: self.manage_service(c))
            control_lay.addWidget(btn)
            
        control_lay.addStretch()
        
        self.btn_logs = QPushButton("View Logs")
        self.btn_logs.setObjectName("PrimaryBtn")
        self.btn_logs.clicked.connect(self.view_logs)
        control_lay.addWidget(self.btn_logs)
        
        layout.addWidget(control_grp)
        
        self.refresh_devices()

    def refresh_devices(self):
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        device_status = getattr(self.db_mgr, 'device_status', {})
        for dev in self.db_mgr.get_devices():
            if device_status.get(dev['id']) == "Reachable":
                self.device_combo.addItem(f"{dev['name']} ({dev['ip']})", dev)
        self.device_combo.blockSignals(False)
        self.fetch_services()

    def fetch_services(self):
        dev = self.device_combo.currentData()
        if not dev: return
        
        unit_type = self.type_combo.currentData()
        type_flag = f"--type={unit_type}" if unit_type != "all" else ""
        
        # --no-legend removes the footer ("XXX loaded units listed.") for clean parsing
        # --plain removes tree styling
        cmd = f"systemctl list-units {type_flag} --all --no-pager --plain --no-legend"
        
        self.worker = SSHWorker(dev, cmd, self.sec_mgr)
        self.worker.finished.connect(self.populate_table)
        self.worker.start()

    def populate_table(self, result):
        if result['code'] != 0: 
            QMessageBox.critical(self, "Error", f"Failed to list systemd units:\n{result['stderr']}")
            return
            
        lines = result['stdout'].strip().split('\n')
        self.table.setRowCount(0)
        
        for i, line in enumerate(lines):
            if not line.strip(): continue
            
            # systemctl outputs: UNIT LOAD ACTIVE SUB DESCRIPTION
            # We split by max 4 spaces to keep the entire description intact in the 5th element
            parts = line.split(None, 4)
            if len(parts) >= 4:
                self.table.insertRow(i)
                self.table.setItem(i, 0, QTableWidgetItem(parts[0]))
                
                # Load State
                load_item = QTableWidgetItem(parts[1])
                if parts[1] == "not-found" or parts[1] == "error":
                    load_item.setForeground(Qt.GlobalColor.red)
                self.table.setItem(i, 1, load_item)
                
                # Active State
                active_item = QTableWidgetItem(parts[2])
                if parts[2] == "active": 
                    active_item.setForeground(Qt.GlobalColor.green)
                elif parts[2] == "failed": 
                    active_item.setForeground(Qt.GlobalColor.red)
                elif parts[2] in ["inactive", "dead"]:
                    active_item.setForeground(Qt.GlobalColor.gray)
                self.table.setItem(i, 2, active_item)
                
                # Sub State
                self.table.setItem(i, 3, QTableWidgetItem(parts[3]))
                
                # Description (if available)
                desc = parts[4] if len(parts) == 5 else ""
                self.table.setItem(i, 4, QTableWidgetItem(desc))

    def filter_table(self, text):
        search_term = text.lower()
        for row in range(self.table.rowCount()):
            unit_name = self.table.item(row, 0).text().lower()
            desc_item = self.table.item(row, 4)
            unit_desc = desc_item.text().lower() if desc_item else ""
            
            if search_term in unit_name or search_term in unit_desc:
                self.table.setRowHidden(row, False)
            else:
                self.table.setRowHidden(row, True)

    def manage_service(self, action):
        dev = self.device_combo.currentData()
        row = self.table.currentRow()
        if not dev or row < 0: 
            QMessageBox.warning(self, "Warning", "Please select a unit from the table first.")
            return
            
        unit_name = self.table.item(row, 0).text()
        
        # Confirm destructive actions
        if action in ["mask", "stop", "disable"]:
            reply = QMessageBox.question(self, f"Confirm {action.capitalize()}", 
                                         f"Are you sure you want to {action} '{unit_name}'?\nThis may affect system stability.",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes: return
            
        self.logs_view.setText(f"Executing: systemctl {action} {unit_name}...")
        cmd = f"systemctl {action} {unit_name}"
        
        self.worker_cmd = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_cmd.finished.connect(self.on_manage_done)
        self.worker_cmd.start()

    def on_manage_done(self, result):
        if result['code'] == 0:
            self.logs_view.setText(f"Action completed successfully.\n{result['stdout']}")
        else:
            self.logs_view.setText(f"Action failed!\n{result['stderr']}")
        self.fetch_services()

    def daemon_reload(self):
        dev = self.device_combo.currentData()
        if not dev: return
        
        reply = QMessageBox.question(self, "Confirm Daemon Reload", 
                                     "Reload systemd manager configuration on the target node?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes: return
        
        self.logs_view.setText("Executing: systemctl daemon-reload...")
        self.worker_reload = SSHWorker(dev, "systemctl daemon-reload", self.sec_mgr, use_sudo=True)
        self.worker_reload.finished.connect(lambda r: self.logs_view.setText("Daemon reload complete.") or self.fetch_services())
        self.worker_reload.start()

    def view_logs(self):
        dev = self.device_combo.currentData()
        row = self.table.currentRow()
        if not dev or row < 0: 
            QMessageBox.warning(self, "Warning", "Please select a unit to view logs.")
            return
            
        unit_name = self.table.item(row, 0).text()
        self.logs_view.setText(f"Fetching journalctl logs for {unit_name}...")
        
        # Fetch last 100 lines for the specific unit
        cmd = f"journalctl -u {unit_name} -n 100 --no-pager"
        
        self.worker_logs = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_logs.finished.connect(lambda r: self.logs_view.setText(r['stdout'] or f"No journalctl logs found for {unit_name}."))
        self.worker_logs.start()
