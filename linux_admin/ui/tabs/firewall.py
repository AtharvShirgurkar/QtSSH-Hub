from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QPushButton, QTextEdit, QInputDialog, QMessageBox, QGroupBox, QSplitter
from PyQt6.QtCore import Qt
from linux_admin.ui.workers import SSHWorker

class FirewallTab(QWidget):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        self.detected_fw = None
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        title = QLabel("Firewall & Network Security")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)
        
        header = QHBoxLayout()
        self.device_combo = QComboBox()
        self.btn_detect = QPushButton("Scan Firewall")
        self.btn_detect.clicked.connect(self.detect_firewall)
        
        self.status_lbl = QLabel("FW: Unknown")
        self.status_lbl.setStyleSheet("font-weight: bold; color: #f9e2af;")
        header.addWidget(QLabel("Target:"))
        header.addWidget(self.device_combo)
        header.addWidget(self.btn_detect)
        header.addWidget(self.status_lbl)
        header.addStretch()
        layout.addLayout(header)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # Left Panel: Rules
        rules_grp = QGroupBox("Firewall Rules")
        rules_lay = QVBoxLayout(rules_grp)
        self.output_log = QTextEdit()
        self.output_log.setReadOnly(True)
        self.output_log.setStyleSheet("background-color: #11111b; font-family: monospace;")
        rules_lay.addWidget(self.output_log)
        
        actions = QHBoxLayout()
        self.btn_enable = QPushButton("Enable")
        self.btn_disable = QPushButton("Disable")
        self.btn_add_rule = QPushButton("Allow Port (e.g. 80/tcp)")
        self.btn_enable.clicked.connect(lambda: self.run_fw_cmd("enable"))
        self.btn_disable.clicked.connect(lambda: self.run_fw_cmd("disable"))
        self.btn_add_rule.clicked.connect(self.add_rule)
        actions.addWidget(self.btn_enable)
        actions.addWidget(self.btn_disable)
        actions.addWidget(self.btn_add_rule)
        rules_lay.addLayout(actions)
        splitter.addWidget(rules_grp)
        
        # Right Panel: Active Connections View
        conn_grp = QGroupBox("Live Active Connections (ss)")
        conn_lay = QVBoxLayout(conn_grp)
        self.conn_log = QTextEdit()
        self.conn_log.setReadOnly(True)
        self.conn_log.setStyleSheet("background-color: #11111b; font-family: monospace;")
        conn_lay.addWidget(self.conn_log)
        self.btn_refresh_conn = QPushButton("Refresh Connections")
        self.btn_refresh_conn.clicked.connect(self.fetch_connections)
        conn_lay.addWidget(self.btn_refresh_conn)
        splitter.addWidget(conn_grp)
        
        self.refresh_devices()

    def refresh_devices(self):
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for dev in self.db_mgr.get_devices():
            if self.db_mgr.device_status.get(dev['id']) == "Reachable":
                self.device_combo.addItem(f"{dev['name']} ({dev['ip']})", dev)
        self.device_combo.blockSignals(False)

    def detect_firewall(self):
        dev = self.device_combo.currentData()
        if not dev: return
        cmd = "if systemctl is-active --quiet ufw; then echo ufw; elif systemctl is-active --quiet firewalld; then echo firewalld; else echo none; fi"
        self.worker = SSHWorker(dev, cmd, self.sec_mgr)
        self.worker.finished.connect(self.on_detected)
        self.worker.start()
        self.fetch_connections()

    def on_detected(self, result):
        fw = result['stdout'].strip()
        self.detected_fw = fw
        self.status_lbl.setText(f"FW Engine: {fw.upper()}")
        
        if fw == "ufw":
            self.run_raw_cmd("ufw status numbered")
        elif fw == "firewalld":
            self.run_raw_cmd("firewall-cmd --list-all")
        else:
            self.output_log.setText("No supported firewall actively running.")

    def run_raw_cmd(self, cmd):
        dev = self.device_combo.currentData()
        self.worker_cmd = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_cmd.finished.connect(lambda r: self.output_log.setText(r['stdout'] + "\n" + r['stderr']))
        self.worker_cmd.start()

    def fetch_connections(self):
        dev = self.device_combo.currentData()
        if not dev: return
        self.conn_log.setText("Scanning established connections...")
        cmd = "ss -tunap | grep ESTAB"
        self.w_conn = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.w_conn.finished.connect(lambda r: self.conn_log.setText(r['stdout'] or "No established connections found."))
        self.w_conn.start()

    def run_fw_cmd(self, action):
        if not self.detected_fw or self.detected_fw == 'none': return
        cmd = ""
        if self.detected_fw == 'ufw':
            if action == 'enable': cmd = "ufw --force enable"
            elif action == 'disable': cmd = "ufw disable"
        elif self.detected_fw == 'firewalld':
            if action == 'enable': cmd = "systemctl start firewalld && systemctl enable firewalld"
            elif action == 'disable': cmd = "systemctl stop firewalld && systemctl disable firewalld"
        self.run_raw_cmd(cmd)

    def add_rule(self):
        if not self.detected_fw or self.detected_fw == 'none': return
        port, ok = QInputDialog.getText(self, "Add Rule", "Enter port/proto (e.g. 8080/tcp):")
        if ok and port:
            if self.detected_fw == 'ufw': cmd = f"ufw allow {port}"
            elif self.detected_fw == 'firewalld': cmd = f"firewall-cmd --permanent --add-port={port} && firewall-cmd --reload"
            self.run_raw_cmd(cmd)
