from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QTextEdit, QPushButton, QRadioButton, QButtonGroup
from linux_admin.core.ansible_manager import AnsibleManager
from linux_admin.ui.workers import AnsibleWorker

class PackagesTab(QWidget):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        self.ansible_mgr = AnsibleManager(sec_mgr)
        
        layout = QVBoxLayout(self)
        
        # Target Selection
        target_layout = QHBoxLayout()
        self.radio_group = QRadioButton("Target Group")
        self.radio_device = QRadioButton("Target Device")
        self.radio_device.setChecked(True)
        
        self.btn_group = QButtonGroup()
        self.btn_group.addButton(self.radio_group)
        self.btn_group.addButton(self.radio_device)
        
        self.target_combo = QComboBox()
        
        target_layout.addWidget(self.radio_group)
        target_layout.addWidget(self.radio_device)
        target_layout.addWidget(self.target_combo)
        layout.addLayout(target_layout)
        
        self.radio_group.toggled.connect(self.refresh_targets)
        
        # Package details
        layout.addWidget(QLabel("Packages (comma separated):"))
        self.pkg_input = QTextEdit()
        self.pkg_input.setMaximumHeight(60)
        layout.addWidget(self.pkg_input)
        
        action_layout = QHBoxLayout()
        self.action_combo = QComboBox()
        self.action_combo.addItems(["present", "latest", "absent"]) # Ansible states
        action_layout.addWidget(QLabel("Action State:"))
        action_layout.addWidget(self.action_combo)
        
        self.btn_run = QPushButton("Execute Ansible Playbook")
        self.btn_run.clicked.connect(self.run_ansible)
        action_layout.addWidget(self.btn_run)
        layout.addLayout(action_layout)
        
        # Output
        self.output_log = QTextEdit()
        self.output_log.setReadOnly(True)
        layout.addWidget(QLabel("Ansible Execution Log:"))
        layout.addWidget(self.output_log)
        
        self.refresh_devices()

    def refresh_devices(self):
        self.refresh_targets()

    def refresh_targets(self):
        self.target_combo.clear()
        if self.radio_device.isChecked():
            for dev in self.db_mgr.get_devices():
                self.target_combo.addItem(f"{dev['name']} ({dev['ip']})", [dev])
        else:
            for g in self.db_mgr.get_groups():
                devices = self.db_mgr.get_devices(group_id=g['id'])
                self.target_combo.addItem(f"Group: {g['name']} ({len(devices)} devices)", devices)

    def run_ansible(self):
        devices = self.target_combo.currentData()
        if not devices: return
        
        pkgs = [p.strip() for p in self.pkg_input.toPlainText().split(',') if p.strip()]
        if not pkgs: return
        
        state = self.action_combo.currentText()
        self.output_log.append(f"Starting Ansible job for {len(devices)} targets...")
        self.btn_run.setEnabled(False)
        
        self.worker = AnsibleWorker(self.ansible_mgr, devices, pkgs, state)
        self.worker.finished.connect(self.on_ansible_done)
        self.worker.error.connect(lambda e: self.output_log.append(f"Error: {e}"))
        self.worker.start()

    def on_ansible_done(self, out, err, code):
        self.output_log.append(f"\n--- STDOUT ---\n{out}")
        if err: self.output_log.append(f"\n--- STDERR ---\n{err}")
        self.output_log.append(f"Exited with code {code}")
        self.btn_run.setEnabled(True)
