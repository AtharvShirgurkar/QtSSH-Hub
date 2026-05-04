from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, 
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, 
                             QTabWidget, QTextEdit, QInputDialog, QMessageBox, QSplitter)
from PyQt6.QtCore import Qt
import base64
from linux_admin.ui.workers import SSHWorker

class DockerTab(QWidget):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        self.active_workers = []
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        title = QLabel("Docker Engine Management")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #89b4fa;")
        layout.addWidget(title)
        
        # --- Header Controls ---
        header = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(250)
        
        self.btn_fetch = QPushButton("Refresh All")
        self.btn_fetch.clicked.connect(self.fetch_all)
        
        self.btn_prune = QPushButton("System Prune")
        self.btn_prune.setObjectName("DangerBtn")
        self.btn_prune.setToolTip("Remove unused data (containers, networks, images)")
        self.btn_prune.clicked.connect(self.system_prune)
        
        header.addWidget(QLabel("Target Host:"))
        header.addWidget(self.device_combo)
        header.addWidget(self.btn_fetch)
        header.addStretch()
        header.addWidget(self.btn_prune)
        layout.addLayout(header)
        
        # --- Main Layout Splitter ---
        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter)
        
        self.tabs = QTabWidget()
        splitter.addWidget(self.tabs)
        
        # ==============================================================
        # TAB 1: CONTAINERS
        # ==============================================================
        c_tab = QWidget()
        c_lay = QVBoxLayout(c_tab)
        self.con_table = QTableWidget()
        self.con_table.setColumnCount(5)
        self.con_table.setHorizontalHeaderLabels(["ID", "Name", "Image", "Status", "Ports"])
        self.con_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.con_table.verticalHeader().setVisible(False)
        self.con_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        c_lay.addWidget(self.con_table)
        
        c_actions = QHBoxLayout()
        for act, lbl in [("start", "Start"), ("stop", "Stop"), ("restart", "Restart"), 
                         ("pause", "Pause"), ("unpause", "Unpause"), ("rm -f", "Delete")]:
            btn = QPushButton(lbl)
            btn.clicked.connect(lambda checked, a=act: self.manage_docker("container", a))
            if act == "rm -f": btn.setObjectName("DangerBtn")
            c_actions.addWidget(btn)
            
        c_actions.addStretch()
        
        self.btn_exec = QPushButton("Exec Cmd")
        self.btn_exec.setToolTip("Run a command inside the selected container")
        self.btn_exec.clicked.connect(self.exec_container)
        
        self.btn_stats = QPushButton("Stats")
        self.btn_stats.clicked.connect(self.view_container_stats)
        
        self.btn_logs = QPushButton("View Logs")
        self.btn_logs.setObjectName("PrimaryBtn")
        self.btn_logs.clicked.connect(self.view_container_logs)
        
        c_actions.addWidget(self.btn_exec)
        c_actions.addWidget(self.btn_stats)
        c_actions.addWidget(self.btn_logs)
        c_lay.addLayout(c_actions)
        self.tabs.addTab(c_tab, "Containers")
        
        # ==============================================================
        # TAB 2: IMAGES
        # ==============================================================
        i_tab = QWidget()
        i_lay = QVBoxLayout(i_tab)
        self.img_table = QTableWidget()
        self.img_table.setColumnCount(4)
        self.img_table.setHorizontalHeaderLabels(["Image ID", "Repository", "Tag", "Size"])
        self.img_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.img_table.verticalHeader().setVisible(False)
        self.img_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        i_lay.addWidget(self.img_table)
        
        i_actions = QHBoxLayout()
        self.btn_pull = QPushButton("Pull Image")
        self.btn_pull.setObjectName("PrimaryBtn")
        self.btn_pull.clicked.connect(self.pull_image)
        
        self.btn_rm_img = QPushButton("Delete Selected")
        self.btn_rm_img.setObjectName("DangerBtn")
        self.btn_rm_img.clicked.connect(lambda: self.manage_docker("image", "rm -f"))
        
        i_actions.addWidget(self.btn_pull)
        i_actions.addWidget(self.btn_rm_img)
        i_actions.addStretch()
        i_lay.addLayout(i_actions)
        self.tabs.addTab(i_tab, "Images")
        
        # ==============================================================
        # TAB 3: VOLUMES
        # ==============================================================
        v_tab = QWidget()
        v_lay = QVBoxLayout(v_tab)
        self.vol_table = QTableWidget()
        self.vol_table.setColumnCount(2)
        self.vol_table.setHorizontalHeaderLabels(["Volume Name", "Driver"])
        self.vol_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.vol_table.verticalHeader().setVisible(False)
        self.vol_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        v_lay.addWidget(self.vol_table)
        
        v_actions = QHBoxLayout()
        self.btn_rm_vol = QPushButton("Delete Selected Volume")
        self.btn_rm_vol.setObjectName("DangerBtn")
        self.btn_rm_vol.clicked.connect(lambda: self.manage_docker("volume", "rm -f"))
        v_actions.addWidget(self.btn_rm_vol)
        v_actions.addStretch()
        v_lay.addLayout(v_actions)
        self.tabs.addTab(v_tab, "Volumes")
        
        # ==============================================================
        # TAB 4: NETWORKS
        # ==============================================================
        n_tab = QWidget()
        n_lay = QVBoxLayout(n_tab)
        self.net_table = QTableWidget()
        self.net_table.setColumnCount(4)
        self.net_table.setHorizontalHeaderLabels(["Network ID", "Name", "Driver", "Scope"])
        self.net_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.net_table.verticalHeader().setVisible(False)
        self.net_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        n_lay.addWidget(self.net_table)
        
        n_actions = QHBoxLayout()
        self.btn_rm_net = QPushButton("Delete Selected Network")
        self.btn_rm_net.setObjectName("DangerBtn")
        self.btn_rm_net.clicked.connect(lambda: self.manage_docker("network", "rm"))
        n_actions.addWidget(self.btn_rm_net)
        n_actions.addStretch()
        n_lay.addLayout(n_actions)
        self.tabs.addTab(n_tab, "Networks")
        
        # --- Bottom Log Output ---
        self.log_out = QTextEdit()
        self.log_out.setReadOnly(True)
        self.log_out.setStyleSheet("background-color: #11111b; font-family: monospace;")
        splitter.addWidget(self.log_out)
        
        splitter.setSizes([600, 200])
        self.refresh_devices()

    def refresh_devices(self):
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for dev in self.db_mgr.get_devices():
            if self.db_mgr.device_status.get(dev['id']) == "Reachable":
                self.device_combo.addItem(f"{dev['name']} ({dev['ip']})", dev)
        self.device_combo.blockSignals(False)

    def log(self, text):
        self.log_out.setText(text)

    # --- Unified Data Fetcher ---
    def fetch_all(self):
        dev = self.device_combo.currentData()
        if not dev: return
        self.log("Refreshing Docker Engine data... please wait.")
        
        # Collect Containers, Images, Volumes, and Networks safely in one go
        script = """
        echo "===CON==="
        docker ps -a --format "{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}" || true
        echo "===IMG==="
        docker images --format "{{.ID}}|{{.Repository}}|{{.Tag}}|{{.Size}}" || true
        echo "===VOL==="
        docker volume ls --format "{{.Name}}|{{.Driver}}" || true
        echo "===NET==="
        docker network ls --format "{{.ID}}|{{.Name}}|{{.Driver}}|{{.Scope}}" || true
        """
        
        b64_script = base64.b64encode(script.encode('utf-8')).decode('utf-8')
        cmd = f"bash -c 'echo {b64_script} | base64 -d | bash'"
        
        worker = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        worker.finished.connect(self.populate_all)
        self.active_workers.append(worker)
        worker.start()

    def populate_all(self, result):
        if result['code'] != 0:
            self.log(f"Failed to fetch docker data. Is docker installed and running?\nError: {result['stderr']}")
            return
            
        stdout = result['stdout']
        try:
            parts = stdout.split("===")
            data = {}
            for i in range(1, len(parts), 2):
                if i+1 < len(parts):
                    key = parts[i].strip()
                    data[key] = parts[i+1].strip()
            
            # Populate Containers
            c_lines = data.get("CON", "").split('\n')
            self.con_table.setRowCount(0)
            for i, line in enumerate([l for l in c_lines if l.strip()]):
                row_data = line.split('|')
                row_data += [''] * (5 - len(row_data)) # Pad missing columns if empty
                self.con_table.insertRow(i)
                for col in range(5): self.con_table.setItem(i, col, QTableWidgetItem(row_data[col]))
            
            # Populate Images
            i_lines = data.get("IMG", "").split('\n')
            self.img_table.setRowCount(0)
            for i, line in enumerate([l for l in i_lines if l.strip()]):
                row_data = line.split('|')
                row_data += [''] * (4 - len(row_data))
                self.img_table.insertRow(i)
                for col in range(4): self.img_table.setItem(i, col, QTableWidgetItem(row_data[col]))
                    
            # Populate Volumes
            v_lines = data.get("VOL", "").split('\n')
            self.vol_table.setRowCount(0)
            for i, line in enumerate([l for l in v_lines if l.strip()]):
                row_data = line.split('|')
                row_data += [''] * (2 - len(row_data))
                self.vol_table.insertRow(i)
                for col in range(2): self.vol_table.setItem(i, col, QTableWidgetItem(row_data[col]))
                    
            # Populate Networks
            n_lines = data.get("NET", "").split('\n')
            self.net_table.setRowCount(0)
            for i, line in enumerate([l for l in n_lines if l.strip()]):
                row_data = line.split('|')
                row_data += [''] * (4 - len(row_data))
                self.net_table.insertRow(i)
                for col in range(4): self.net_table.setItem(i, col, QTableWidgetItem(row_data[col]))
                    
            self.log("Docker data refreshed successfully.")
        except Exception as e:
            self.log(f"Error parsing data: {str(e)}")

    # --- Actions ---
    def manage_docker(self, target_type, action):
        dev = self.device_combo.currentData()
        if not dev: return
        
        target_id = None
        if target_type == "container":
            row = self.con_table.currentRow()
            if row >= 0: target_id = self.con_table.item(row, 0).text()
        elif target_type == "image":
            row = self.img_table.currentRow()
            if row >= 0: target_id = self.img_table.item(row, 0).text()
        elif target_type == "volume":
            row = self.vol_table.currentRow()
            if row >= 0: target_id = self.vol_table.item(row, 0).text()
        elif target_type == "network":
            row = self.net_table.currentRow()
            if row >= 0: target_id = self.net_table.item(row, 0).text()
            
        if not target_id:
            QMessageBox.warning(self, "No Selection", f"Please select a {target_type} first.")
            return
            
        cmd = f"docker {target_type} {action} {target_id}"
        self.log(f"Executing: {cmd}...")
        
        worker = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        worker.finished.connect(lambda r: self.log(r['stdout'] + r['stderr']) or self.fetch_all())
        self.active_workers.append(worker)
        worker.start()

    def view_container_logs(self):
        dev = self.device_combo.currentData()
        row = self.con_table.currentRow()
        if not dev or row < 0: return
        cid = self.con_table.item(row, 0).text()
        
        self.log(f"Fetching tail logs for container {cid}...")
        cmd = f"docker logs --tail 100 {cid}"
        worker = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        worker.finished.connect(lambda r: self.log(r['stdout'] + "\n" + r['stderr']))
        self.active_workers.append(worker)
        worker.start()

    def view_container_stats(self):
        dev = self.device_combo.currentData()
        row = self.con_table.currentRow()
        if not dev or row < 0: return
        cid = self.con_table.item(row, 0).text()
        
        self.log(f"Fetching instant stats for {cid}...")
        cmd = f"docker stats --no-stream {cid}"
        worker = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        worker.finished.connect(lambda r: self.log(r['stdout'] + r['stderr']))
        self.active_workers.append(worker)
        worker.start()

    def exec_container(self):
        dev = self.device_combo.currentData()
        row = self.con_table.currentRow()
        if not dev or row < 0: return
        
        cid = self.con_table.item(row, 0).text()
        cname = self.con_table.item(row, 1).text()
        
        cmd_text, ok = QInputDialog.getText(self, "Execute Command", f"Run command inside '{cname}':\n(e.g., ls -la, ps aux)")
        if ok and cmd_text:
            cmd = f"docker exec {cid} {cmd_text}"
            self.log(f"Running '{cmd_text}' in {cname}...")
            worker = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
            worker.finished.connect(lambda r: self.log(f"Output of '{cmd_text}':\n\n" + r['stdout'] + r['stderr']))
            self.active_workers.append(worker)
            worker.start()

    def pull_image(self):
        dev = self.device_combo.currentData()
        if not dev: return
        
        img_name, ok = QInputDialog.getText(self, "Pull Docker Image", "Enter image name (e.g., ubuntu:latest, nginx):")
        if ok and img_name:
            cmd = f"docker pull {img_name}"
            self.log(f"Pulling image {img_name}... This might take a while.")
            worker = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
            worker.finished.connect(lambda r: self.log(r['stdout'] + r['stderr']) or self.fetch_all())
            self.active_workers.append(worker)
            worker.start()

    def system_prune(self):
        dev = self.device_combo.currentData()
        if not dev: return
        
        reply = QMessageBox.question(self, "Confirm System Prune", 
                                     "This will remove ALL stopped containers, unused networks, dangling images, and build cache. Continue?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                                     
        if reply == QMessageBox.StandardButton.Yes:
            self.log("Running Docker System Prune...")
            cmd = "docker system prune -af"
            worker = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
            worker.finished.connect(lambda r: self.log(r['stdout'] + r['stderr']) or self.fetch_all())
            self.active_workers.append(worker)
            worker.start()
