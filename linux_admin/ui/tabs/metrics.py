import base64
import time
import pyqtgraph as pg
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, 
                             QLabel, QSplitter, QTabWidget, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QTextEdit)
from PyQt6.QtCore import QTimer, Qt
from linux_admin.ui.workers import SSHWorker

class MetricsTab(QWidget):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        self.is_polling = False
        
        # --- State Tracking for Rate Calculations ---
        self.last_net_time = 0
        self.last_rx_bytes = 0
        self.last_tx_bytes = 0
        
        # --- UI Layout ---
        layout = QVBoxLayout(self)
        
        # Header Selection
        header = QHBoxLayout()
        header.addWidget(QLabel("Select Device to Monitor:"))
        self.device_combo = QComboBox()
        self.device_combo.currentIndexChanged.connect(self.reset_graphs)
        header.addWidget(self.device_combo)
        
        self.status_lbl = QLabel("Status: Waiting...")
        header.addWidget(self.status_lbl)
        header.addStretch()
        layout.addLayout(header)
        
        # --- Nested Tabs for Cycling Visualizations ---
        self.viz_tabs = QTabWidget()
        layout.addWidget(self.viz_tabs)
        
        # Setup the 4 Sub-Tabs
        self.setup_resource_tab()
        self.setup_network_tab()
        self.setup_health_tab()
        self.setup_procs_logins_tab()
        
        # --- Data Arrays (60 data points for graphs) ---
        self.cpu_data = [0]*60
        self.ram_data = [0]*60
        self.rx_data = [0]*60
        self.tx_data = [0]*60
        self.load_data = [0]*60
        self.swap_data = [0]*60
        
        # --- Poller ---
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll_metrics)
        self.timer.start(3000) # Poll every 3 seconds for smooth realtime feel
        
        self.refresh_devices()

    def setup_resource_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # CPU
        self.cpu_plot = pg.PlotWidget(title="CPU Usage (%)")
        self.cpu_plot.setYRange(0, 100)
        self.cpu_plot.showGrid(x=True, y=True)
        self.cpu_curve = self.cpu_plot.plot(pen=pg.mkPen('c', width=2)) # Cyan
        
        # RAM
        self.ram_plot = pg.PlotWidget(title="RAM Usage (MB)")
        self.ram_plot.showGrid(x=True, y=True)
        self.ram_curve = self.ram_plot.plot(pen=pg.mkPen('m', width=2)) # Magenta
        
        splitter.addWidget(self.cpu_plot)
        splitter.addWidget(self.ram_plot)
        layout.addWidget(splitter)
        self.viz_tabs.addTab(tab, "Core Resources (CPU/RAM)")

    def setup_network_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # RX
        self.rx_plot = pg.PlotWidget(title="Network Receive (KB/s)")
        self.rx_plot.showGrid(x=True, y=True)
        self.rx_curve = self.rx_plot.plot(pen=pg.mkPen('g', width=2), fillLevel=0, brush=(0,255,0,50))
        
        # TX
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
        
        # Load Average Graph
        self.load_plot = pg.PlotWidget(title="System Load Average (1m)")
        self.load_plot.showGrid(x=True, y=True)
        self.load_curve = self.load_plot.plot(pen=pg.mkPen('r', width=2))
        
        # Text/Stats display
        stats_widget = QWidget()
        stats_layout = QVBoxLayout(stats_widget)
        self.disk_lbl = QLabel("<b>Root Disk Space:</b> Fetching...")
        self.disk_lbl.setStyleSheet("font-size: 16px;")
        
        self.swap_plot = pg.PlotWidget(title="Swap Memory Used (MB)")
        self.swap_plot.showGrid(x=True, y=True)
        self.swap_curve = self.swap_plot.plot(pen=pg.mkPen(color=(255, 165, 0), width=2)) # Orange
        
        stats_layout.addWidget(self.disk_lbl)
        stats_layout.addWidget(self.swap_plot)
        
        splitter.addWidget(self.load_plot)
        splitter.addWidget(stats_widget)
        layout.addWidget(splitter)
        self.viz_tabs.addTab(tab, "System Health & Disk")

    def setup_procs_logins_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Top Procs Table
        proc_widget = QWidget()
        proc_layout = QVBoxLayout(proc_widget)
        proc_layout.addWidget(QLabel("Top 5 Processes by CPU:"))
        self.proc_table = QTableWidget()
        self.proc_table.setColumnCount(5)
        self.proc_table.setHorizontalHeaderLabels(["PID", "User", "CPU%", "MEM%", "Command"])
        self.proc_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        proc_layout.addWidget(self.proc_table)
        
        # Logins
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
        self.cpu_data = [0]*60
        self.ram_data = [0]*60
        self.rx_data = [0]*60
        self.tx_data = [0]*60
        self.load_data = [0]*60
        self.swap_data = [0]*60
        
        self.last_net_time = 0
        self.last_rx_bytes = 0
        self.last_tx_bytes = 0
        
        self.cpu_curve.setData(self.cpu_data)
        self.ram_curve.setData(self.ram_data)
        self.rx_curve.setData(self.rx_data)
        self.tx_curve.setData(self.tx_data)
        self.load_curve.setData(self.load_data)
        self.swap_curve.setData(self.swap_data)

    def poll_metrics(self):
        dev = self.device_combo.currentData()
        if not dev or self.is_polling: 
            return
            
        self.is_polling = True
        self.status_lbl.setText("Status: Polling...")
        self.status_lbl.setStyleSheet("color: yellow;")
        
        # All-in-one metrics fetch script
        bash_payload = r"""
cpu=$(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1}')
ram=$(free -m | awk 'NR==2{print $3}')
swap=$(free -m | awk 'NR==3{print $3}')
net=$(cat /proc/net/dev | awk -F'[: ]+' 'NR>2 && $2 != "lo" {rx+=$2; tx+=$10} END {print rx" "tx}')
disk=$(df -h / | awk 'NR==2{print $5"|"$3"|"$2}')
load=$(cat /proc/loadavg | awk '{print $1}')

echo "SYS_METRICS_START"
echo "CPU|$cpu"
echo "RAM|$ram"
echo "SWAP|$swap"
echo "NET|$net"
echo "DISK|$disk"
echo "LOAD|$load"
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
        self.status_lbl.setText(f"Status: Error - {err_msg[:30]}...")
        self.status_lbl.setStyleSheet("color: red;")

    def update_ui(self, result):
        self.is_polling = False
        
        if result['code'] != 0:
            self.status_lbl.setText("Status: Error executing commands.")
            self.status_lbl.setStyleSheet("color: red;")
            return
            
        self.status_lbl.setText("Status: Connected & Polling")
        self.status_lbl.setStyleSheet("color: #00ff00;")
        
        stdout = result['stdout']
        if "SYS_METRICS_START" not in stdout: return
        
        try:
            parts = stdout.split("===PROCS===")
            metrics_raw = parts[0].replace("SYS_METRICS_START\n", "").strip()
            
            procs_and_logins = parts[1].split("===LOGINS===")
            procs_raw = procs_and_logins[0].strip()
            logins_raw = procs_and_logins[1].strip() if len(procs_and_logins) > 1 else ""
            
            # 1. Parse Key-Value Metrics
            metrics = {}
            for line in metrics_raw.split('\n'):
                if '|' in line:
                    k, v = line.split('|', 1)
                    metrics[k] = v.strip()

            # Update CPU, RAM, SWAP, LOAD
            if 'CPU' in metrics and metrics['CPU']:
                self.cpu_data.pop(0)
                self.cpu_data.append(float(metrics['CPU']))
                self.cpu_curve.setData(self.cpu_data)
                
            if 'RAM' in metrics and metrics['RAM']:
                self.ram_data.pop(0)
                self.ram_data.append(float(metrics['RAM']))
                self.ram_curve.setData(self.ram_data)
                
            if 'SWAP' in metrics and metrics['SWAP']:
                self.swap_data.pop(0)
                self.swap_data.append(float(metrics['SWAP']))
                self.swap_curve.setData(self.swap_data)
                
            if 'LOAD' in metrics and metrics['LOAD']:
                self.load_data.pop(0)
                self.load_data.append(float(metrics['LOAD']))
                self.load_curve.setData(self.load_data)

            if 'DISK' in metrics and metrics['DISK']:
                d_parts = metrics['DISK'].split('|')
                if len(d_parts) == 3:
                    self.disk_lbl.setText(f"<b>Root Disk Space:</b> {d_parts[0]} Used ({d_parts[1]} / {d_parts[2]})")

            # Calculate Network Speeds
            if 'NET' in metrics and metrics['NET']:
                rx_tx = metrics['NET'].split()
                if len(rx_tx) == 2:
                    current_rx = int(rx_tx[0])
                    current_tx = int(rx_tx[1])
                    current_time = time.time()
                    
                    if self.last_net_time != 0:
                        time_diff = current_time - self.last_net_time
                        if time_diff > 0:
                            rx_speed = ((current_rx - self.last_rx_bytes) / 1024) / time_diff # KB/s
                            tx_speed = ((current_tx - self.last_tx_bytes) / 1024) / time_diff # KB/s
                            
                            # Prevent negative spikes on counter resets
                            if rx_speed >= 0 and tx_speed >= 0:
                                self.rx_data.pop(0)
                                self.rx_data.append(rx_speed)
                                self.rx_curve.setData(self.rx_data)
                                
                                self.tx_data.pop(0)
                                self.tx_data.append(tx_speed)
                                self.tx_curve.setData(self.tx_data)
                    
                    self.last_rx_bytes = current_rx
                    self.last_tx_bytes = current_tx
                    self.last_net_time = current_time

            # 2. Update Process Table
            proc_lines = procs_raw.split('\n')
            if len(proc_lines) > 1: # Line 1 is header
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
            self.status_lbl.setText(f"Status: Parse Error ({str(e)})")
