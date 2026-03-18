from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit
from linux_admin.ui.workers import SSHWorker

class GPUTab(QWidget):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        
        layout = QVBoxLayout(self)
        
        header = QHBoxLayout()
        self.device_combo = QComboBox()
        self.btn_fetch = QPushButton("Poll NVIDIA GPU Metrics")
        self.btn_fetch.clicked.connect(self.fetch_gpu)
        
        header.addWidget(QLabel("Device:"))
        header.addWidget(self.device_combo)
        header.addWidget(self.btn_fetch)
        layout.addLayout(header)
        
        self.general_metrics = QTextEdit()
        self.general_metrics.setReadOnly(True)
        self.general_metrics.setMaximumHeight(80)
        layout.addWidget(QLabel("GPU Status (Name, Util, Mem, Temp):"))
        layout.addWidget(self.general_metrics)
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["PID", "Process Name", "VRAM Used", "System User"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(QLabel("Processes Using GPU:"))
        layout.addWidget(self.table)
        
        self.refresh_devices()

    def refresh_devices(self):
        self.device_combo.clear()
        for dev in self.db_mgr.get_devices():
            self.device_combo.addItem(f"{dev['name']} ({dev['ip']})", dev)

    def fetch_gpu(self):
        dev = self.device_combo.currentData()
        if not dev: return
        # Command gets GPU metrics, then gets Compute Apps, then finds user mapping using `ps`
        cmd = """
        nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader;
        echo "===PROCS===";
        for pid in $(nvidia-smi --query-compute-apps=pid --format=csv,noheader); do
            user=$(ps -o ruser= -p $pid);
            proc_name=$(nvidia-smi --query-compute-apps=process_name --format=csv,noheader | grep $pid | head -1 | awk -F',' '{print $2}');
            vram=$(nvidia-smi --query-compute-apps=used_memory --format=csv,noheader | grep $pid | head -1 | awk -F',' '{print $3}');
            echo "$pid|$proc_name|$vram|$user";
        done
        """
        self.worker = SSHWorker(dev, cmd, self.sec_mgr)
        self.worker.finished.connect(self.populate_gpu_data)
        self.worker.start()

    def populate_gpu_data(self, result):
        if result['code'] != 0:
            self.general_metrics.setText("nvidia-smi failed. Ensure NVIDIA drivers are installed.")
            return
            
        parts = result['stdout'].split('===PROCS===')
        self.general_metrics.setText(parts[0].strip())
        
        self.table.setRowCount(0)
        if len(parts) > 1:
            procs = parts[1].strip().split('\n')
            row = 0
            for p in procs:
                if not p: continue
                fields = p.split('|')
                if len(fields) >= 4:
                    self.table.insertRow(row)
                    for col in range(4):
                        self.table.setItem(row, col, QTableWidgetItem(fields[col].strip()))
                    row += 1
