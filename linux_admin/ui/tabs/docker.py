from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView
from linux_admin.ui.workers import SSHWorker

class DockerTab(QWidget):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        
        layout = QVBoxLayout(self)
        
        header = QHBoxLayout()
        self.device_combo = QComboBox()
        self.btn_fetch = QPushButton("List Containers")
        self.btn_fetch.clicked.connect(self.fetch_docker)
        
        header.addWidget(QLabel("Device:"))
        header.addWidget(self.device_combo)
        header.addWidget(self.btn_fetch)
        layout.addLayout(header)
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Container ID", "Image", "Status", "Names"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        
        actions = QHBoxLayout()
        for action in ["start", "stop", "restart", "rm -f"]:
            btn = QPushButton(action.capitalize())
            btn.clicked.connect(lambda checked, a=action: self.manage_docker(a))
            actions.addWidget(btn)
        layout.addLayout(actions)
        
        self.refresh_devices()

    def refresh_devices(self):
        self.device_combo.clear()
        for dev in self.db_mgr.get_devices():
            self.device_combo.addItem(f"{dev['name']} ({dev['ip']})", dev)

    def fetch_docker(self):
        dev = self.device_combo.currentData()
        if not dev: return
        cmd = 'docker ps -a --format "{{.ID}}|{{.Image}}|{{.Status}}|{{.Names}}"'
        self.worker = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker.finished.connect(self.populate_table)
        self.worker.start()

    def populate_table(self, result):
        if result['code'] != 0: 
            return # Docker not installed or permission issue
        lines = result['stdout'].strip().split('\n')
        self.table.setRowCount(0)
        for i, line in enumerate(lines):
            if not line: continue
            parts = line.split('|')
            if len(parts) >= 4:
                self.table.insertRow(i)
                for col in range(4):
                    self.table.setItem(i, col, QTableWidgetItem(parts[col]))

    def manage_docker(self, action):
        dev = self.device_combo.currentData()
        row = self.table.currentRow()
        if not dev or row < 0: return
        cid = self.table.item(row, 0).text()
        cmd = f"docker {action} {cid}"
        self.worker = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker.finished.connect(lambda r: self.fetch_docker())
        self.worker.start()
