from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QPushButton, QTextEdit, QInputDialog, QMessageBox, QGroupBox, QSplitter, QFormLayout, QLineEdit
from PyQt6.QtCore import Qt
import base64
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
        
        # Left Panel: Rules and Builder
        left_panel = QWidget()
        left_lay = QVBoxLayout(left_panel)
        left_lay.setContentsMargins(0,0,10,0)
        
        # Global Actions
        global_actions = QHBoxLayout()
        self.btn_enable = QPushButton("Enable Firewall")
        self.btn_disable = QPushButton("Disable Firewall")
        self.btn_enable.clicked.connect(lambda: self.run_fw_cmd("enable"))
        self.btn_disable.clicked.connect(lambda: self.run_fw_cmd("disable"))
        global_actions.addWidget(self.btn_enable)
        global_actions.addWidget(self.btn_disable)
        left_lay.addLayout(global_actions)
        
        # Rule Builder
        build_grp = QGroupBox("Rule Builder")
        build_lay = QFormLayout(build_grp)
        
        self.r_action = QComboBox()
        self.r_action.addItems(["Allow", "Deny"])
        self.r_proto = QComboBox()
        self.r_proto.addItems(["TCP", "UDP", "Both"])
        self.r_port = QLineEdit()
        self.r_port.setPlaceholderText("e.g. 80, 443, 8000:8080")
        self.r_src = QLineEdit()
        self.r_src.setPlaceholderText("Optional: IP or Subnet (e.g. 192.168.1.0/24)")
        
        self.btn_add_rule = QPushButton("Add Rule")
        self.btn_add_rule.setObjectName("PrimaryBtn")
        self.btn_add_rule.clicked.connect(self.add_rule)
        
        build_lay.addRow("Action:", self.r_action)
        build_lay.addRow("Protocol:", self.r_proto)
        build_lay.addRow("Port(s):", self.r_port)
        build_lay.addRow("Source IP:", self.r_src)
        build_lay.addRow(self.btn_add_rule)
        left_lay.addWidget(build_grp)
        
        # Delete Rule
        del_grp = QGroupBox("Remove Rule")
        del_lay = QHBoxLayout(del_grp)
        self.r_del_target = QLineEdit()
        self.r_del_target.setPlaceholderText("Rule Number (ufw) or Port (e.g. 80/tcp)")
        self.btn_del_rule = QPushButton("Delete")
        self.btn_del_rule.setObjectName("DangerBtn")
        self.btn_del_rule.clicked.connect(self.del_rule)
        del_lay.addWidget(self.r_del_target)
        del_lay.addWidget(self.btn_del_rule)
        left_lay.addWidget(del_grp)
        
        # Logs
        self.output_log = QTextEdit()
        self.output_log.setReadOnly(True)
        self.output_log.setStyleSheet("background-color: #11111b; font-family: monospace;")
        left_lay.addWidget(QLabel("Execution Output:"))
        left_lay.addWidget(self.output_log)
        
        splitter.addWidget(left_panel)
        
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
        
        splitter.setSizes([450, 550])
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
        # --- UPDATED THREAD HANDLING ---
        if not hasattr(self, 'active_workers'): self.active_workers = []
        self.active_workers = [w for w in self.active_workers if w.isRunning()]
        
        worker = SSHWorker(dev, cmd, self.sec_mgr)
        worker.finished.connect(self.on_detected)
        
        self.active_workers.append(worker)
        worker.start()
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
        # Wrap the command in base64 to ensure sudo applies to compound commands (&&, ||)
        # and to safely escape all complex quotes in firewall rich-rules.
        b64_cmd = base64.b64encode(cmd.encode('utf-8')).decode('utf-8')
        safe_cmd = f"bash -c 'echo {b64_cmd} | base64 -d | bash'"
        
        self.worker_cmd = SSHWorker(dev, safe_cmd, self.sec_mgr, use_sudo=True)
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
        
        action = self.r_action.currentText().lower()
        proto = self.r_proto.currentText().lower()
        port = self.r_port.text().strip()
        src = self.r_src.text().strip()
        
        if not port:
            QMessageBox.warning(self, "Input Error", "Please specify a port or range.")
            return

        cmd = ""
        if self.detected_fw == 'ufw':
            proto_str = "" if proto == "both" else f"proto {proto}"
            src_str = f"from {src}" if src else "from any"
            # Normalize firewalld hyphen ranges to ufw colon ranges just in case
            port = port.replace("-", ":") 
            cmd = f"ufw {action} {src_str} to any port {port} {proto_str}"
            
        elif self.detected_fw == 'firewalld':
            fw_action = "accept" if action == "allow" else "reject"
            port = port.replace(":", "-") # Firewalld uses hyphens for ranges
            
            if src:
                # Use rich rule for source specific
                p_str = "" if proto == "both" else f' protocol="{proto}"'
                cmd = f"firewall-cmd --permanent --add-rich-rule='rule family=\"ipv4\" source address=\"{src}\" port port=\"{port}\"{p_str} {fw_action}'"
            else:
                if action == "deny":
                    cmd = f"firewall-cmd --permanent --add-rich-rule='rule family=\"ipv4\" port port=\"{port}\" protocol=\"{proto if proto != 'both' else 'tcp'}\" reject'"
                else:
                    if proto == "both":
                        cmd = f"firewall-cmd --permanent --add-port={port}/tcp && firewall-cmd --permanent --add-port={port}/udp"
                    else:
                        cmd = f"firewall-cmd --permanent --add-port={port}/{proto}"
            
            cmd += " && firewall-cmd --reload"
            
        self.run_raw_cmd(cmd)
        
    def del_rule(self):
        if not self.detected_fw or self.detected_fw == 'none': return
        
        target = self.r_del_target.text().strip()
        if not target: return
        
        cmd = ""
        if self.detected_fw == 'ufw':
            # Target can be a rule number or a command equivalent (e.g. 'allow 80/tcp')
            cmd = f"ufw --force delete {target}"
        elif self.detected_fw == 'firewalld':
            # Simplified removal for standard ports. Rich rules require exact string matching.
            if '/' in target:
                cmd = f"firewall-cmd --permanent --remove-port={target} && firewall-cmd --reload"
            else:
                cmd = f"firewall-cmd --permanent --remove-port={target}/tcp && firewall-cmd --permanent --remove-port={target}/udp && firewall-cmd --reload"
                
        self.run_raw_cmd(cmd)
