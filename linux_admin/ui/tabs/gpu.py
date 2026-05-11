import base64
import time
import datetime
import pyqtgraph as pg
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, 
                             QLabel, QTableWidget, QTableWidgetItem, QHeaderView, 
                             QTextEdit, QTabWidget, QSplitter, QPushButton, 
                             QMessageBox, QLineEdit, QDialog, QGroupBox, 
                             QDateEdit, QFileDialog)
from PyQt6.QtCore import QTimer, Qt, QDate
from linux_admin.ui.workers import SSHWorker

class GPUTab(QWidget):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        self.is_polling = False
        self.last_fetched_ts = 0
        self.active_workers = []
        self.static_gpu_info = {}
        
        self.gpu_history = {} 
        self.gpu_curves = {'util': {}, 'vram': {}, 'temp': {}, 'power': {}}
        self.colors = ['#89b4fa', '#f38ba8', '#a6e3a1', '#f9e2af', '#cba6f7', '#fab387', '#89dceb', '#f5c2e7']
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
        
        self.btn_deploy = QPushButton("Deploy GPU Telemetry")
        self.btn_deploy.setObjectName("PrimaryBtn")
        self.btn_deploy.clicked.connect(self.deploy_agent)
        header.addWidget(self.btn_deploy)
        
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
        self.setup_historical_tab()
        self.setup_utilization_tab()
        self.setup_thermals_tab()
        self.setup_advanced_tab()
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll_metrics)
        # UI polls every 10 seconds for maximum responsiveness.
        # Minimal overhead since the live log is strictly capped at 150 lines.
        self.timer.start(10000) 
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
        self.table.setHorizontalHeaderLabels(["PID", "VRAM Used", "System User", "Command Executable"])
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
        self.viz_tabs.addTab(tab, "Live User Analysis")

    def setup_historical_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        controls = QHBoxLayout()
        self.hist_timeframe = QComboBox()
        self.hist_timeframe.addItems(["Today", "This Week", "This Month", "All Time", "Custom Date"])
        self.hist_timeframe.currentTextChanged.connect(self.on_timeframe_changed)
        
        self.hist_date_picker = QDateEdit()
        self.hist_date_picker.setCalendarPopup(True)
        self.hist_date_picker.setDate(QDate.currentDate())
        self.hist_date_picker.setVisible(False)
        
        self.btn_calc_hist = QPushButton("Fetch & Plot Data")
        self.btn_calc_hist.setObjectName("PrimaryBtn")
        self.btn_calc_hist.clicked.connect(self.calculate_historical)
        
        self.btn_export_csv = QPushButton("Export CSV (Merged Sessions)")
        self.btn_export_csv.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold;")
        self.btn_export_csv.clicked.connect(self.export_csv)
        
        controls.addWidget(QLabel("Timeframe:"))
        controls.addWidget(self.hist_timeframe)
        controls.addWidget(self.hist_date_picker)
        controls.addWidget(self.btn_calc_hist)
        controls.addStretch()
        controls.addWidget(self.btn_export_csv)
        layout.addLayout(controls)
        
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        self.hist_table = QTableWidget()
        self.hist_table.setColumnCount(4)
        self.hist_table.setHorizontalHeaderLabels(["User", "Peak VRAM (MB)", "Avg VRAM (MB)", "Active Data Points"])
        self.hist_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.hist_table.verticalHeader().setVisible(False)
        self.hist_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        splitter.addWidget(self.hist_table)
        
        self.timeline_plot = pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem(orientation='bottom')})
        self.style_plot(self.timeline_plot, "User-Wise VRAM Usage Timeline (MB)")
        splitter.addWidget(self.timeline_plot)
        
        splitter.setSizes([200, 500])
        layout.addWidget(splitter)
        
        self.viz_tabs.addTab(tab, "Historical Usage & Timeline")

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
        self.btn_persist_on.clicked.connect(lambda: self.run_driver_cmd("nvidia-smi -pm 1"))
        
        self.btn_persist_off = QPushButton("Disable Persistence Mode")
        self.btn_persist_off.clicked.connect(lambda: self.run_driver_cmd("nvidia-smi -pm 0"))
        
        self.btn_reset_gpu = QPushButton("Soft Reset GPU (-r)")
        self.btn_reset_gpu.setObjectName("DangerBtn")
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
        self.util_plot.clear()
        self.vram_plot.clear()
        self.temp_plot.clear()
        self.power_plot.clear()
        if hasattr(self, 'timeline_plot'):
            self.timeline_plot.clear()
        self.gpu_curves = {'util': {}, 'vram': {}, 'temp': {}, 'power': {}}
        self.general_metrics.clear()
        self.last_fetched_ts = 0
        self.table.setRowCount(0)
        self.driver_lbl.setText("Driver: --- | CUDA: ---")
        if hasattr(self, 'user_table'):
            self.user_table.setRowCount(0)
            self.user_proc_table.setRowCount(0)
            
        # Instantly trigger a fast poll when changing tabs/devices so the user isn't stuck waiting
        QTimer.singleShot(100, self.poll_metrics)

    def on_timeframe_changed(self, text):
        self.hist_date_picker.setVisible(text == "Custom Date")

    def get_time_bounds(self):
        tf = self.hist_timeframe.currentText()
        end_str = "tomorrow 00:00:00" 
        target_files = []
        
        if tf == "Today":
            start_str = "today 00:00:00"
            d = datetime.date.today()
            target_files.append(f"/var/log/gpu_metrics_history_{d.strftime('%Y-%m-%d')}.log")
        elif tf == "This Week":
            start_str = "last sunday 00:00:00" 
            today = datetime.date.today()
            for i in range(8):
                d = today - datetime.timedelta(days=i)
                target_files.append(f"/var/log/gpu_metrics_history_{d.strftime('%Y-%m-%d')}.log")
        elif tf == "This Month":
            start_str = "1 month ago"
            today = datetime.date.today()
            for i in range(32):
                d = today - datetime.timedelta(days=i)
                target_files.append(f"/var/log/gpu_metrics_history_{d.strftime('%Y-%m-%d')}.log")
        elif tf == "Custom Date":
            d_str = self.hist_date_picker.date().toString("yyyy-MM-dd")
            start_str = f"{d_str} 00:00:00"
            end_str = f"{d_str} 23:59:59"
            target_files.append(f"/var/log/gpu_metrics_history_{d_str}.log")
        else: 
            start_str = "1970-01-01"
            target_files = ["/var/log/gpu_metrics_history_*.log"]
            
        files_str = " ".join(target_files)
        return start_str, end_str, files_str

    def deploy_agent(self):
        dev = self.device_combo.currentData()
        if not dev: return
        self.btn_deploy.setEnabled(False)
        self.status_lbl.setText("Deploying...")

        bash_payload = r"""set -e
cat << 'EOF' > /usr/local/bin/gpu_admin_agent.sh
#!/bin/bash
LIVE_LOG="/var/log/gpu_metrics_live.log"
LAST_HIST=0

while true; do
    TS=$(date +%s)
    TODAY=$(date +%F)
    HIST_LOG="/var/log/gpu_metrics_history_${TODAY}.log"
    
    GPU_STATS=$(nvidia-smi --query-gpu=index,utilization.gpu,memory.used,temperature.gpu,power.draw --format=csv,noheader,nounits 2>/dev/null | tr '\n' ';' | sed 's/;$//')

    PRC_STATS=$(nvidia-smi | awk '/^\|.* [CG\+]+ .*MiB \|$/' | while read -r line; do
        pid=$(echo "$line" | grep -oE "[0-9]+ +[CG\+]+" | awk '{print $1}')
        vram=$(echo "$line" | grep -oE "[0-9]+ *MiB" | tr -d ' MiB')
        if [ -n "$pid" ]; then
            user=$(ps -o ruser= -p "$pid" | tr -d ' ' | tail -n 1)
            comm=$(ps -p "$pid" -o comm= 2>/dev/null | tail -n 1 || echo "Unknown")
            safe_cmd=$(echo "$comm" | tr -d ';|,')
            echo "${pid},${vram},${user},${safe_cmd}"
        fi
    done | tr '\n' ';' | sed 's/;$//')

    LINE="$TS|$GPU_STATS|$PRC_STATS"

    # 1. LIVE LOG
    echo "$LINE" >> "$LIVE_LOG"
    tail -n 150 "$LIVE_LOG" > "$LIVE_LOG.tmp" && mv "$LIVE_LOG.tmp" "$LIVE_LOG"

    # 2. HISTORY LOG (Daily File)
    if [ -z "$LAST_HIST" ] || [ $((TS - LAST_HIST)) -ge 60 ]; then
        echo "$LINE" >> "$HIST_LOG"
        LAST_HIST=$TS
        
        # Auto-Cleanup: Delete daily logs older than 90 days to save disk space
        find /var/log/ -name "gpu_metrics_history_*.log" -type f -mtime +90 -delete 2>/dev/null || true
    fi

    # Agent runs efficiently every 60s
    sleep 60
done
EOF

chmod +x /usr/local/bin/gpu_admin_agent.sh
cat << 'EOF' > /etc/systemd/system/gpu_admin_agent.service
[Unit]
Description=QtSSH Hub GPU Telemetry
After=network.target

[Service]
ExecStart=/usr/local/bin/gpu_admin_agent.sh
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload && systemctl enable --now gpu_admin_agent.service
"""
        cmd = f"bash -c 'echo {base64.b64encode(bash_payload.encode()).decode()} | base64 -d | bash'"
        worker = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        worker.finished.connect(lambda r: self.btn_deploy.setEnabled(True))
        self.active_workers.append(worker)
        worker.start()

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

    def calculate_historical(self):
        dev = self.device_combo.currentData()
        if not dev: return
        self.btn_calc_hist.setEnabled(False)
        self.btn_calc_hist.setText("Calculating...")
        
        start_str, end_str, files_str = self.get_time_bounds()

        bash_payload = f"""
        START_TS=$(date -d '{start_str}' +%s 2>/dev/null || echo 0)
        END_TS=$(date -d '{end_str}' +%s 2>/dev/null || echo 9999999999)
        
        cat {files_str} 2>/dev/null | awk -F'|' -v start="$START_TS" -v end="$END_TS" '
        $1 >= start && $1 <= end {{
            ts = $1
            split($3, procs, ";")
            delete current_vram
            for (i in procs) {{
                if (procs[i] == "") continue
                split(procs[i], p_info, ",")
                vram = p_info[2] + 0
                user = p_info[3]
                if (user != "") {{
                    current_vram[user] += vram
                }}
            }}
            
            bucket = int(ts / 60) * 60
            for (u in current_vram) {{
                if (current_vram[u] > bucket_max[bucket SUBSEP u]) {{
                    bucket_max[bucket SUBSEP u] = current_vram[u]
                }}
                
                if (!seen[ts SUBSEP u]) {{
                    user_total_vram[u] += current_vram[u]
                    user_samples[u]++
                    if (current_vram[u] > user_peak[u]) {{ user_peak[u] = current_vram[u] }}
                    seen[ts SUBSEP u] = 1
                }}
            }}
        }}
        END {{
            print "===SUMMARY==="
            for (u in user_samples) {{
                avg = user_total_vram[u] / user_samples[u]
                printf "%s|%d|%d|%d\\n", u, user_peak[u], avg, user_samples[u]
            }}
            print "===TIMESERIES==="
            for (b_u in bucket_max) {{
                split(b_u, arr, SUBSEP)
                printf "%s|%s|%d\\n", arr[1], arr[2], bucket_max[b_u]
            }}
        }}' || echo "ERROR"
        """
        cmd = f"bash -c 'echo {base64.b64encode(bash_payload.encode()).decode()} | base64 -d | bash'"
        worker = SSHWorker(dev, cmd, self.sec_mgr)
        worker.finished.connect(self.populate_historical)
        self.active_workers.append(worker)
        worker.start()

    def populate_historical(self, result):
        self.btn_calc_hist.setEnabled(True)
        self.btn_calc_hist.setText("Fetch & Plot Data")
        self.hist_table.setRowCount(0)
        self.timeline_plot.clear()
        
        if result['code'] == 0 and "ERROR" not in result['stdout']:
            parts = result['stdout'].split('===SUMMARY===')
            if len(parts) > 1:
                sub_parts = parts[1].split('===TIMESERIES===')
                summary_lines = sub_parts[0].strip().split('\n')
                timeseries_lines = sub_parts[1].strip().split('\n') if len(sub_parts) > 1 else []
                
                row = 0
                for line in summary_lines:
                    if not line: continue
                    fields = line.split('|')
                    if len(fields) == 4:
                        self.hist_table.insertRow(row)
                        self.hist_table.setItem(row, 0, QTableWidgetItem(fields[0]))
                        self.hist_table.setItem(row, 1, QTableWidgetItem(fields[1]))
                        self.hist_table.setItem(row, 2, QTableWidgetItem(fields[2]))
                        self.hist_table.setItem(row, 3, QTableWidgetItem(fields[3]))
                        row += 1

                user_ts_data = {}
                for line in timeseries_lines:
                    if not line: continue
                    ts_str, user, vram_str = line.split('|')
                    try:
                        ts = int(ts_str)
                        vram = int(vram_str)
                        if user not in user_ts_data:
                            user_ts_data[user] = {'ts': [], 'vram': []}
                        user_ts_data[user]['ts'].append(ts)
                        user_ts_data[user]['vram'].append(vram)
                    except: pass
                
                for i, (user, data) in enumerate(user_ts_data.items()):
                    sorted_pairs = sorted(zip(data['ts'], data['vram']))
                    ts_sorted = []
                    vram_sorted = []
                    last_ts = None
                    
                    for ts, vram in sorted_pairs:
                        if last_ts is not None and (ts - last_ts) > 180:
                            ts_sorted.append(last_ts + 60)
                            vram_sorted.append(0)
                            ts_sorted.append(ts - 60)
                            vram_sorted.append(0)
                            
                        ts_sorted.append(ts)
                        vram_sorted.append(vram)
                        last_ts = ts
                        
                    if last_ts is not None:
                        ts_sorted.append(last_ts + 60)
                        vram_sorted.append(0)
                        
                    c = self.colors[i % len(self.colors)]
                    self.timeline_plot.plot(ts_sorted, vram_sorted, 
                                            pen=pg.mkPen(c, width=2), 
                                            fillLevel=0, 
                                            brush=pg.mkBrush(c+'60'), 
                                            name=user)

    def export_csv(self):
        dev = self.device_combo.currentData()
        if not dev: 
            QMessageBox.warning(self, "No Device", "Please select a target device first.")
            return
            
        start_str, end_str, files_str = self.get_time_bounds()

        bash_payload = f"""
        START_TS=$(date -d '{start_str}' +%s 2>/dev/null || echo 0)
        END_TS=$(date -d '{end_str}' +%s 2>/dev/null || echo 9999999999)
        
        cat {files_str} 2>/dev/null | awk -F'|' -v start="$START_TS" -v end="$END_TS" '
        $1 >= start && $1 <= end {{
            ts = $1
            split($3, procs, ";")
            delete current_vram
            for (i in procs) {{
                if (procs[i] == "") continue
                split(procs[i], p_info, ",")
                vram = p_info[2] + 0
                user = p_info[3]
                if (user != "") {{
                    current_vram[user] += vram
                }}
            }}
            
            bucket = int(ts / 300) * 300
            for (u in current_vram) {{
                if (!seen[ts SUBSEP u]) {{
                    bucket_sum[bucket SUBSEP u] += current_vram[u]
                    bucket_count[bucket SUBSEP u]++
                    seen[ts SUBSEP u] = 1
                }}
            }}
        }}
        END {{
            for (b_u in bucket_sum) {{
                split(b_u, arr, SUBSEP)
                bucket = arr[1]
                user = arr[2]
                avg_vram = int(bucket_sum[b_u] / bucket_count[b_u])
                printf "%s,%s,%d\\n", bucket, user, avg_vram
            }}
        }}' || echo "ERROR"
        """
        cmd = f"bash -c 'echo {base64.b64encode(bash_payload.encode()).decode()} | base64 -d | bash'"
        
        self.btn_export_csv.setEnabled(False)
        self.btn_export_csv.setText("Exporting...")
        
        worker = SSHWorker(dev, cmd, self.sec_mgr)
        worker.finished.connect(self.on_csv_ready)
        self.active_workers.append(worker)
        worker.start()

    def on_csv_ready(self, result):
        self.btn_export_csv.setEnabled(True)
        self.btn_export_csv.setText("Export CSV (Merged Sessions)")
        
        if result['code'] != 0 or "ERROR" in result['stdout']:
            QMessageBox.critical(self, "Export Failed", f"Could not generate CSV data.\n{result['stderr']}")
            return
            
        lines = result['stdout'].strip().split('\n')
        
        parsed_data = []
        for line in lines:
            if not line: continue
            parts = line.split(',')
            if len(parts) == 3:
                try:
                    ts = int(parts[0])
                    user = parts[1]
                    vram = int(parts[2])
                    parsed_data.append((ts, user, vram))
                except Exception: pass
                
        parsed_data.sort(key=lambda x: x[0])
        
        user_blocks = {}
        for ts, user, vram in parsed_data:
            if user not in user_blocks:
                user_blocks[user] = []
                
            blocks = user_blocks[user]
            if not blocks:
                blocks.append({'start_ts': ts, 'end_ts': ts + 300, 'vrams': [vram]})
            else:
                last_block = blocks[-1]
                if ts <= last_block['end_ts']:
                    last_block['end_ts'] = max(last_block['end_ts'], ts + 300)
                    last_block['vrams'].append(vram)
                else:
                    blocks.append({'start_ts': ts, 'end_ts': ts + 300, 'vrams': [vram]})

        final_rows = []
        for user, blocks in user_blocks.items():
            for b in blocks:
                avg_vram = int(sum(b['vrams']) / len(b['vrams']))
                final_rows.append((user, b['start_ts'], b['end_ts'], avg_vram))
                
        final_rows.sort(key=lambda x: x[1])
        
        csv_lines = ["Username,Start Time,End Time,Total Time,Average VRAM (MB)"]
        for user, start_ts, end_ts, vram in final_rows:
            start_time_str = datetime.datetime.fromtimestamp(start_ts).strftime('%Y-%m-%d %H:%M:%S')
            end_time_str = datetime.datetime.fromtimestamp(end_ts).strftime('%Y-%m-%d %H:%M:%S')
            
            total_seconds = end_ts - start_ts
            total_time_str = str(datetime.timedelta(seconds=total_seconds))
            
            csv_lines.append(f"{user},{start_time_str},{end_time_str},{total_time_str},{vram}")
                
        csv_data = "\n".join(csv_lines)
        
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Export Data", "gpu_usage_merged_sessions.csv", "CSV Files (*.csv)")
        if file_path:
            try:
                with open(file_path, 'w') as f:
                    f.write(csv_data)
                QMessageBox.information(self, "Success", f"Merged Sessions GPU Usage exported successfully to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "File Error", f"Failed to save file:\n{str(e)}")

    def poll_metrics(self):
        dev = self.device_combo.currentData()
        if not dev or self.is_polling: return
        self.is_polling = True
        
        bash_payload = f"""
        export PATH=$PATH:/usr/bin:/bin:/usr/local/bin:/sbin:/usr/sbin
        if [ ! -f /var/log/gpu_metrics_live.log ]; then echo "MISSING"; exit 0; fi
        
        echo "===SYS==="
        smi_out=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n 1)
        nvcc_out=$(nvcc --version 2>/dev/null | grep release | awk '{{print $5}}' | cut -d',' -f1)
        if [ -z "$nvcc_out" ]; then nvcc_out=$(nvidia-smi | grep "CUDA Version" | awk '{{print $9}}'); fi
        echo "Driver: ${{smi_out:-Unknown}} | CUDA: ${{nvcc_out:-Unknown}}"
        
        echo "===STATIC==="
        nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader,nounits 2>/dev/null
        
        echo "DATA"
        awk -F'|' -v ts="{self.last_fetched_ts}" '($1+0) > (ts+0)' /var/log/gpu_metrics_live.log 2>/dev/null || true
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
            return
            
        stdout = result.get('stdout', '')
        if "MISSING" in stdout:
            self.status_lbl.setText("Agent Not Running")
            self.status_lbl.setStyleSheet("color: #f38ba8; padding: 5px; background: #313244; border-radius: 5px;")
            return
            
        self.status_lbl.setText("Connected & Live")
        self.status_lbl.setStyleSheet("color: #a6e3a1; padding: 5px; background: #313244; border-radius: 5px;")
        
        try:
            # Re-engineered parsing so that random blank lines or carriage returns never break the UI
            if "===SYS===" in stdout:
                sys_part_raw = stdout.split("===SYS===")[1]
                sys_parts = sys_part_raw.split("===STATIC===")
                self.driver_lbl.setText(sys_parts[0].strip())
                
                static_str = sys_parts[1]
                static_parts = static_str.split("DATA")
                static_lines = static_parts[0].strip().split('\n')
                
                data_lines_raw = static_parts[1].strip() if len(static_parts) > 1 else ""
                data_lines = data_lines_raw.split('\n') if data_lines_raw else []
                
                for line in static_lines:
                    if not line: continue
                    fields = [x.strip() for x in line.split(',')]
                    if len(fields) >= 3:
                        try:
                            idx = int(fields[0])
                            self.static_gpu_info[idx] = {'name': fields[1], 'total': fields[2]}
                        except: pass
            else:
                return

            latest_gpu_str = ""
            latest_procs_str = ""
            
            for line in data_lines:
                if not line or '|' not in line: continue
                fields = line.split('|')
                if len(fields) < 2: continue
                
                ts = int(fields[0])
                self.last_fetched_ts = ts
                
                latest_gpu_str = fields[1]
                latest_procs_str = fields[2] if len(fields) >= 3 else ""
                
                gpus = latest_gpu_str.split(';')
                for g in gpus:
                    if not g: continue
                    f = [x.strip() for x in g.split(',')]
                    if len(f) >= 5:
                        try: idx = int(f[0])
                        except ValueError: continue
                        
                        try: util = float(f[1])
                        except ValueError: util = 0.0
                        try: v_used = float(f[2])
                        except ValueError: v_used = 0.0
                        try: temp = float(f[3])
                        except ValueError: temp = 0.0
                        try: pwr = float(f[4])
                        except ValueError: pwr = 0.0
                        
                        if idx not in self.gpu_history:
                            self.gpu_history[idx] = {'ts': [], 'util': [], 'vram': [], 'temp': [], 'power': []}
                            c = self.colors[idx % len(self.colors)]
                            self.gpu_curves['util'][idx] = self.util_plot.plot(pen=pg.mkPen(c, width=2), name=f"GPU {idx}")
                            self.gpu_curves['vram'][idx] = self.vram_plot.plot(pen=pg.mkPen(c, width=2), name=f"GPU {idx}")
                            self.gpu_curves['temp'][idx] = self.temp_plot.plot(pen=pg.mkPen(c, width=2), name=f"GPU {idx}")
                            self.gpu_curves['power'][idx] = self.power_plot.plot(pen=pg.mkPen(c, width=2), name=f"GPU {idx}")
                            
                        self.gpu_history[idx]['ts'].append(ts)
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
            
            if not latest_gpu_str:
                return

            overview = ""
            for g in latest_gpu_str.split(';'):
                if not g: continue
                f = [x.strip() for x in g.split(',')]
                if len(f) >= 5:
                    try: idx = int(f[0])
                    except ValueError: continue
                    util, v_used, temp, pwr = f[1], f[2], f[3], f[4]
                    static = self.static_gpu_info.get(idx, {'name': 'Unknown', 'total': '0'})
                    name = static['name']
                    v_tot = static['total']
                    overview += f"[{idx}] {name} | Compute: {util}% | VRAM: {v_used}/{v_tot}MB | Temp: {temp}C | Pwr: {pwr}W\n"
            self.general_metrics.setText(overview)
            
            selected_pid = None
            if self.table.currentRow() >= 0:
                selected_pid = self.table.item(self.table.currentRow(), 0).text()
                
            self.table.setRowCount(0)
            proc_lines = latest_procs_str.split(';')
            
            user_stats = {} 
            self.current_gpu_procs = []
            
            row_i = 0
            for p in proc_lines:
                if not p: continue
                f = p.split(',') 
                if len(f) >= 4:
                    pid, vram_val, user, cmd = f[0].strip(), f[1].strip(), f[2].strip(), f[3].strip()
                    vram_str = f"{vram_val} MiB"
                    
                    self.table.insertRow(row_i)
                    self.table.setItem(row_i, 0, QTableWidgetItem(pid))
                    self.table.setItem(row_i, 1, QTableWidgetItem(vram_str))
                    self.table.setItem(row_i, 2, QTableWidgetItem(user))
                    self.table.setItem(row_i, 3, QTableWidgetItem(cmd))
                    
                    if pid == selected_pid:
                        self.table.selectRow(row_i)
                    row_i += 1
                        
                    v = 0
                    try: v = int(vram_val)
                    except ValueError: pass
                        
                    if user not in user_stats:
                        user_stats[user] = {'vram': 0, 'count': 0}
                    user_stats[user]['vram'] += v
                    user_stats[user]['count'] += 1
                    
                    self.current_gpu_procs.append({'pid': pid, 'vram': vram_str, 'user': user, 'cmd': cmd})
            
            self.filter_processes()
            
            if hasattr(self, 'user_table'):
                selected_user = None
                if self.user_table.currentRow() >= 0:
                    selected_user = self.user_table.item(self.user_table.currentRow(), 0).text()
                    
                self.user_table.setRowCount(0)
                row_idx = 0
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
