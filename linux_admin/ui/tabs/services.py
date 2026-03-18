from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView
from linux_admin.ui.workers import SSHWorker

class ServicesTab(QWidget):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        
        layout = QVBoxLayout(self)
        
        header = QHBoxLayout()
        self.device_combo = QComboBox()
        self.btn_fetch = QPushButton("List Services")
        self.btn_fetch.clicked.connect(self.fetch_services)
        header.addWidget(QLabel("Device:"))
        header.addWidget(self.device_combo)
        header.addWidget(self.btn_fetch)
        layout.addLayout(header)
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Unit", "Load", "Active", "Sub"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        
        actions = QHBoxLayout()
        for action in ["start", "stop", "restart", "enable", "disable", "mask", "unmask"]:
            btn = QPushButton(action.capitalize())
            btn.clicked.connect(lambda checked, a=action: self.manage_service(a))
            actions.addWidget(btn)
        layout.addLayout(actions)
        
        self.refresh_devices()

    def refresh_devices(self):
        self.device_combo.clear()
        for dev in self.db_mgr.get_devices():
            self.device_combo.addItem(f"{dev['name']} ({dev['ip']})", dev)

    def fetch_services(self):
        dev = self.device_combo.currentData()
        if not dev: return
        cmd = "systemctl list-units --type=service --all --no-pager --plain | head -n -3"
        self.worker = SSHWorker(dev, cmd, self.sec_mgr)
        self.worker.finished.connect(self.populate_table)
        self.worker.start()

    def populate_table(self, result):
        if result['code'] != 0: return
        lines = result['stdout'].strip().split('\n')[1:] # skip header
        self.table.setRowCount(0)
        for i, line in enumerate(lines):
            parts = line.split()
            if len(parts) >= 4:
                self.table.insertRow(i)
                self.table.setItem(i, 0, QTableWidgetItem(parts[0]))
                self.table.setItem(i, 1, QTableWidgetItem(parts[1]))
                self.table.setItem(i, 2, QTableWidgetItem(parts[2]))
                self.table.setItem(i, 3, QTableWidgetItem(parts[3]))

    def manage_service(self, action):
        dev = self.device_combo.currentData()
        row = self.table.currentRow()
        if not dev or row < 0: return
        service_name = self.table.item(row, 0).text()
        cmd = f"systemctl {action} {service_name}"
        self.worker = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker.finished.connect(lambda r: self.fetch_services()) # Refresh on done
        self.worker.start()
