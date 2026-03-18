import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QSplitter
from PyQt6.QtCore import QTimer
from linux_admin.ui.workers import SSHWorker

class MetricsTab(QWidget):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        
        layout = QVBoxLayout(self)
        
        # Selector
        header = QHBoxLayout()
        header.addWidget(QLabel("Select Device:"))
        self.device_combo = QComboBox()
        self.device_combo.currentIndexChanged.connect(self.reset_graphs)
        header.addWidget(self.device_combo)
        layout.addLayout(header)
        
        # Plots
        splitter = QSplitter()
        
        self.cpu_plot = pg.PlotWidget(title="CPU Usage (%)")
        self.cpu_curve = self.cpu_plot.plot(pen='y')
        
        self.ram_plot = pg.PlotWidget(title="RAM Usage (MB)")
        self.ram_curve = self.ram_plot.plot(pen='c')

        self.disk_plot = pg.PlotWidget(title="Users Logged In") # Using as a text display widget placeholder conceptually
        
        splitter.addWidget(self.cpu_plot)
        splitter.addWidget(self.ram_plot)
        layout.addWidget(splitter)

        self.login_info = QLabel("Login Info: Waiting...")
        layout.addWidget(self.login_info)
        
        # Data arrays
        self.cpu_data = [0]*60
        self.ram_data = [0]*60
        
        # Poller
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll_metrics)
        self.timer.start(5000) # Poll every 5s
        
        self.refresh_devices()

    def refresh_devices(self):
        self.device_combo.clear()
        for dev in self.db_mgr.get_devices():
            self.device_combo.addItem(f"{dev['name']} ({dev['ip']})", dev)

    def reset_graphs(self):
        self.cpu_data = [0]*60
        self.ram_data = [0]*60
        self.cpu_curve.setData(self.cpu_data)
        self.ram_curve.setData(self.ram_data)

    def poll_metrics(self):
        dev = self.device_combo.currentData()
        if not dev: return
        
        # Command gets CPU usage, RAM, and last logged in users
        cmd = """
        top -bn1 | grep "Cpu(s)" | sed "s/.*, *\\([0-9.]*\\)%* id.*/\\1/" | awk '{print 100 - $1}';
        free -m | awk 'NR==2{print $3}';
        last -a | head -n 3
        """
        self.worker = SSHWorker(dev, cmd, self.sec_mgr)
        self.worker.finished.connect(self.update_ui)
        self.worker.start()

    def update_ui(self, result):
        if result['code'] == 0:
            parts = result['stdout'].strip().split('\n')
            if len(parts) >= 2:
                try:
                    cpu_val = float(parts[0])
                    ram_val = float(parts[1])
                    
                    self.cpu_data.pop(0)
                    self.cpu_data.append(cpu_val)
                    self.cpu_curve.setData(self.cpu_data)
                    
                    self.ram_data.pop(0)
                    self.ram_data.append(ram_val)
                    self.ram_curve.setData(self.ram_data)
                    
                    logins = "\n".join(parts[2:])
                    self.login_info.setText(f"Recent Logins:\n{logins}")
                except ValueError:
                    pass
