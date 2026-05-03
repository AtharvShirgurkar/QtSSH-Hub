from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QSplitter, QTextEdit
from PyQt6.QtCore import Qt
from linux_admin.ui.workers import SSHWorker

class ServicesTab(QWidget):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        title = QLabel("Systemd Services Manager")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)
        
        header = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(200)
        self.btn_fetch = QPushButton("Load Services")
        self.btn_fetch.clicked.connect(self.fetch_services)
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Filter services...")
        self.search_bar.textChanged.connect(self.filter_table)
        
        header.addWidget(QLabel("Server:"))
        header.addWidget(self.device_combo)
        header.addWidget(self.btn_fetch)
        header.addStretch()
        header.addWidget(self.search_bar)
        layout.addLayout(header)
        
        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter)
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Service Unit", "Load State", "Active State", "Sub State"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        splitter.addWidget(self.table)
        
        self.logs_view = QTextEdit()
        self.logs_view.setReadOnly(True)
        self.logs_view.setStyleSheet("background-color: #11111b; font-family: monospace;")
        self.logs_view.setPlaceholderText("Service logs will appear here...")
        splitter.addWidget(self.logs_view)
        
        actions = QHBoxLayout()
        for action in ["start", "stop", "restart", "enable", "disable"]:
            btn = QPushButton(f"{action.capitalize()}")
            if action in ["start", "enable"]: btn.setStyleSheet("color: #a6e3a1;")
            if action in ["stop", "disable"]: btn.setStyleSheet("color: #f38ba8;")
            btn.clicked.connect(lambda checked, a=action: self.manage_service(a))
            actions.addWidget(btn)
            
        self.btn_logs = QPushButton("View Logs")
        self.btn_logs.setObjectName("PrimaryBtn")
        self.btn_logs.clicked.connect(self.view_logs)
        actions.addStretch()
        actions.addWidget(self.btn_logs)
        
        layout.addLayout(actions)
        self.refresh_devices()

    def refresh_devices(self):
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for dev in self.db_mgr.get_devices():
            if self.db_mgr.device_status.get(dev['id']) == "Reachable":
                self.device_combo.addItem(f"{dev['name']} ({dev['ip']})", dev)
        self.device_combo.blockSignals(False)

    def fetch_services(self):
        dev = self.device_combo.currentData()
        if not dev: return
        cmd = "systemctl list-units --type=service --all --no-pager --plain | head -n -3"
        self.worker = SSHWorker(dev, cmd, self.sec_mgr)
        self.worker.finished.connect(self.populate_table)
        self.worker.start()

    def populate_table(self, result):
        if result['code'] != 0: return
        lines = result['stdout'].strip().split('\n')[1:] 
        self.table.setRowCount(0)
        for i, line in enumerate(lines):
            parts = line.split()
            if len(parts) >= 4:
                self.table.insertRow(i)
                self.table.setItem(i, 0, QTableWidgetItem(parts[0]))
                self.table.setItem(i, 1, QTableWidgetItem(parts[1]))
                
                active_item = QTableWidgetItem(parts[2])
                if parts[2] == "active": active_item.setForeground(Qt.GlobalColor.green)
                elif parts[2] == "failed": active_item.setForeground(Qt.GlobalColor.red)
                self.table.setItem(i, 2, active_item)
                
                self.table.setItem(i, 3, QTableWidgetItem(parts[3]))

    def filter_table(self, text):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            self.table.setRowHidden(row, text.lower() not in item.text().lower())

    def manage_service(self, action):
        dev = self.device_combo.currentData()
        row = self.table.currentRow()
        if not dev or row < 0: return
        service_name = self.table.item(row, 0).text()
        cmd = f"systemctl {action} {service_name}"
        self.worker_cmd = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_cmd.finished.connect(lambda r: self.fetch_services())
        self.worker_cmd.start()

    def view_logs(self):
        dev = self.device_combo.currentData()
        row = self.table.currentRow()
        if not dev or row < 0: return
        service_name = self.table.item(row, 0).text()
        self.logs_view.setText(f"Fetching logs for {service_name}...")
        
        cmd = f"journalctl -u {service_name} -n 100 --no-pager"
        self.worker_logs = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_logs.finished.connect(lambda r: self.logs_view.setText(r['stdout'] or "No logs found."))
        self.worker_logs.start()
