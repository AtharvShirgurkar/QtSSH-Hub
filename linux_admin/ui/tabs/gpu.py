import base64
import time
import pyqtgraph as pg
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, 
                             QLabel, QTableWidget, QTableWidgetItem, QHeaderView, 
                             QTextEdit, QTabWidget, QSplitter, QPushButton, QMessageBox)
from PyQt6.QtCore import QTimer, Qt
from linux_admin.ui.workers import SSHWorker

class GPUTab(QWidget):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        self.is_polling = False
        
        self.gpu_history = {} 
        self.gpu_curves = {'util': {}, 'vram': {}, 'temp': {}, 'power': {}}
        self.colors = ['#89b4fa', '#f38ba8', '#a6e3a1', '#f9e2af', '#cba6f7', '#fab387']
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        header = QHBoxLayout()
        title = QLabel("NVIDIA Datacenter GPU Dashboard")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #a6e3a1;")
        header.addWidget(title)
        header.addSpacing(30)
        
        header.addWidget(QLabel("Node:"))
        self.device_combo = QComboBox()
        self.device_combo.currentIndexChanged.connect(self.reset_graphs)
        header.addWidget(self.device_combo)
        
        self.status_lbl = QLabel("Status: Waiting...")
        header.addWidget(self.status_lbl)
        header.addStretch()
        layout.addLayout(header)
        
        self.viz_tabs = QTabWidget()
        layout.addWidget(self.viz_tabs)
        
        self.setup_overview_tab()
        self.setup_utilization_tab()
        self.setup_thermals_tab()
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll_metrics)
        self.timer.start(4000) 
        self.refresh_devices()

    def style_plot(self, p, title):
        p.setTitle(title, color="#cdd6f4")
        if hasattr(p, 'setBackground'):
            p.setBackground('#181825')
        p.showGrid(x=True, y=True, alpha=0.2)
        p.addLegend(offset=(10, 10))

    def setup_overview_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        self.general_metrics = QTextEdit()
        self.general_metrics.setReadOnly(True)
        self.general_metrics.setMaximumHeight(120)
        self.general_metrics.setStyleSheet("background-color: #11111b; font-family: monospace; color: #a6e3a1;")
        layout.addWidget(QLabel("Hardware Summary:"))
        layout.addWidget(self.general_metrics)
        
        act_lay = QHBoxLayout()
        act_lay.addWidget(QLabel("Processes Actively Using GPU:"))
        act_lay.addStretch()
        self.btn_kill = QPushButton("Kill Selected Process")
        self.btn_kill.setObjectName("DangerBtn")
        self.btn_kill.clicked.connect(self.kill_gpu_process)
        act_lay.addWidget(self.btn_kill)
        layout.addLayout(act_lay)
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["PID", "Process Name", "VRAM Used", "System User"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)
        
        self.viz_tabs.addTab(tab, "Overview & Processes")

    def setup_utilization_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.util_plot = pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem(orientation='bottom')})
        self.style_plot(self.util_plot, "Utilization (%)")
        self.util_plot.setYRange(0, 100)
        
        self.vram_plot = pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem(orientation='bottom')})
        self.style_plot(self.vram_plot, "VRAM Usage (MB)")
        
        splitter.addWidget(self.util_plot); splitter.addWidget(self.vram_plot)
        layout.addWidget(splitter)
        self.viz_tabs.addTab(tab, "Utilization")

    def setup_thermals_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.temp_plot = pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem(orientation='bottom')})
        self.style_plot(self.temp_plot, "Core Temp (°C)")
        
        self.power_plot = pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem(orientation='bottom')})
        self.style_plot(self.power_plot, "Power Draw (W)")
        
        splitter.addWidget(self.temp_plot); splitter.addWidget(self.power_plot)
        layout.addWidget(splitter)
        self.viz_tabs.addTab(tab, "Thermals & Power")

    def refresh_devices(self):
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for dev in self.db_mgr.get_devices():
            # Only show if reachable AND specifically flagged as having a GPU
            if self.db_mgr.device_status.get(dev['id']) == "Reachable" and dev.get('has_gpu', 0) == 1:
                self.device_combo.addItem(f"{dev['name']} ({dev['ip']})", dev)
        self.device_combo.blockSignals(False)
        self.reset_graphs()

    def reset_graphs(self):
        self.gpu_history.clear()
        self.util_plot.clear(); self.vram_plot.clear()
        self.temp_plot.clear(); self.power_plot.clear()
        self.gpu_curves = {'util': {}, 'vram': {}, 'temp': {}, 'power': {}}
        self.general_metrics.clear()
        self.table.setRowCount(0)

    def kill_gpu_process(self):
        dev = self.device_combo.currentData()
        row = self.table.currentRow()
        if not dev or row < 0: return
        pid = self.table.item(row, 0).text()
        
        reply = QMessageBox.question(self, "Confirm Kill", f"Kill process PID {pid} to free VRAM?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.w_kill = SSHWorker(dev, f"kill -9 {pid}", self.sec_mgr, use_sudo=True)
            self.w_kill.start() 

    def poll_metrics(self):
        dev = self.device_combo.currentData()
        if not dev or self.is_polling: return
        self.is_polling = True
        
        bash_payload = r"""
        export PATH=$PATH:/usr/bin:/bin:/usr/local/bin:/sbin:/usr/sbin
        echo "===GPU==="
        nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw --format=csv,noheader,nounits 2>/dev/null
        echo "===PRC==="
        for pid in $(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null); do
            if [ -n "$pid" ]; then
                user=$(ps -o ruser= -p $pid | tr -d ' ' | tail -1)
                proc=$(nvidia-smi --query-compute-apps=process_name --format=csv,noheader | grep -w "$pid" | head -1 | awk -F',' '{print $2}')
                vram=$(nvidia-smi --query-compute-apps=used_memory --format=csv,noheader | grep -w "$pid" | head -1 | awk -F',' '{print $3}')
                echo "$pid|$proc|$vram|$user"
            fi
        done
        """
        cmd = f"bash -c 'echo {base64.b64encode(bash_payload.encode()).decode()} | base64 -d | bash'"
        # --- UPDATED THREAD HANDLING ---
        if not hasattr(self, 'active_workers'): self.active_workers = []
        
        worker = SSHWorker(dev, cmd, self.sec_mgr)
        worker.finished.connect(self.update_ui)
        
        # Auto-cleanup
        worker.finished.connect(lambda r, w=worker: self.active_workers.remove(w) if w in self.active_workers else None)
        worker.error.connect(lambda e, w=worker: self.active_workers.remove(w) if w in self.active_workers else None)
        
        self.active_workers.append(worker)
        worker.start()

    def update_ui(self, result):
        self.is_polling = False
        if result['code'] != 0:
            self.status_lbl.setText("No Drivers / Error")
            return
            
        self.status_lbl.setText("Connected")
        parts = result['stdout'].split('===PRC===')
        if len(parts) < 2: return
        
        stats = parts[0].replace('===GPU===\n', '').strip()
        procs = parts[1].strip()
        
        now = time.time()
        overview = ""
        for line in stats.split('\n'):
            if not line.strip(): continue
            f = [x.strip() for x in line.split(',')]
            if len(f) >= 7:
                idx = int(f[0]); name = f[1]; util = float(f[2]) if f[2] != '[Not Supported]' else 0.0
                v_used = float(f[3]); v_tot = float(f[4]); temp = float(f[5])
                try: pwr = float(f[6])
                except: pwr = 0.0
                
                overview += f"[{idx}] {name} | Util: {util}% | VRAM: {v_used}/{v_tot}MB | Temp: {temp}C | Pwr: {pwr}W\n"
                
                if idx not in self.gpu_history:
                    self.gpu_history[idx] = {'ts': [], 'util': [], 'vram': [], 'temp': [], 'power': []}
                    c = self.colors[idx % len(self.colors)]
                    self.gpu_curves['util'][idx] = self.util_plot.plot(pen=pg.mkPen(c, width=2), name=f"GPU {idx}")
                    self.gpu_curves['vram'][idx] = self.vram_plot.plot(pen=pg.mkPen(c, width=2), name=f"GPU {idx}")
                    self.gpu_curves['temp'][idx] = self.temp_plot.plot(pen=pg.mkPen(c, width=2), name=f"GPU {idx}")
                    self.gpu_curves['power'][idx] = self.power_plot.plot(pen=pg.mkPen(c, width=2), name=f"GPU {idx}")
                    
                self.gpu_history[idx]['ts'].append(now)
                self.gpu_history[idx]['util'].append(util)
                self.gpu_history[idx]['vram'].append(v_used)
                self.gpu_history[idx]['temp'].append(temp)
                self.gpu_history[idx]['power'].append(pwr)
                
                for k in ['ts', 'util', 'vram', 'temp', 'power']:
                    if len(self.gpu_history[idx][k]) > 50: self.gpu_history[idx][k].pop(0)
                        
                self.gpu_curves['util'][idx].setData(self.gpu_history[idx]['ts'], self.gpu_history[idx]['util'])
                self.gpu_curves['vram'][idx].setData(self.gpu_history[idx]['ts'], self.gpu_history[idx]['vram'])
                self.gpu_curves['temp'][idx].setData(self.gpu_history[idx]['ts'], self.gpu_history[idx]['temp'])
                self.gpu_curves['power'][idx].setData(self.gpu_history[idx]['ts'], self.gpu_history[idx]['power'])
                
        self.general_metrics.setText(overview)
        
        self.table.setRowCount(0)
        for i, p in enumerate(procs.split('\n')):
            if not p: continue
            f = p.split('|')
            if len(f) >= 4:
                self.table.insertRow(i)
                for col in range(4): self.table.setItem(i, col, QTableWidgetItem(f[col].strip()))
