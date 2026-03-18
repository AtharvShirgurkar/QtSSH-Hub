from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QPushButton, QTextEdit, QInputDialog, QMessageBox
from linux_admin.ui.workers import SSHWorker

class FirewallTab(QWidget):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        self.detected_fw = None
        
        layout = QVBoxLayout(self)
        
        header = QHBoxLayout()
        self.device_combo = QComboBox()
        self.btn_detect = QPushButton("Detect & List Rules")
        self.btn_detect.clicked.connect(self.detect_firewall)
        
        self.status_lbl = QLabel("Firewall: Unknown")
        header.addWidget(QLabel("Device:"))
        header.addWidget(self.device_combo)
        header.addWidget(self.btn_detect)
        header.addWidget(self.status_lbl)
        layout.addLayout(header)
        
        self.output_log = QTextEdit()
        self.output_log.setReadOnly(True)
        layout.addWidget(self.output_log)
        
        actions = QHBoxLayout()
        self.btn_enable = QPushButton("Enable")
        self.btn_disable = QPushButton("Disable")
        self.btn_add_rule = QPushButton("Add Allow Port (e.g. 80/tcp)")
        
        self.btn_enable.clicked.connect(lambda: self.run_fw_cmd("enable"))
        self.btn_disable.clicked.connect(lambda: self.run_fw_cmd("disable"))
        self.btn_add_rule.clicked.connect(self.add_rule)
        
        actions.addWidget(self.btn_enable)
        actions.addWidget(self.btn_disable)
        actions.addWidget(self.btn_add_rule)
        layout.addLayout(actions)
        
        self.refresh_devices()

    def refresh_devices(self):
        self.device_combo.clear()
        for dev in self.db_mgr.get_devices():
            self.device_combo.addItem(f"{dev['name']} ({dev['ip']})", dev)

    def detect_firewall(self):
        dev = self.device_combo.currentData()
        if not dev: return
        cmd = "if systemctl is-active --quiet ufw; then echo ufw; elif systemctl is-active --quiet firewalld; then echo firewalld; else echo none; fi"
        self.worker = SSHWorker(dev, cmd, self.sec_mgr)
        self.worker.finished.connect(self.on_detected)
        self.worker.start()

    def on_detected(self, result):
        fw = result['stdout'].strip()
        self.detected_fw = fw
        self.status_lbl.setText(f"Firewall: {fw}")
        
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
            cmd = ""
            if self.detected_fw == 'ufw':
                cmd = f"ufw allow {port}"
            elif self.detected_fw == 'firewalld':
                cmd = f"firewall-cmd --permanent --add-port={port} && firewall-cmd --reload"
            self.run_raw_cmd(cmd)
