import base64
import time
import pyqtgraph as pg
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, 
                             QLabel, QTableWidget, QTableWidgetItem, QHeaderView, 
                             QTextEdit, QTabWidget, QSplitter, QPushButton, 
                             QMessageBox, QLineEdit, QDialog, QGroupBox)
from PyQt6.QtCore import QTimer, Qt
from linux_admin.ui.workers import SSHWorker

class GPUTab(QWidget):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        self.is_polling = False
        self.active_workers = []
        
        self.gpu_history = {} 
        self.gpu_curves = {'util': {}, 'vram': {}, 'temp': {}, 'power': {}}
        self.colors = ['#89b4fa', '#f38ba8', '#a6e3a1', '#f9e2af', '#cba6f7', '#fab387']
        self.current_gpu_procs = [] 
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        header = QHBoxLayout()
        title = QLabel("NVIDIA Datacenter GPU Dashboard")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #a6e3a1;")
        header.addWidget(title)
        header.addSpacing(30)
        
        header.addWidget(QLabel("Node:"))
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(200)
        self.device_combo.currentIndexChanged.connect(self.reset_graphs)
        header.addWidget(self.device_combo)
        
        self.driver_lbl = QLabel("Driver: --- | CUDA: ---")
        self.driver_lbl.setStyleSheet("font-weight: bold; color: #f9e2af; padding-left: 15px;")
        header.addWidget(self.driver_lbl)
        
        header.addStretch()
        self.status_lbl = QLabel("Status: Waiting...")
        self.status_lbl.setStyleSheet("font-weight: bold; color: #a6adc8; padding: 5px; background: #313244; border-radius: 5px;")
        header.addWidget(self.status_lbl)
        layout.addLayout(header)
        
        self.viz_tabs = QTabWidget()
        layout.addWidget(self.viz_tabs)
        
        self.setup_overview_tab()
        self.setup_users_tab()
        self.setup_utilization_tab()
        self.setup_thermals_tab()
        self.setup_advanced_tab()
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll_metrics)
        self.timer.start(4000) 
        self.refresh_devices()

    def style_plot(self, p, title):
        p.setTitle(title, color="#cdd6f4")
        if hasattr(p, 'setBackground'):
            p.setBackground('#181825')
        p.showGrid(x=True, y=True, alpha=0.2)
        p.getAxis('left').setPen('#a6adc8')
        p.getAxis('bottom').setPen('#a6adc8')
        p.getAxis('left').setTextPen('#cdd6f4')
        p.getAxis('bottom').setTextPen('#cdd6f4')
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
        
        # --- Process Controls ---
        proc_controls = QHBoxLayout()
        self.proc_search = QLineEdit()
        self.proc_search.setPlaceholderText("Search GPU processes by PID, User, or Command...")
        self.proc_search.textChanged.connect(self.filter_processes)
        
        self.btn_term = QPushButton("Term (15)")
        self.btn_term.clicked.connect(lambda: self.manage_gpu_process('term'))
        
        self.btn_kill = QPushButton("Force Kill (9)")
        self.btn_kill.setObjectName("DangerBtn")
        self.btn_kill.clicked.connect(lambda: self.manage_gpu_process('kill'))
        
        self.btn_inspect = QPushButton("Inspect Details")
        self.btn_inspect.setObjectName("PrimaryBtn")
        self.btn_inspect.clicked.connect(lambda: self.manage_gpu_process('inspect'))
        
        proc_controls.addWidget(self.proc_search)
        proc_controls.addWidget(self.btn_term)
        proc_controls.addWidget(self.btn_kill)
        proc_controls.addWidget(self.btn_inspect)
        layout.addLayout(proc_controls)
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["PID", "VRAM Used", "System User", "Full Command Line"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)
        
        self.viz_tabs.addTab(tab, "Overview & Processes")

    def setup_users_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Panel: Users Table
        left_grp = QGroupBox("Active GPU Users")
        left_lay = QVBoxLayout(left_grp)
        self.user_table = QTableWidget()
        self.user_table.setColumnCount(3)
        self.user_table.setHorizontalHeaderLabels(["User", "Total VRAM", "Process Count"])
        self.user_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.user_table.verticalHeader().setVisible(False)
        self.user_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.user_table.itemSelectionChanged.connect(self.on_gpu_user_selected)
        left_lay.addWidget(self.user_table)
        splitter.addWidget(left_grp)

        # Right Panel: User's Processes
        right_grp = QGroupBox("Selected User's Processes")
        right_lay = QVBoxLayout(right_grp)
        self.user_proc_table = QTableWidget()
        self.user_proc_table.setColumnCount(3)
        self.user_proc_table.setHorizontalHeaderLabels(["PID", "VRAM Used", "Command"])
        self.user_proc_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.user_proc_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.user_proc_table.verticalHeader().setVisible(False)
        self.user_proc_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        
        proc_btns = QHBoxLayout()
        
        self.btn_user_proc_inspect = QPushButton("Inspect Details")
        self.btn_user_proc_inspect.setObjectName("PrimaryBtn")
        self.btn_user_proc_inspect.clicked.connect(self.inspect_user_process)
        
        self.btn_user_proc_kill = QPushButton("Force Kill Selected Process")
        self.btn_user_proc_kill.setObjectName("DangerBtn")
        self.btn_user_proc_kill.clicked.connect(self.kill_user_process)
        
        proc_btns.addWidget(self.btn_user_proc_inspect)
        proc_btns.addWidget(self.btn_user_proc_kill)
        proc_btns.addStretch()
        
        right_lay.addWidget(self.user_proc_table)
        right_lay.addLayout(proc_btns)
        splitter.addWidget(right_grp)

        splitter.setSizes([450, 750])
        layout.addWidget(splitter)
        self.viz_tabs.addTab(tab, "User Analysis")

    def setup_utilization_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.util_plot = pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem(orientation='bottom')})
        
        self.style_plot(self.util_plot, "Compute Core Utilization (%)")
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

    def setup_advanced_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        grp = QGroupBox("Ubuntu Driver & Hardware Tools")
        grp_lay = QHBoxLayout(grp)
        
        self.btn_persist_on = QPushButton("Enable Persistence Mode")
        self.btn_persist_on.setToolTip("Keeps NVIDIA driver loaded to prevent spin-up lag on Ubuntu servers")
        self.btn_persist_on.clicked.connect(lambda: self.run_driver_cmd("nvidia-smi -pm 1"))
        
        self.btn_persist_off = QPushButton("Disable Persistence Mode")
        self.btn_persist_off.clicked.connect(lambda: self.run_driver_cmd("nvidia-smi -pm 0"))
        
        self.btn_reset_gpu = QPushButton("Soft Reset GPU (-r)")
        self.btn_reset_gpu.setObjectName("DangerBtn")
        self.btn_reset_gpu.setToolTip("Attempt to reset GPU state (requires no active compute processes)")
        self.btn_reset_gpu.clicked.connect(lambda: self.run_driver_cmd("nvidia-smi -r"))
        
        self.btn_deep_query = QPushButton("Full Topology & Details Query")
        self.btn_deep_query.setObjectName("PrimaryBtn")
        self.btn_deep_query.clicked.connect(lambda: self.run_driver_cmd("nvidia-smi -q"))
        
        grp_lay.addWidget(self.btn_persist_on)
        grp_lay.addWidget(self.btn_persist_off)
        grp_lay.addWidget(self.btn_reset_gpu)
        grp_lay.addWidget(self.btn_deep_query)
        layout.addWidget(grp)
        
        self.advanced_log = QTextEdit()
        self.advanced_log.setReadOnly(True)
        self.advanced_log.setStyleSheet("background-color: #11111b; font-family: monospace;")
        layout.addWidget(QLabel("Driver Command Output:"))
        layout.addWidget(self.advanced_log)
        
        self.viz_tabs.addTab(tab, "Driver Tools")

    def refresh_devices(self):
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for dev in self.db_mgr.get_devices():
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
        self.driver_lbl.setText("Driver: --- | CUDA: ---")
        if hasattr(self, 'user_table'):
            self.user_table.setRowCount(0)
            self.user_proc_table.setRowCount(0)

    def run_driver_cmd(self, cmd):
        dev = self.device_combo.currentData()
        if not dev: return
        self.advanced_log.setText(f"Executing: sudo {cmd} ...")
        worker = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        worker.finished.connect(lambda r: self.advanced_log.setText(f"STDOUT:\n{r['stdout']}\n\nSTDERR:\n{r['stderr']}"))
        self.active_workers.append(worker)
        worker.start()

    def filter_processes(self):
        search_term = self.proc_search.text().lower()
        for row in range(self.table.rowCount()):
            pid = self.table.item(row, 0).text().lower()
            user = self.table.item(row, 2).text().lower()
            cmd = self.table.item(row, 3).text().lower()
            
            if search_term in pid or search_term in user or search_term in cmd:
                self.table.setRowHidden(row, False)
            else:
                self.table.setRowHidden(row, True)

    def manage_gpu_process(self, action):
        dev = self.device_combo.currentData()
        row = self.table.currentRow()
        if not dev or row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a GPU process from the list.")
            return
            
        pid = self.table.item(row, 0).text()
        vram = self.table.item(row, 1).text()
        
        cmd = ""
        if action == "term":
            if QMessageBox.question(self, "Confirm Term", f"Send SIGTERM to PID {pid} to free {vram}?") == QMessageBox.StandardButton.Yes:
                cmd = f"kill -15 {pid}"
        elif action == "kill":
            if QMessageBox.question(self, "Confirm Kill", f"Force KILL PID {pid}? This will instantly free {vram} but may cause data loss.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                cmd = f"kill -9 {pid}"
        elif action == "inspect":
            self.status_lbl.setText("Inspecting PID...")
            bash_payload = f"""
            echo "=== GPU Process Details for PID {pid} ==="
            ps -p {pid} -o user,pid,ppid,state,pcpu,pmem,start,etime,args || echo "Process exited"
            echo -e "\\n=== Environment Variables (CUDA/GPU specific) ==="
            cat /proc/{pid}/environ 2>/dev/null | tr '\\0' '\\n' | grep -i -E 'CUDA|NVIDIA|GPU' || echo "None found or Access Denied"
            echo -e "\\n=== Active File Descriptors & Sockets ==="
            ls -l /proc/{pid}/fd 2>/dev/null | head -n 30 || echo "Access Denied"
            """
            b64_cmd = base64.b64encode(bash_payload.encode()).decode()
            cmd = f"bash -c 'echo {b64_cmd} | base64 -d | bash'"
            
        if cmd:
            worker = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
            if action == "inspect":
                worker.finished.connect(self.show_inspect_dialog)
            else:
                worker.finished.connect(lambda r: self.status_lbl.setText(f"Proc Action: {'Success' if r['code'] == 0 else 'Failed'}"))
            self.active_workers.append(worker)
            worker.start()

    def show_inspect_dialog(self, result):
        self.status_lbl.setText("Live")
        dlg = QDialog(self)
        dlg.setWindowTitle("GPU Process Deep Inspection")
        dlg.resize(900, 600)
        lay = QVBoxLayout(dlg)
        
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setStyleSheet("background-color: #11111b; font-family: monospace; color: #a6e3a1; font-size: 13px;")
        txt.setText(result['stdout'] if result['code'] == 0 else f"Error:\n{result['stderr']}\n\n{result['stdout']}")
        lay.addWidget(txt)
        
        btn = QPushButton("Close")
        btn.clicked.connect(dlg.accept)
        lay.addWidget(btn)
        dlg.exec()

    def inspect_user_process(self):
        dev = self.device_combo.currentData()
        row = self.user_proc_table.currentRow()
        if not dev or row < 0: 
            QMessageBox.warning(self, "No Selection", "Please select a process from the user's process list.")
            return
        
        pid = self.user_proc_table.item(row, 0).text()
        
        self.status_lbl.setText("Inspecting PID...")
        bash_payload = f"""
        echo "=== GPU Process Details for PID {pid} ==="
        ps -p {pid} -o user,pid,ppid,state,pcpu,pmem,start,etime,args || echo "Process exited"
        echo -e "\\n=== Environment Variables (CUDA/GPU specific) ==="
        cat /proc/{pid}/environ 2>/dev/null | tr '\\0' '\\n' | grep -i -E 'CUDA|NVIDIA|GPU' || echo "None found or Access Denied"
        echo -e "\\n=== Active File Descriptors & Sockets ==="
        ls -l /proc/{pid}/fd 2>/dev/null | head -n 30 || echo "Access Denied"
        """
        b64_cmd = base64.b64encode(bash_payload.encode()).decode()
        cmd = f"bash -c 'echo {b64_cmd} | base64 -d | bash'"
        
        worker = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        worker.finished.connect(self.show_inspect_dialog)
        self.active_workers.append(worker)
        worker.start()

    def kill_user_process(self):
        dev = self.device_combo.currentData()
        row = self.user_proc_table.currentRow()
        if not dev or row < 0: 
            QMessageBox.warning(self, "No Selection", "Please select a process from the user's process list.")
            return
        
        pid = self.user_proc_table.item(row, 0).text()
        vram = self.user_proc_table.item(row, 1).text()
        
        if QMessageBox.question(self, "Confirm Kill", f"Force KILL PID {pid}? This will instantly free {vram}.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            cmd = f"kill -9 {pid}"
            worker = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
            worker.finished.connect(lambda r: self.status_lbl.setText(f"User Proc Action: {'Success' if r['code'] == 0 else 'Failed'}"))
            self.active_workers.append(worker)
            worker.start()

    def on_gpu_user_selected(self):
        rows = self.user_table.selectedItems()
        if not rows:
            self.user_proc_table.setRowCount(0)
            return
        
        selected_user = self.user_table.item(rows[0].row(), 0).text()
        
        # Preserve selection
        selected_pid = None
        if self.user_proc_table.currentRow() >= 0:
            selected_pid = self.user_proc_table.item(self.user_proc_table.currentRow(), 0).text()

        self.user_proc_table.setRowCount(0)
        row_idx = 0
        for p in getattr(self, 'current_gpu_procs', []):
            if p['user'] == selected_user:
                self.user_proc_table.insertRow(row_idx)
                self.user_proc_table.setItem(row_idx, 0, QTableWidgetItem(p['pid']))
                self.user_proc_table.setItem(row_idx, 1, QTableWidgetItem(p['vram']))
                self.user_proc_table.setItem(row_idx, 2, QTableWidgetItem(p['cmd']))
                
                if p['pid'] == selected_pid:
                    self.user_proc_table.selectRow(row_idx)
                row_idx += 1

    def poll_metrics(self):
        dev = self.device_combo.currentData()
        if not dev or self.is_polling: return
        self.is_polling = True
        
        bash_payload = r"""
        export PATH=$PATH:/usr/bin:/bin:/usr/local/bin:/sbin:/usr/sbin
        echo "===SYS==="
        smi_out=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n 1)
        nvcc_out=$(nvcc --version 2>/dev/null | grep release | awk '{print $5}' | cut -d',' -f1)
        if [ -z "$nvcc_out" ]; then nvcc_out=$(nvidia-smi | grep "CUDA Version" | awk '{print $9}'); fi
        echo "Driver: ${smi_out:-Unknown} | CUDA: ${nvcc_out:-Unknown}"
        
        echo "===GPU==="
        nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw --format=csv,noheader,nounits 2>/dev/null
        
        echo "===PRC==="
        nvidia-smi | awk '/^\|.* [CG\+]+ .*MiB \|$/' | while read -r line; do
            pid=$(echo "$line" | grep -oE "[0-9]+ +[CG\+]+" | awk '{print $1}')
            vram=$(echo "$line" | grep -oE "[0-9]+ *MiB" | tr -d ' ')
            if [ -n "$pid" ]; then
                user=$(ps -o ruser= -p "$pid" | tr -d ' ' | tail -n 1)
                full_cmd=$(ps -p "$pid" -o args= 2>/dev/null | tail -n 1 || echo "Unknown/Exited")
                echo "$pid|$vram|$user|$full_cmd"
            fi
        done
        """
        cmd = f"bash -c 'echo {base64.b64encode(bash_payload.encode()).decode()} | base64 -d | bash'"
        
        worker = SSHWorker(dev, cmd, self.sec_mgr)
        worker.finished.connect(self.update_ui)
        worker.error.connect(lambda e: setattr(self, 'is_polling', False))
        
        worker.finished.connect(lambda r, w=worker: self.active_workers.remove(w) if w in self.active_workers else None)
        worker.error.connect(lambda e, w=worker: self.active_workers.remove(w) if w in self.active_workers else None)
        
        self.active_workers.append(worker)
        worker.start()

    def update_ui(self, result):
        self.is_polling = False
        if result['code'] != 0:
            self.status_lbl.setText("No Drivers / Error")
            self.status_lbl.setStyleSheet("color: #f38ba8; padding: 5px; background: #313244; border-radius: 5px;")
            return
            
        self.status_lbl.setText("Connected & Live")
        self.status_lbl.setStyleSheet("color: #a6e3a1; padding: 5px; background: #313244; border-radius: 5px;")
        
        stdout = result.get('stdout', '')
        
        try:
            parts = stdout.split('===')
            data_blocks = {}
            for i in range(1, len(parts), 2):
                if i+1 < len(parts):
                    key = parts[i].strip()
                    data_blocks[key] = parts[i+1].strip()
            
            if 'SYS' in data_blocks:
                self.driver_lbl.setText(data_blocks['SYS'])
            
            stats = data_blocks.get('GPU', '')
            procs = data_blocks.get('PRC', '')
            
            now = time.time()
            overview = ""
            for line in stats.split('\n'):
                if not line.strip(): continue
                f = [x.strip() for x in line.split(',')]
                if len(f) >= 7:
                    try: idx = int(f[0])
                    except ValueError: continue
                    
                    name = f[1]
                    try: util = float(f[2])
                    except ValueError: util = 0.0
                    try: v_used = float(f[3])
                    except ValueError: v_used = 0.0
                    try: v_tot = float(f[4])
                    except ValueError: v_tot = 0.0
                    try: temp = float(f[5])
                    except ValueError: temp = 0.0
                    try: pwr = float(f[6])
                    except ValueError: pwr = 0.0
                    
                    overview += f"[{idx}] {name} | Compute: {util}% | VRAM: {v_used}/{v_tot}MB | Temp: {temp}C | Pwr: {pwr}W\n"
                    
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
            
            # --- Update Processes & User Analysis ---
            selected_pid = None
            if self.table.currentRow() >= 0:
                selected_pid = self.table.item(self.table.currentRow(), 0).text()
                
            self.table.setRowCount(0)
            proc_lines = [p for p in procs.split('\n') if p.strip()]
            
            user_stats = {} 
            self.current_gpu_procs = []
            
            for i, p in enumerate(proc_lines):
                f = p.split('|', 3) 
                if len(f) >= 4:
                    pid, vram_str, user, cmd = f[0].strip(), f[1].strip(), f[2].strip(), f[3].strip()
                    
                    # 1. Update standard overview table
                    self.table.insertRow(i)
                    self.table.setItem(i, 0, QTableWidgetItem(pid))
                    self.table.setItem(i, 1, QTableWidgetItem(vram_str))
                    self.table.setItem(i, 2, QTableWidgetItem(user))
                    self.table.setItem(i, 3, QTableWidgetItem(cmd))
                    
                    if pid == selected_pid:
                        self.table.selectRow(i)
                        
                    # 2. Aggregate Data for User Analysis Tab
                    vram_val = 0
                    try:
                        vram_val = int(vram_str.replace('MiB', '').strip())
                    except:
                        pass
                        
                    if user not in user_stats:
                        user_stats[user] = {'vram': 0, 'count': 0}
                    user_stats[user]['vram'] += vram_val
                    user_stats[user]['count'] += 1
                    
                    self.current_gpu_procs.append({'pid': pid, 'vram': vram_str, 'user': user, 'cmd': cmd})
            
            self.filter_processes()
            
            # 3. Update the Users Table in the new tab
            if hasattr(self, 'user_table'):
                selected_user = None
                if self.user_table.currentRow() >= 0:
                    selected_user = self.user_table.item(self.user_table.currentRow(), 0).text()
                    
                self.user_table.setRowCount(0)
                row_idx = 0
                # Sort users by total VRAM used
                for user, stats in sorted(user_stats.items(), key=lambda item: item[1]['vram'], reverse=True):
                    self.user_table.insertRow(row_idx)
                    self.user_table.setItem(row_idx, 0, QTableWidgetItem(user))
                    self.user_table.setItem(row_idx, 1, QTableWidgetItem(f"{stats['vram']} MiB"))
                    self.user_table.setItem(row_idx, 2, QTableWidgetItem(str(stats['count'])))
                    
                    if user == selected_user:
                        self.user_table.selectRow(row_idx)
                    row_idx += 1
                    
                self.on_gpu_user_selected()
                
        except Exception as e:
            print(f"Error parsing GPU data: {e}")
