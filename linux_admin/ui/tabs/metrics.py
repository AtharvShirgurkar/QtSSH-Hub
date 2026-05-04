import base64
import pyqtgraph as pg
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, 
                             QLabel, QSplitter, QTabWidget, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QTextEdit, QPushButton, 
                             QMessageBox, QGroupBox, QLineEdit, QInputDialog)
from PyQt6.QtCore import QTimer, Qt
from linux_admin.ui.workers import SSHWorker

class MetricsTab(QWidget):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        self.is_polling = False
        self.last_fetched_ts = 0
        self.active_workers = []
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header Selection
        header = QHBoxLayout()
        title = QLabel("Realtime Telemetry")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        header.addWidget(title)
        header.addSpacing(30)
        
        header.addWidget(QLabel("Target Server:"))
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(200)
        self.device_combo.currentIndexChanged.connect(self.reset_graphs)
        header.addWidget(self.device_combo)
        
        self.btn_deploy = QPushButton("Deploy Telemetry Agent")
        self.btn_deploy.setObjectName("PrimaryBtn")
        self.btn_deploy.clicked.connect(self.deploy_agent)
        header.addWidget(self.btn_deploy)
        
        header.addStretch()
        self.status_lbl = QLabel("Standby")
        self.status_lbl.setStyleSheet("font-weight: bold; color: #a6adc8; padding: 5px; background: #313244; border-radius: 5px;")
        header.addWidget(self.status_lbl)
        layout.addLayout(header)
        
        # --- Modern Grid Dashboard ---
        self.viz_tabs = QTabWidget()
        layout.addWidget(self.viz_tabs)
        
        self.setup_dashboards()
        
        # --- Data Arrays ---
        self.timestamps = []
        self.cpu_data = []
        self.ram_data = []
        self.rx_data = []
        self.tx_data = []
        
        # --- Poller ---
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll_metrics)
        self.timer.start(3000) 
        
        self.refresh_devices()

    def apply_plot_style(self, plot, title):
        plot.setTitle(title, color="#cdd6f4", size="12pt")
        if hasattr(plot, 'setBackground'):
            plot.setBackground('#181825')
        plot.showGrid(x=True, y=True, alpha=0.2)
        plot.getAxis('left').setPen('#a6adc8')
        plot.getAxis('bottom').setPen('#a6adc8')
        plot.getAxis('left').setTextPen('#cdd6f4')
        plot.getAxis('bottom').setTextPen('#cdd6f4')

    def setup_dashboards(self):
        # Tab 1: Core Resources
        t1 = QWidget()
        l1 = QHBoxLayout(t1)
        s1 = QSplitter(Qt.Orientation.Horizontal)
        
        self.cpu_plot = pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem(orientation='bottom')})
        self.apply_plot_style(self.cpu_plot, "CPU Utilization (%)")
        self.cpu_plot.setYRange(0, 100)
        self.cpu_curve = self.cpu_plot.plot(pen=pg.mkPen('#89b4fa', width=3), fillLevel=0, brush=(137,180,250,50))
        
        self.ram_plot = pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem(orientation='bottom')})
        self.apply_plot_style(self.ram_plot, "Memory Usage (MB)")
        self.ram_curve = self.ram_plot.plot(pen=pg.mkPen('#cba6f7', width=3), fillLevel=0, brush=(203,166,247,50))
        
        s1.addWidget(self.cpu_plot)
        s1.addWidget(self.ram_plot)
        l1.addWidget(s1)
        self.viz_tabs.addTab(t1, "Core Performance")

        # Tab 2: Network & Disk Info
        t2 = QWidget()
        l2 = QHBoxLayout(t2)
        s2 = QSplitter(Qt.Orientation.Horizontal)
        
        net_widget = pg.GraphicsLayoutWidget()
        net_widget.setBackground('#181825')
        self.rx_plot = net_widget.addPlot(title="Net RX (KB/s)", axisItems={'bottom': pg.DateAxisItem(orientation='bottom')})
        self.apply_plot_style(self.rx_plot, "Net RX (KB/s)")
        self.rx_curve = self.rx_plot.plot(pen=pg.mkPen('#a6e3a1', width=2), fillLevel=0, brush=(166,227,161,50))
        net_widget.nextRow()
        self.tx_plot = net_widget.addPlot(title="Net TX (KB/s)", axisItems={'bottom': pg.DateAxisItem(orientation='bottom')})
        self.apply_plot_style(self.tx_plot, "Net TX (KB/s)")
        self.tx_curve = self.tx_plot.plot(pen=pg.mkPen('#f9e2af', width=2), fillLevel=0, brush=(249,226,175,50))
        
        s2.addWidget(net_widget)
        
        # Disk and Health Group
        health_grp = QGroupBox("System Health")
        hl = QVBoxLayout(health_grp)
        self.disk_lbl = QLabel("Disk Space: Waiting for data...")
        self.disk_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #89dceb;")
        
        self.sockets_lbl = QLabel("Active Sockets: Waiting...")
        self.sockets_lbl.setStyleSheet("font-size: 14px; color: #cdd6f4;")
        
        hl.addWidget(self.disk_lbl)
        hl.addWidget(self.sockets_lbl)
        hl.addStretch()
        
        s2.addWidget(health_grp)
        l2.addWidget(s2)
        self.viz_tabs.addTab(t2, "Network & Health")

        # Tab 3: Processes
        t3 = QWidget()
        l3 = QVBoxLayout(t3)
        
        # Search & Action controls for Processes
        proc_controls = QHBoxLayout()
        self.proc_search = QLineEdit()
        self.proc_search.setPlaceholderText("Search processes by PID, User, or Command...")
        self.proc_search.textChanged.connect(self.filter_processes)
        
        self.btn_term = QPushButton("Term (15)")
        self.btn_term.setToolTip("Send SIGTERM (Graceful exit)")
        self.btn_term.clicked.connect(lambda: self.manage_process('term'))
        
        self.btn_kill = QPushButton("Kill (9)")
        self.btn_kill.setObjectName("DangerBtn")
        self.btn_kill.setToolTip("Send SIGKILL (Force quit)")
        self.btn_kill.clicked.connect(lambda: self.manage_process('kill'))
        
        self.btn_renice = QPushButton("Renice")
        self.btn_renice.setToolTip("Change process CPU scheduling priority")
        self.btn_renice.clicked.connect(lambda: self.manage_process('renice'))
        
        proc_controls.addWidget(self.proc_search)
        proc_controls.addWidget(self.btn_term)
        proc_controls.addWidget(self.btn_kill)
        proc_controls.addWidget(self.btn_renice)
        l3.addLayout(proc_controls)
        
        self.proc_table = QTableWidget()
        self.proc_table.setColumnCount(5)
        self.proc_table.setHorizontalHeaderLabels(["PID", "User", "CPU%", "MEM%", "Command"])
        self.proc_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.proc_table.verticalHeader().setVisible(False)
        self.proc_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        l3.addWidget(self.proc_table)
        
        self.viz_tabs.addTab(t3, "Processes (Top 100)")

    def refresh_devices(self):
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for dev in self.db_mgr.get_devices():
            if self.db_mgr.device_status.get(dev['id']) == "Reachable":
                self.device_combo.addItem(f"{dev['name']} ({dev['ip']})", dev)
        self.device_combo.blockSignals(False)
        self.reset_graphs()

    def reset_graphs(self):
        self.timestamps.clear()
        self.cpu_data.clear()
        self.ram_data.clear()
        self.rx_data.clear()
        self.tx_data.clear()
        self.last_fetched_ts = 0
        
        self.cpu_curve.setData([], [])
        self.ram_curve.setData([], [])
        self.rx_curve.setData([], [])
        self.tx_curve.setData([], [])
        self.disk_lbl.setText("Disk Space: Waiting...")
        self.proc_table.setRowCount(0)

    def deploy_agent(self):
        dev = self.device_combo.currentData()
        if not dev: return
        self.btn_deploy.setEnabled(False)
        self.status_lbl.setText("Deploying...")
        
        bash_payload = r"""set -e
cat << 'EOF' > /usr/local/bin/linux_admin_agent.sh
#!/bin/bash
LOG="/dev/shm/admin_metrics.log"
TMP="/dev/shm/admin_metrics.tmp"
last_rx=0; last_tx=0

while true; do
    TS=$(date +%s)
    cpu=$(vmstat 1 2 | tail -1 | awk '{print 100 - $15}')
    ram=$(free -m | awk 'NR==2{print $3}')
    read rx tx <<< $(cat /proc/net/dev | awk -F'[: ]+' 'NR>2 && $2 != "lo" {rx+=$2; tx+=$10} END {print rx" "tx}')
    rx_speed=0; tx_speed=0
    if [ "$last_rx" -ne 0 ]; then
        rx_speed=$(( (rx - last_rx) / 1024 / 3 ))
        tx_speed=$(( (tx - last_tx) / 1024 / 3 ))
    fi
    last_rx=$rx; last_tx=$tx
    disk=$(df -h / | awk 'NR==2{print $5","$3","$2}')

    echo "$TS|$cpu|$ram|0|$rx_speed|$tx_speed|0|$disk" >> "$LOG"
    lines=$(wc -l < "$LOG" 2>/dev/null || echo 0)
    if [ "$lines" -gt "2000" ]; then tail -n 1000 "$LOG" > "$TMP" && mv "$TMP" "$LOG"; fi
    sleep 3
done
EOF

chmod +x /usr/local/bin/linux_admin_agent.sh
cat << 'EOF' > /etc/systemd/system/linux_admin_agent.service
[Unit]
Description=QtSSH Hub Telemetry
[Service]
ExecStart=/usr/local/bin/linux_admin_agent.sh
Restart=always
[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload && systemctl enable --now linux_admin_agent.service
"""
        cmd = f"bash -c 'echo {base64.b64encode(bash_payload.encode()).decode()} | base64 -d | bash'"
        worker = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        worker.finished.connect(lambda r: self.btn_deploy.setEnabled(True))
        self.active_workers.append(worker)
        worker.start()

    def filter_processes(self):
        search_term = self.proc_search.text().lower()
        for row in range(self.proc_table.rowCount()):
            pid = self.proc_table.item(row, 0).text().lower()
            user = self.proc_table.item(row, 1).text().lower()
            comm = self.proc_table.item(row, 4).text().lower()
            
            if search_term in pid or search_term in comm or search_term in user:
                self.proc_table.setRowHidden(row, False)
            else:
                self.proc_table.setRowHidden(row, True)

    def manage_process(self, action):
        dev = self.device_combo.currentData()
        row = self.proc_table.currentRow()
        
        if not dev or row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a process from the list first.")
            return
            
        pid = self.proc_table.item(row, 0).text()
        comm = self.proc_table.item(row, 4).text()
        cmd = ""
        
        if action == "term":
            if QMessageBox.question(self, "Confirm Term", f"Send SIGTERM to {comm} (PID {pid})?") == QMessageBox.StandardButton.Yes:
                cmd = f"kill -15 {pid}"
        elif action == "kill":
            if QMessageBox.question(self, "Confirm Kill", f"Force KILL {comm} (PID {pid})?\nThis might cause data loss.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                cmd = f"kill -9 {pid}"
        elif action == "renice":
            val, ok = QInputDialog.getInt(self, "Renice Process", f"Set CPU Nice value (-20 to 19) for {comm}\nLower values = Higher priority:", 0, -20, 19)
            if ok:
                cmd = f"renice -n {val} -p {pid}"
                
        if cmd:
            worker = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
            worker.finished.connect(lambda r: self.status_lbl.setText(f"Proc Cmd: {'Success' if r['code'] == 0 else 'Failed'}"))
            self.active_workers.append(worker)
            worker.start()

    def poll_metrics(self):
        dev = self.device_combo.currentData()
        if not dev or self.is_polling: return
        self.is_polling = True
        
        # Extended head to 100 so the user has more processes to search and kill
        bash_payload = f"""
if [ ! -f /dev/shm/admin_metrics.log ]; then echo "MISSING"; exit 0; fi
echo "DATA"
awk -F'|' -v ts="{self.last_fetched_ts}" '($1+0) > (ts+0)' /dev/shm/admin_metrics.log || true
echo "===P==="
ps -eo pid,user,%cpu,%mem,comm --sort=-%cpu | head -n 100 || true
echo "===S==="
ss -s | grep "TCP:" || true
"""
        cmd = f"bash -c 'echo {base64.b64encode(bash_payload.encode()).decode()} | base64 -d | bash'"
        
        worker = SSHWorker(dev, cmd, self.sec_mgr)
        worker.finished.connect(self.update_ui)
        worker.error.connect(lambda e: setattr(self, 'is_polling', False))
        
        # Auto-cleanup
        worker.finished.connect(lambda r, w=worker: self.active_workers.remove(w) if w in self.active_workers else None)
        worker.error.connect(lambda e, w=worker: self.active_workers.remove(w) if w in self.active_workers else None)
        
        self.active_workers.append(worker)
        worker.start()

    def update_ui(self, result):
        self.is_polling = False
        stdout = result.get('stdout', '')
        if "MISSING" in stdout:
            self.status_lbl.setText("Agent Not Running")
            self.status_lbl.setStyleSheet("color: #f38ba8;")
            return
            
        if "DATA" not in stdout: return
        self.status_lbl.setText("Live")
        self.status_lbl.setStyleSheet("color: #a6e3a1;")
        
        try:
            parts = stdout.split("===P===")
            metrics = parts[0].replace("DATA\n", "").strip().split('\n')
            p_s = parts[1].split("===S===")
            procs = p_s[0].strip().split('\n')
            sockets = p_s[1].strip() if len(p_s) > 1 else ""
            
            # --- Graph Updates ---
            for line in metrics:
                if not line or '|' not in line: continue
                m = line.split('|')
                if len(m) < 8: continue
                self.last_fetched_ts = int(m[0])
                self.timestamps.append(int(m[0]))
                self.cpu_data.append(float(m[1]))
                self.ram_data.append(float(m[2]))
                self.rx_data.append(float(m[4]))
                self.tx_data.append(float(m[5]))
                
                d = m[7].split(',')
                if len(d) == 3: self.disk_lbl.setText(f"Root FS: {d[0]} Full ({d[1]} used of {d[2]})")
                
            if len(self.timestamps) > 100:
                self.timestamps = self.timestamps[-100:]
                self.cpu_data = self.cpu_data[-100:]
                self.ram_data = self.ram_data[-100:]
                self.rx_data = self.rx_data[-100:]
                self.tx_data = self.tx_data[-100:]

            if self.timestamps:
                self.cpu_curve.setData(self.timestamps, self.cpu_data)
                self.ram_curve.setData(self.timestamps, self.ram_data)
                self.rx_curve.setData(self.timestamps, self.rx_data)
                self.tx_curve.setData(self.timestamps, self.tx_data)
                
            # --- Processes Table Update (Preserving Selection) ---
            if len(procs) > 1:
                selected_pid = None
                if self.proc_table.currentRow() >= 0:
                    selected_pid = self.proc_table.item(self.proc_table.currentRow(), 0).text()
                    
                self.proc_table.setRowCount(0)
                for i, line in enumerate(procs[1:]):
                    f = line.split()
                    if len(f) >= 5:
                        self.proc_table.insertRow(i)
                        for col, val in enumerate([f[0], f[1], f[2], f[3], " ".join(f[4:])]):
                            self.proc_table.setItem(i, col, QTableWidgetItem(val))
                        
                        # Re-select the previously highlighted process
                        if f[0] == selected_pid:
                            self.proc_table.selectRow(i)
                
                # Re-apply the search filter instantly
                self.filter_processes()
                            
            # --- Network Sockets Update ---
            if sockets:
                self.sockets_lbl.setText(f"Network Sockets:\n{sockets}")
                
        except Exception:
            pass
