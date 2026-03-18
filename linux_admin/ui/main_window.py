from PyQt6.QtWidgets import QMainWindow, QTabWidget, QVBoxLayout, QWidget
from linux_admin.ui.tabs.devices import DevicesTab
from linux_admin.ui.tabs.metrics import MetricsTab
from linux_admin.ui.tabs.packages import PackagesTab
from linux_admin.ui.tabs.services import ServicesTab
from linux_admin.ui.tabs.firewall import FirewallTab
from linux_admin.ui.tabs.docker import DockerTab
from linux_admin.ui.tabs.gpu import GPUTab

class MainWindow(QMainWindow):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        
        self.setWindowTitle("Linux System Administrator - Pro Dashboard")
        self.resize(1200, 800)
        
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        # Initialize Tabs
        self.devices_tab = DevicesTab(sec_mgr, db_mgr)
        self.metrics_tab = MetricsTab(sec_mgr, db_mgr)
        self.packages_tab = PackagesTab(sec_mgr, db_mgr)
        self.services_tab = ServicesTab(sec_mgr, db_mgr)
        self.firewall_tab = FirewallTab(sec_mgr, db_mgr)
        self.docker_tab = DockerTab(sec_mgr, db_mgr)
        self.gpu_tab = GPUTab(sec_mgr, db_mgr)
        
        self.tabs.addTab(self.devices_tab, "Devices & Groups")
        self.tabs.addTab(self.metrics_tab, "Realtime Metrics")
        self.tabs.addTab(self.packages_tab, "Packages (Ansible)")
        self.tabs.addTab(self.services_tab, "Services (Systemd)")
        self.tabs.addTab(self.firewall_tab, "Firewall")
        self.tabs.addTab(self.docker_tab, "Docker")
        self.tabs.addTab(self.gpu_tab, "NVIDIA GPU")

        # Connect signals so UI updates when devices change
        self.devices_tab.devices_changed.connect(self.metrics_tab.refresh_devices)
        self.devices_tab.devices_changed.connect(self.packages_tab.refresh_devices)
        self.devices_tab.devices_changed.connect(self.services_tab.refresh_devices)
        self.devices_tab.devices_changed.connect(self.firewall_tab.refresh_devices)
        self.devices_tab.devices_changed.connect(self.docker_tab.refresh_devices)
        self.devices_tab.devices_changed.connect(self.gpu_tab.refresh_devices)
