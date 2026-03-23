import base64
import pyqtgraph as pg
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, 
                             QLabel, QTableWidget, QTableWidgetItem, QHeaderView, 
                             QTextEdit, QTabWidget, QSplitter)
from PyQt6.QtCore import QTimer, Qt
from linux_admin.ui.workers import SSHWorker

class GPUTab(QWidget):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        self.is_polling = False
        
        # --- Multi-GPU Data Storage ---
        self.gpu_history = {} # Format: { gpu_idx: {'util': [], 'vram': [], 'temp': [], 'power': []} }
        self.gpu_curves = {'util': {}, 'vram': {}, 'temp': {}, 'power': {}}
        self.colors = [(0, 255, 255), (255, 0, 255), (255, 255, 0), (0, 255, 0), (255, 0, 0), (255, 165, 0)] # c, m, y, g, r, orange
        
        # --- UI Layout ---
        layout = QVBoxLayout(self)
        
        # Header Selection
        header = QHBoxLayout()
        header.addWidget(QLabel("Device:"))
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
        
        self.setup_overview_tab()
        self.setup_utilization_tab()
        self.setup_thermals_tab()
        
        # --- Poller ---
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll_metrics)
        self.timer.start(4000) # Poll every 4 seconds
        
        self.refresh_devices()

    def setup_overview_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        self.general_metrics = QTextEdit()
        self.general_metrics.setReadOnly(True)
        self.general_metrics.setMaximumHeight(100)
        layout.addWidget(QLabel("GPU Hardware Summary:"))
        layout.addWidget(self.general_metrics)
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["PID", "Process Name", "VRAM Used", "System User"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(QLabel("Processes Actively Using GPU:"))
        layout.addWidget(self.table)
        
        self.viz_tabs.addTab(tab, "Overview & Processes")

    def setup_utilization_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        self.util_plot = pg.PlotWidget(title="GPU Utilization (%)")
        self.util_plot.setYRange(0, 100)
        self.util_plot.showGrid(x=True, y=True)
        self.util_plot.addLegend()
        
        self.vram_plot = pg.PlotWidget(title="VRAM Usage (MB)")
        self.vram_plot.showGrid(x=True, y=True)
        self.vram_plot.addLegend()
        
        splitter.addWidget(self.util_plot)
        splitter.addWidget(self.vram_plot)
        layout.addWidget(splitter)
        self.viz_tabs.addTab(tab, "GPU & VRAM Utilization")

    def setup_thermals_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        self.temp_plot = pg.PlotWidget(title="GPU Core Temperature (°C)")
        self.temp_plot.showGrid(x=True, y=True)
        self.temp_plot.addLegend()
        
        self.power_plot = pg.PlotWidget(title="Power Draw (Watts)")
        self.power_plot.showGrid(x=True, y=True)
        self.power_plot.addLegend()
        
        splitter.addWidget(self.temp_plot)
        splitter.addWidget(self.power_plot)
        layout.addWidget(splitter)
        self.viz_tabs.addTab(tab, "Thermals & Power")

    def refresh_devices(self):
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for dev in self.db_mgr.get_devices():
            self.device_combo.addItem(f"{dev['name']} ({dev['ip']})", dev)
        self.device_combo.blockSignals(False)
        self.reset_graphs()

    def reset_graphs(self):
        # Clear all historical data and curves when switching devices
        self.gpu_history.clear()
        
        self.util_plot.clear()
        self.vram_plot.clear()
        self.temp_plot.clear()
        self.power_plot.clear()
        
        self.gpu_curves = {'util': {}, 'vram': {}, 'temp': {}, 'power': {}}
        self.general_metrics.clear()
        self.table.setRowCount(0)

    def poll_metrics(self):
        dev = self.device_combo.currentData()
        if not dev or self.is_polling: 
            return
            
        self.is_polling = True
        self.status_lbl.setText("Status: Polling NVIDIA Metrics...")
        self.status_lbl.setStyleSheet("color: yellow;")
        
        # Uses raw string (r"") and pulls power/temperature dynamically as well
        bash_payload = r"""
        export PATH=$PATH:/usr/bin:/bin:/usr/local/bin:/sbin:/usr/sbin
        echo "===GPU_STATS==="
        nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw --format=csv,noheader,nounits 2>/dev/null
        echo "===PROCS==="
        for pid in $(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null); do
            if [ -n "$pid" ]; then
                user=$(ps -o ruser= -p $pid | tr -d ' ')
                proc_name=$(nvidia-smi --query-compute-apps=process_name --format=csv,noheader | grep -w "$pid" | head -1 | awk -F',' '{print $2}')
                vram=$(nvidia-smi --query-compute-apps=used_memory --format=csv,noheader | grep -w "$pid" | head -1 | awk -F',' '{print $3}')
                echo "$pid|$proc_name|$vram|$user"
            fi
        done
        """
        
        b64_script = base64.b64encode(bash_payload.encode('utf-8')).decode('utf-8')
        cmd = f"bash -c 'echo {b64_script} | base64 -d | bash'"
        
        self.worker = SSHWorker(dev, cmd, self.sec_mgr)
        self.worker.finished.connect(self.update_ui)
        self.worker.start()

    def update_ui(self, result):
        self.is_polling = False
        
        if result['code'] != 0:
            self.status_lbl.setText("Status: Error / NVIDIA drivers not found.")
            self.status_lbl.setStyleSheet("color: red;")
            self.general_metrics.setText(f"nvidia-smi failed. Ensure NVIDIA drivers are installed.\nError: {result['stderr']}")
            return
            
        self.status_lbl.setText("Status: Connected & Polling")
        self.status_lbl.setStyleSheet("color: #00ff00;")
        
        parts = result['stdout'].split('===PROCS===')
        if len(parts) < 2: return
        
        stats_raw = parts[0].replace('===GPU_STATS===\n', '').strip()
        procs_raw = parts[1].strip()
        
        # --- 1. Parse GPU Hardware Metrics ---
        overview_text = ""
        for line in stats_raw.split('\n'):
            if not line.strip(): continue
            fields = [x.strip() for x in line.split(',')]
            
            # Expecting: index, name, util, vram_used, vram_total, temp, power
            if len(fields) >= 7:
                idx = int(fields[0])
                name = fields[1]
                util = float(fields[2]) if fields[2] != '[Not Supported]' else 0.0
                vram_used = float(fields[3])
                vram_total = float(fields[4])
                temp = float(fields[5])
                try: power = float(fields[6])
                except ValueError: power = 0.0 # Some GPUs don't report power
                
                overview_text += f"GPU {idx}: {name} | Util: {util}% | VRAM: {vram_used} / {vram_total} MB | Temp: {temp}°C | Power: {power}W\n"
                
                # Dynamically create new lines on the plot if a new GPU is detected
                if idx not in self.gpu_history:
                    self.gpu_history[idx] = {'util': [], 'vram': [], 'temp': [], 'power': []}
                    color = self.colors[idx % len(self.colors)]
                    
                    self.gpu_curves['util'][idx] = self.util_plot.plot(pen=pg.mkPen(color, width=2), name=f"GPU {idx}: {name[:12]}")
                    self.gpu_curves['vram'][idx] = self.vram_plot.plot(pen=pg.mkPen(color, width=2), name=f"GPU {idx}")
                    self.gpu_curves['temp'][idx] = self.temp_plot.plot(pen=pg.mkPen(color, width=2), name=f"GPU {idx}")
                    self.gpu_curves['power'][idx] = self.power_plot.plot(pen=pg.mkPen(color, width=2), name=f"GPU {idx}")
                    
                # Append live data
                self.gpu_history[idx]['util'].append(util)
                self.gpu_history[idx]['vram'].append(vram_used)
                self.gpu_history[idx]['temp'].append(temp)
                self.gpu_history[idx]['power'].append(power)
                
                # Cap the local arrays at 60 points to keep visualizations snappy
                for k in ['util', 'vram', 'temp', 'power']:
                    if len(self.gpu_history[idx][k]) > 60:
                        self.gpu_history[idx][k].pop(0)
                        
                # Update Curves
                self.gpu_curves['util'][idx].setData(self.gpu_history[idx]['util'])
                self.gpu_curves['vram'][idx].setData(self.gpu_history[idx]['vram'])
                self.gpu_curves['temp'][idx].setData(self.gpu_history[idx]['temp'])
                self.gpu_curves['power'][idx].setData(self.gpu_history[idx]['power'])
                
        self.general_metrics.setText(overview_text.strip())
        
        # --- 2. Parse Process Table ---
        self.table.setRowCount(0)
        procs = procs_raw.split('\n')
        row = 0
        for p in procs:
            if not p: continue
            fields = p.split('|')
            if len(fields) >= 4:
                self.table.insertRow(row)
                for col in range(4):
                    self.table.setItem(row, col, QTableWidgetItem(fields[col].strip()))
                row += 1
