import base64
import time
import pyqtgraph as pg
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, 
                             QLabel, QSplitter, QTabWidget, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QTextEdit, QPushButton, QMessageBox)
from PyQt6.QtCore import QTimer, Qt
from linux_admin.ui.workers import SSHWorker

class MetricsTab(QWidget):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        self.is_polling = False
        self.last_fetched_ts = 0  # Crucial for Delta Fetching
        
        # --- UI Layout ---
        layout = QVBoxLayout(self)
        
        # Header Selection
        header = QHBoxLayout()
        header.addWidget(QLabel("Select Device:"))
        self.device_combo = QComboBox()
        self.device_combo.currentIndexChanged.connect(self.reset_graphs)
        header.addWidget(self.device_combo)
        
        self.btn_deploy = QPushButton("Deploy / Start Metrics Agent")
        self.btn_deploy.setStyleSheet("background-color: #005f87; font-weight: bold;")
        self.btn_deploy.clicked.connect(self.deploy_agent)
        header.addWidget(self.btn_deploy)
        
        self.status_lbl = QLabel("Status: Waiting...")
        header.addWidget(self.status_lbl)
        header.addStretch()
        layout.addLayout(header)
        
        # --- Nested Tabs for Cycling Visualizations ---
        self.viz_tabs = QTabWidget()
        layout.addWidget(self.viz_tabs)
        
        self.setup_resource_tab()
        self.setup_network_tab()
        self.setup_health_tab()
        self.setup_procs_logins_tab()
        
        # --- Data Arrays (Unbounded for history viewing, capped at 10000) ---
        self.timestamps = []
        self.cpu_data = []
        self.ram_data = []
        self.rx_data = []
        self.tx_data = []
        self.load_data = []
        self.swap_data = []
        
        # --- Poller ---
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll_metrics)
        self.timer.start(3000) 
        
        self.refresh_devices()

    def setup_resource_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        self.cpu_plot = pg.PlotWidget(title="CPU Usage (%)")
        self.cpu_plot.setYRange(0, 100)
        self.cpu_plot.showGrid(x=True, y=True)
        self.cpu_curve = self.cpu_plot.plot(pen=pg.mkPen('c', width=2))
        
        self.ram_plot = pg.PlotWidget(title="RAM Usage (MB)")
        self.ram_plot.showGrid(x=True, y=True)
        self.ram_curve = self.ram_plot.plot(pen=pg.mkPen('m', width=2))
        
        splitter.addWidget(self.cpu_plot)
        splitter.addWidget(self.ram_plot)
        layout.addWidget(splitter)
        self.viz_tabs.addTab(tab, "Core Resources")

    def setup_network_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        self.rx_plot = pg.PlotWidget(title="Network Receive (KB/s)")
        self.rx_plot.showGrid(x=True, y=True)
        self.rx_curve = self.rx_plot.plot(pen=pg.mkPen('g', width=2), fillLevel=0, brush=(0,255,0,50))
        
        self.tx_plot = pg.PlotWidget(title="Network Transmit (KB/s)")
        self.tx_plot.showGrid(x=True, y=True)
        self.tx_curve = self.tx_plot.plot(pen=pg.mkPen('y', width=2), fillLevel=0, brush=(255,255,0,50))
        
        splitter.addWidget(self.rx_plot)
        splitter.addWidget(self.tx_plot)
        layout.addWidget(splitter)
        self.viz_tabs.addTab(tab, "Network I/O")

    def setup_health_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        self.load_plot = pg.PlotWidget(title="System Load Average (1m)")
        self.load_plot.showGrid(x=True, y=True)
        self.load_curve = self.load_plot.plot(pen=pg.mkPen('r', width=2))
        
        stats_widget = QWidget()
        stats_layout = QVBoxLayout(stats_widget)
        self.disk_lbl = QLabel("<b>Root Disk Space:</b> Fetching...")
        self.disk_lbl.setStyleSheet("font-size: 16px;")
        
        self.swap_plot = pg.PlotWidget(title="Swap Memory Used (MB)")
        self.swap_plot.showGrid(x=True, y=True)
        self.swap_curve = self.swap_plot.plot(pen=pg.mkPen(color=(255, 165, 0), width=2))
        
        stats_layout.addWidget(self.disk_lbl)
        stats_layout.addWidget(self.swap_plot)
        
        splitter.addWidget(self.load_plot)
        splitter.addWidget(stats_widget)
        layout.addWidget(splitter)
        self.viz_tabs.addTab(tab, "System Health")

    def setup_procs_logins_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        proc_widget = QWidget()
        proc_layout = QVBoxLayout(proc_widget)
        proc_layout.addWidget(QLabel("Top 5 Processes by CPU:"))
        self.proc_table = QTableWidget()
        self.proc_table.setColumnCount(5)
        self.proc_table.setHorizontalHeaderLabels(["PID", "User", "CPU%", "MEM%", "Command"])
        self.proc_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        proc_layout.addWidget(self.proc_table)
        
        login_widget = QWidget()
        login_layout = QVBoxLayout(login_widget)
        login_layout.addWidget(QLabel("Recent Logins:"))
        self.login_text = QTextEdit()
        self.login_text.setReadOnly(True)
        login_layout.addWidget(self.login_text)
        
        splitter.addWidget(proc_widget)
        splitter.addWidget(login_widget)
        layout.addWidget(splitter)
        self.viz_tabs.addTab(tab, "Processes & Logins")

    def refresh_devices(self):
        self.device_combo.clear()
        for dev in self.db_mgr.get_devices():
            self.device_combo.addItem(f"{dev['name']} ({dev['ip']})", dev)

    def reset_graphs(self):
        self.timestamps = []
        self.cpu_data = []
        self.ram_data = []
        self.rx_data = []
        self.tx_data = []
        self.load_data = []
        self.swap_data = []
        self.last_fetched_ts = 0
        
        # Clear plots visually
        self.cpu_curve.setData([], [])
        self.ram_curve.setData([], [])
        self.rx_curve.setData([], [])
        self.tx_curve.setData([], [])
        self.load_curve.setData([], [])
        self.swap_curve.setData([], [])

    def deploy_agent(self):
        dev = self.device_combo.currentData()
        if not dev: return
        self.btn_deploy.setEnabled(False)
        self.status_lbl.setText("Status: Deploying Agent...")
        
        # Bash script to create the agent and systemd service.
        # It writes logs to /dev/shm (RAM) to prevent SSD wear out.
        bash_payload = r"""set -e
cat << 'EOF' > /usr/local/bin/linux_admin_agent.sh
#!/bin/bash
LOG="/dev/shm/admin_metrics.log"
TMP="/dev/shm/admin_metrics.tmp"
MAX_LINES=10000
last_rx=0
last_tx=0

while true; do
    TS=$(date +%s)
    cpu=$(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1}')
    ram=$(free -m | awk 'NR==2{print $3}')
    swap=$(free -m | awk 'NR==3{print $3}')
    load=$(cat /proc/loadavg | awk '{print $1}')
    
    # Calculate RX/TX diffs directly in the agent!
    read rx tx <<< $(cat /proc/net/dev | awk -F'[: ]+' 'NR>2 && $2 != "lo" {rx+=$2; tx+=$10} END {print rx" "tx}')
    rx_speed=0; tx_speed=0
    if [ "$last_rx" -ne 0 ]; then
        rx_speed=$(( (rx - last_rx) / 1024 / 3 ))
        tx_speed=$(( (tx - last_tx) / 1024 / 3 ))
    fi
    last_rx=$rx; last_tx=$tx
    disk=$(df -h / | awk 'NR==2{print $5","$3","$2}')

    echo "$TS|$cpu|$ram|$swap|$rx_speed|$tx_speed|$load|$disk" >> "$LOG"

    # Ring buffer logic: Slice file in half if it gets too big
    lines=$(wc -l < "$LOG" 2>/dev/null || echo 0)
    if [ "$lines" -gt "$MAX_LINES" ]; then
        tail -n $((MAX_LINES / 2)) "$LOG" > "$TMP" && mv "$TMP" "$LOG"
    fi
    sleep 3
done
EOF

chmod +x /usr/local/bin/linux_admin_agent.sh

cat << 'EOF' > /etc/systemd/system/linux_admin_agent.service
[Unit]
Description=Linux Admin Live Metrics Agent
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/linux_admin_agent.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now linux_admin_agent.service
"""
        b64_script = base64.b64encode(bash_payload.encode('utf-8')).decode('utf-8')
        cmd = f"bash -c 'echo {b64_script} | base64 -d | bash'"
        
        self.worker_deploy = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_deploy.finished.connect(self.on_deploy_finished)
        self.worker_deploy.start()

    def on_deploy_finished(self, result):
        self.btn_deploy.setEnabled(True)
        if result['code'] == 0:
            QMessageBox.information(self, "Success", "Background Agent Deployed and Running!")
        else:
            QMessageBox.critical(self, "Error", f"Failed to deploy agent: {result['stderr']}")

    def poll_metrics(self):
        dev = self.device_combo.currentData()
        if not dev or self.is_polling: 
            return
            
        self.is_polling = True
        
        # DELTA FETCH SCRIPT
        # If last_ts == 0, fetch the last 150 points to populate graph instantly.
        # Otherwise, strictly fetch rows newer than last_fetched_ts.
        bash_payload = f"""
if [ ! -f /dev/shm/admin_metrics.log ]; then
    echo "AGENT_NOT_RUNNING"
    exit 0
fi

echo "SYS_METRICS_START"
if [ "{self.last_fetched_ts}" == "0" ]; then
    tail -n 150 /dev/shm/admin_metrics.log
else
    awk -F'|' -v ts="{self.last_fetched_ts}" '$1 > ts' /dev/shm/admin_metrics.log
fi

echo "===PROCS==="
ps -eo pid,user,%cpu,%mem,comm --sort=-%cpu | head -n 6
echo "===LOGINS==="
last -a -n 5
"""
        b64_script = base64.b64encode(bash_payload.encode('utf-8')).decode('utf-8')
        cmd = f"bash -c 'echo {b64_script} | base64 -d | bash'"
        
        self.worker = SSHWorker(dev, cmd, self.sec_mgr)
        self.worker.finished.connect(self.update_ui)
        self.worker.error.connect(self.handle_error)
        self.worker.start()

    def handle_error(self, err_msg):
        self.is_polling = False
        self.status_lbl.setText(f"Status: SSH Timeout / Error")
        self.status_lbl.setStyleSheet("color: red;")

    def update_ui(self, result):
        self.is_polling = False
        if result['code'] != 0: return
        
        stdout = result['stdout']
        if "AGENT_NOT_RUNNING" in stdout:
            self.status_lbl.setText("Status: Agent Missing. Please Deploy Agent.")
            self.status_lbl.setStyleSheet("color: orange;")
            return
            
        if "SYS_METRICS_START" not in stdout: return
        
        self.status_lbl.setText("Status: Delta Polling Active")
        self.status_lbl.setStyleSheet("color: #00ff00;")
        
        try:
            parts = stdout.split("===PROCS===")
            metrics_lines = parts[0].replace("SYS_METRICS_START\n", "").strip().split('\n')
            
            procs_and_logins = parts[1].split("===LOGINS===")
            procs_raw = procs_and_logins[0].strip()
            logins_raw = procs_and_logins[1].strip() if len(procs_and_logins) > 1 else ""
            
            # 1. Parse Delta Metrics Lines
            for line in metrics_lines:
                if not line.strip() or '|' not in line: continue
                
                # Format: TS | CPU | RAM | SWAP | RX | TX | LOAD | DISK (used,total,%)
                ts, cpu, ram, swap, rx, tx, load, disk = line.split('|')
                
                self.last_fetched_ts = int(ts)
                
                # Append to arrays
                self.timestamps.append(int(ts))
                self.cpu_data.append(float(cpu))
                self.ram_data.append(float(ram))
                self.swap_data.append(float(swap))
                self.rx_data.append(float(rx))
                self.tx_data.append(float(tx))
                self.load_data.append(float(load))
                
                # Cap Python arrays at 10,000 points to prevent local RAM leaks
                if len(self.timestamps) > 10000:
                    self.timestamps.pop(0)
                    self.cpu_data.pop(0); self.ram_data.pop(0); self.swap_data.pop(0)
                    self.rx_data.pop(0); self.tx_data.pop(0); self.load_data.pop(0)
                    
                # Update Disk UI Text
                d_parts = disk.split(',')
                if len(d_parts) == 3:
                    self.disk_lbl.setText(f"<b>Root Disk Space:</b> {d_parts[0]} Used ({d_parts[1]} / {d_parts[2]})")

            # Update Graphs with relative index points for smooth panning
            # (Using len range so graphs auto-pan to the right smoothly)
            if self.timestamps:
                x_axis = list(range(len(self.timestamps)))
                self.cpu_curve.setData(x_axis, self.cpu_data)
                self.ram_curve.setData(x_axis, self.ram_data)
                self.rx_curve.setData(x_axis, self.rx_data)
                self.tx_curve.setData(x_axis, self.tx_data)
                self.load_curve.setData(x_axis, self.load_data)
                self.swap_curve.setData(x_axis, self.swap_data)

            # 2. Update Process Table
            proc_lines = procs_raw.split('\n')
            if len(proc_lines) > 1:
                self.proc_table.setRowCount(0)
                for i, line in enumerate(proc_lines[1:]):
                    fields = line.split()
                    if len(fields) >= 5:
                        self.proc_table.insertRow(i)
                        self.proc_table.setItem(i, 0, QTableWidgetItem(fields[0])) # PID
                        self.proc_table.setItem(i, 1, QTableWidgetItem(fields[1])) # USER
                        self.proc_table.setItem(i, 2, QTableWidgetItem(fields[2])) # CPU
                        self.proc_table.setItem(i, 3, QTableWidgetItem(fields[3])) # MEM
                        self.proc_table.setItem(i, 4, QTableWidgetItem(" ".join(fields[4:]))) # COMM

            # 3. Update Logins
            self.login_text.setText(logins_raw)
            
        except Exception as e:
            self.status_lbl.setText(f"Status: Parse Error")
