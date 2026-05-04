from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QTextEdit, 
                             QPushButton, QRadioButton, QButtonGroup, QGroupBox, QLineEdit, QSplitter)
from PyQt6.QtCore import Qt
import base64
from linux_admin.core.ansible_manager import AnsibleManager
from linux_admin.ui.workers import AnsibleWorker, SSHWorker

class PackagesTab(QWidget):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        self.ansible_mgr = AnsibleManager(sec_mgr)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        title = QLabel("Package Management & Updates")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # --- Left Panel: Ansible Targeting ---
        left_group = QGroupBox("Ansible Automation")
        left_layout = QVBoxLayout(left_group)
        
        target_layout = QHBoxLayout()
        self.radio_device = QRadioButton("Single Server")
        self.radio_group = QRadioButton("Server Group")
        self.radio_device.setChecked(True)
        self.btn_group = QButtonGroup()
        self.btn_group.addButton(self.radio_device)
        self.btn_group.addButton(self.radio_group)
        self.target_combo = QComboBox()
        target_layout.addWidget(self.radio_device)
        target_layout.addWidget(self.radio_group)
        target_layout.addWidget(self.target_combo)
        left_layout.addLayout(target_layout)
        
        self.radio_device.toggled.connect(self.refresh_targets)
        
        left_layout.addWidget(QLabel("Packages (comma separated):"))
        self.pkg_input = QTextEdit()
        self.pkg_input.setMaximumHeight(80)
        self.pkg_input.setPlaceholderText("e.g. nginx, htop, curl")
        left_layout.addWidget(self.pkg_input)
        
        action_layout = QHBoxLayout()
        self.action_combo = QComboBox()
        self.action_combo.addItems(["present", "latest", "absent"])
        self.btn_run = QPushButton("Deploy via Ansible")
        self.btn_run.setObjectName("PrimaryBtn")
        self.btn_run.clicked.connect(self.run_ansible)
        action_layout.addWidget(QLabel("State:"))
        action_layout.addWidget(self.action_combo)
        action_layout.addWidget(self.btn_run)
        left_layout.addLayout(action_layout)
        
        splitter.addWidget(left_group)
        
        # --- Right Panel: Quick Actions ---
        right_group = QGroupBox("Quick Commands (Selected Target)")
        right_layout = QVBoxLayout(right_group)
        
        chk_layout = QHBoxLayout()
        self.chk_input = QLineEdit()
        self.chk_input.setPlaceholderText("Package name...")
        self.btn_chk = QPushButton("Check if Installed")
        self.btn_chk.clicked.connect(self.check_package)
        chk_layout.addWidget(self.chk_input)
        chk_layout.addWidget(self.btn_chk)
        right_layout.addLayout(chk_layout)
        
        self.btn_update_all = QPushButton("Run Full System Update (apt/yum)")
        self.btn_update_all.setStyleSheet("background-color: #fab387; color: #11111b; font-weight: bold;")
        self.btn_update_all.clicked.connect(self.system_update)
        right_layout.addWidget(self.btn_update_all)
        right_layout.addStretch()
        
        splitter.addWidget(right_group)
        
        # --- Output Log ---
        self.output_log = QTextEdit()
        self.output_log.setReadOnly(True)
        self.output_log.setStyleSheet("font-family: monospace; background-color: #11111b;")
        layout.addWidget(QLabel("Execution Output:"))
        layout.addWidget(self.output_log)
        
        self.refresh_devices()

    def refresh_devices(self):
        self.refresh_targets()

    def refresh_targets(self):
        self.target_combo.clear()
        device_status = getattr(self.db_mgr, 'device_status', {})
        
        if self.radio_device.isChecked():
            for dev in self.db_mgr.get_devices():
                if device_status.get(dev['id']) == "Reachable":
                    self.target_combo.addItem(f"{dev['name']} ({dev['ip']})", [dev])
        else:
            for g in self.db_mgr.get_groups():
                devices = self.db_mgr.get_devices(group_id=g['id'])
                reachable_devs = [d for d in devices if device_status.get(d['id']) == "Reachable"]
                if reachable_devs:
                    self.target_combo.addItem(f"Group: {g['name']} ({len(reachable_devs)} reachable)", reachable_devs)

    def log(self, text):
        self.output_log.append(text)

    def run_ansible(self):
        devices = self.target_combo.currentData()
        if not devices: return
        pkgs = [p.strip() for p in self.pkg_input.toPlainText().split(',') if p.strip()]
        if not pkgs: return
        
        state = self.action_combo.currentText()
        self.log(f"\n[Ansible] Starting task for {len(devices)} targets...")
        self.btn_run.setEnabled(False)
        
        # --- UPDATED THREAD HANDLING ---
        if not hasattr(self, 'active_workers'): self.active_workers = []
        self.active_workers = [w for w in self.active_workers if w.isRunning()]
        
        worker = AnsibleWorker(self.ansible_mgr, devices, pkgs, state)
        worker.finished.connect(self.on_ansible_done)
        
        self.active_workers.append(worker)
        worker.start()

    def on_ansible_done(self, out, err, code):
        self.log(out)
        if err: self.log(f"Errors:\n{err}")
        self.btn_run.setEnabled(True)

    def get_single_device(self):
        devices = self.target_combo.currentData()
        if not devices or len(devices) > 1:
            self.log("Quick actions only apply to a Single Server selection.")
            return None
        return devices[0]

    def check_package(self):
        dev = self.get_single_device()
        pkg = self.chk_input.text().strip()
        if not dev or not pkg: return
        
        self.log(f"\nChecking if '{pkg}' is installed on {dev['name']}...")
        cmd = f"dpkg -s {pkg} 2>/dev/null | grep Status || rpm -q {pkg} || echo 'Not installed or unsupported PM'"
        self.w1 = SSHWorker(dev, cmd, self.sec_mgr)
        self.w1.finished.connect(lambda r: self.log(r['stdout'] or r['stderr']))
        self.w1.start()

    def system_update(self):
        dev = self.get_single_device()
        if not dev: return
        
        self.log(f"\nInitiating FULL SYSTEM UPDATE on {dev['name']}...")
        cmd = "apt-get update && apt-get upgrade -y || yum update -y"
        
        # Wrap the compound command in base64 so sudo applies to the whole chain
        b64_cmd = base64.b64encode(cmd.encode('utf-8')).decode('utf-8')
        safe_cmd = f"bash -c 'echo {b64_cmd} | base64 -d | bash'"
        
        self.w2 = SSHWorker(dev, safe_cmd, self.sec_mgr, use_sudo=True)
        self.w2.finished.connect(lambda r: self.log("Update Complete:\n" + r['stdout']))
        self.w2.start()
