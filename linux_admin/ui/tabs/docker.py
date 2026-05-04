from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget, QTextEdit
from linux_admin.ui.workers import SSHWorker

class DockerTab(QWidget):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        title = QLabel("Docker Container Engine")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #89b4fa;")
        layout.addWidget(title)
        
        header = QHBoxLayout()
        self.device_combo = QComboBox()
        self.btn_fetch = QPushButton("Refresh Engine")
        self.btn_fetch.clicked.connect(self.fetch_all)
        
        header.addWidget(QLabel("Target Host:"))
        header.addWidget(self.device_combo)
        header.addWidget(self.btn_fetch)
        header.addStretch()
        layout.addLayout(header)
        
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # --- Containers Tab ---
        c_tab = QWidget()
        c_lay = QVBoxLayout(c_tab)
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID", "Image", "Status", "Name"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        c_lay.addWidget(self.table)
        
        actions = QHBoxLayout()
        for action in ["start", "stop", "restart", "rm -f"]:
            btn = QPushButton(f"{action.capitalize().replace(' -f', '')}")
            btn.clicked.connect(lambda checked, a=action: self.manage_docker(a))
            actions.addWidget(btn)
            
        self.btn_logs = QPushButton("View Logs") 
        self.btn_logs.setObjectName("PrimaryBtn")
        self.btn_logs.clicked.connect(self.view_container_logs)
        actions.addStretch()
        actions.addWidget(self.btn_logs)
        c_lay.addLayout(actions)
        self.tabs.addTab(c_tab, "Containers")
        
        # --- Images Tab ---
        i_tab = QWidget()
        i_lay = QVBoxLayout(i_tab)
        self.img_table = QTableWidget()
        self.img_table.setColumnCount(4)
        self.img_table.setHorizontalHeaderLabels(["Repository", "Tag", "Image ID", "Size"])
        self.img_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.img_table.verticalHeader().setVisible(False)
        i_lay.addWidget(self.img_table)
        self.tabs.addTab(i_tab, "Local Images")
        
        # Log Output
        self.log_out = QTextEdit()
        self.log_out.setReadOnly(True)
        self.log_out.setMaximumHeight(150)
        self.log_out.setStyleSheet("background-color: #11111b; font-family: monospace;")
        layout.addWidget(QLabel("Output / Logs:"))
        layout.addWidget(self.log_out)
        
        self.refresh_devices()

    def refresh_devices(self):
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for dev in self.db_mgr.get_devices():
            if self.db_mgr.device_status.get(dev['id']) == "Reachable":
                self.device_combo.addItem(f"{dev['name']} ({dev['ip']})", dev)
        self.device_combo.blockSignals(False)

    def fetch_all(self):
        self.fetch_docker()
        self.fetch_images()

    def fetch_docker(self):
        dev = self.device_combo.currentData()
        if not dev: return
        cmd = 'docker ps -a --format "{{.ID}}|{{.Image}}|{{.Status}}|{{.Names}}"'
        # --- UPDATED THREAD HANDLING ---
        if not hasattr(self, 'active_workers'): self.active_workers = []
        
        # 1. Safely sweep old, dead threads from previous runs
        self.active_workers = [w for w in self.active_workers if w.isRunning()]
        
        # 2. Create and connect the new worker
        worker = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        worker.finished.connect(self.populate_table)
        
        # 3. Add to list and start
        self.active_workers.append(worker)
        worker.start()

    def populate_table(self, result):
        if result['code'] != 0: return
        lines = result['stdout'].strip().split('\n')
        self.table.setRowCount(0)
        for i, line in enumerate(lines):
            if not line: continue
            parts = line.split('|')
            if len(parts) >= 4:
                self.table.insertRow(i)
                for col in range(4):
                    self.table.setItem(i, col, QTableWidgetItem(parts[col]))

    def fetch_images(self):
        dev = self.device_combo.currentData()
        if not dev: return
        cmd = 'docker images --format "{{.Repository}}|{{.Tag}}|{{.ID}}|{{.Size}}"'
        self.w_img = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.w_img.finished.connect(self.populate_images)
        self.w_img.start()
        
    def populate_images(self, result):
        if result['code'] != 0: return
        lines = result['stdout'].strip().split('\n')
        self.img_table.setRowCount(0)
        for i, line in enumerate(lines):
            if not line: continue
            parts = line.split('|')
            if len(parts) >= 4:
                self.img_table.insertRow(i)
                for col in range(4): self.img_table.setItem(i, col, QTableWidgetItem(parts[col]))

    def view_container_logs(self):
        dev = self.device_combo.currentData()
        row = self.table.currentRow()
        if not dev or row < 0: return
        cid = self.table.item(row, 0).text()
        self.log_out.setText(f"Fetching tail logs for {cid}...")
        cmd = f"docker logs --tail 50 {cid}"
        self.w_log = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.w_log.finished.connect(lambda r: self.log_out.setText(r['stdout'] + r['stderr']))
        self.w_log.start()

    def manage_docker(self, action):
        dev = self.device_combo.currentData()
        row = self.table.currentRow()
        if not dev or row < 0: return
        cid = self.table.item(row, 0).text()
        cmd = f"docker {action} {cid}"
        self.log_out.setText(f"Executing: {cmd}")
        self.worker_cmd = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_cmd.finished.connect(lambda r: self.fetch_all())
        self.worker_cmd.start()
