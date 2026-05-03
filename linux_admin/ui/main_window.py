from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QStackedWidget, QLabel
from PyQt6.QtCore import Qt, QSize
from linux_admin.ui.tabs.devices import DevicesTab
from linux_admin.ui.tabs.metrics import MetricsTab
from linux_admin.ui.tabs.packages import PackagesTab
from linux_admin.ui.tabs.services import ServicesTab
from linux_admin.ui.tabs.firewall import FirewallTab
from linux_admin.ui.tabs.docker import DockerTab
from linux_admin.ui.tabs.gpu import GPUTab
from linux_admin.ui.tabs.backups import BackupsTab

class MainWindow(QMainWindow):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        
        self.setWindowTitle("QtSSH Hub - Pro Server Management")
        self.resize(1400, 900)
        
        # Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # --- Sidebar ---
        sidebar_container = QWidget()
        sidebar_container.setFixedWidth(250)
        sidebar_container.setStyleSheet("background-color: #181825; border-right: 1px solid #313244;")
        sidebar_layout = QVBoxLayout(sidebar_container)
        sidebar_layout.setContentsMargins(10, 20, 10, 20)
        
        brand_lbl = QLabel("QtSSH Hub")
        brand_lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: #cba6f7; border: none; margin-bottom: 20px;")
        brand_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(brand_lbl)
        
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setIconSize(QSize(24, 24))
        
        # Removed Emojis for better compatibility
        menu_items = [
            "Devices & Groups",
            "Realtime Metrics",
            "Packages & Updates",
            "System Services",
            "Firewall Rules",
            "Docker Manager",
            "NVIDIA GPU",
            "Backups & Restore"
        ]
        self.sidebar.addItems(menu_items)
        sidebar_layout.addWidget(self.sidebar)
        main_layout.addWidget(sidebar_container)
        
        # --- Content Area ---
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)
        
        # Initialize Tabs
        self.devices_tab = DevicesTab(sec_mgr, db_mgr)
        self.metrics_tab = MetricsTab(sec_mgr, db_mgr)
        self.packages_tab = PackagesTab(sec_mgr, db_mgr)
        self.services_tab = ServicesTab(sec_mgr, db_mgr)
        self.firewall_tab = FirewallTab(sec_mgr, db_mgr)
        self.docker_tab = DockerTab(sec_mgr, db_mgr)
        self.gpu_tab = GPUTab(sec_mgr, db_mgr)
        self.backups_tab = BackupsTab(sec_mgr, db_mgr)
        
        self.stack.addWidget(self.devices_tab)
        self.stack.addWidget(self.metrics_tab)
        self.stack.addWidget(self.packages_tab)
        self.stack.addWidget(self.services_tab)
        self.stack.addWidget(self.firewall_tab)
        self.stack.addWidget(self.docker_tab)
        self.stack.addWidget(self.gpu_tab)
        self.stack.addWidget(self.backups_tab)
        
        # Connect Sidebar to Stack
        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.sidebar.setCurrentRow(0)

        # Signal Connections for auto-refresh
        self.devices_tab.devices_changed.connect(self.metrics_tab.refresh_devices)
        self.devices_tab.devices_changed.connect(self.packages_tab.refresh_devices)
        self.devices_tab.devices_changed.connect(self.services_tab.refresh_devices)
        self.devices_tab.devices_changed.connect(self.firewall_tab.refresh_devices)
        self.devices_tab.devices_changed.connect(self.docker_tab.refresh_devices)
        self.devices_tab.devices_changed.connect(self.gpu_tab.refresh_devices)
        self.devices_tab.devices_changed.connect(self.backups_tab.refresh_devices)
