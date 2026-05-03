import base64
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, 
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, 
                             QGroupBox, QFormLayout, QLineEdit, QMessageBox, QTextEdit, QSplitter)
from PyQt6.QtCore import Qt
from linux_admin.ui.workers import SSHWorker

class BackupsTab(QWidget):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        title = QLabel("Disaster Recovery & Automated Backups")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)
        
        header = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.currentIndexChanged.connect(self.fetch_existing_jobs)
        self.btn_refresh_jobs = QPushButton("Refresh Device Jobs")
        self.btn_refresh_jobs.clicked.connect(self.fetch_existing_jobs)
        
        header.addWidget(QLabel("Select Node:"))
        header.addWidget(self.device_combo)
        header.addWidget(self.btn_refresh_jobs)
        header.addStretch()
        layout.addLayout(header)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # --- 1. Setup New Backup Job ---
        setup_group = QGroupBox("Create New Backup Policy")
        setup_layout = QFormLayout(setup_group)
        
        self.job_name_in = QLineEdit()
        self.job_name_in.setPlaceholderText("e.g., website_data (No spaces)")
        self.src_in = QLineEdit()
        self.src_in.setPlaceholderText("e.g., /var/www/html")
        self.dest_in = QLineEdit()
        self.dest_in.setPlaceholderText("e.g., /mnt/backups/website")
        
        self.schedule_combo = QComboBox()
        self.schedule_combo.addItem("Hourly", "*-*-* *:00:00")
        self.schedule_combo.addItem("Daily (Midnight)", "*-*-* 00:00:00")
        self.schedule_combo.addItem("Weekly (Sunday)", "Sun *-*-* 00:00:00")
        
        self.btn_deploy = QPushButton("Deploy Backup Service")
        self.btn_deploy.setObjectName("PrimaryBtn")
        self.btn_deploy.clicked.connect(self.deploy_backup_job)
        
        setup_layout.addRow("Job Alias:", self.job_name_in)
        setup_layout.addRow("Source Dir:", self.src_in)
        setup_layout.addRow("Dest Dir:", self.dest_in)
        setup_layout.addRow("Schedule:", self.schedule_combo)
        setup_layout.addRow(self.btn_deploy)
        
        self.output_log = QTextEdit()
        self.output_log.setReadOnly(True)
        self.output_log.setStyleSheet("background-color: #11111b; font-family: monospace;")
        setup_layout.addRow("System Log:", self.output_log)
        splitter.addWidget(setup_group)
        
        # --- 2. Manage Existing Backups ---
        manage_group = QGroupBox("Restore & Management")
        manage_layout = QVBoxLayout(manage_group)
        
        job_select_layout = QHBoxLayout()
        self.job_combo = QComboBox()
        self.btn_load_backups = QPushButton("List Versions")
        self.btn_load_backups.clicked.connect(self.list_backups)
        self.btn_run_now = QPushButton("Trigger Now")
        self.btn_run_now.clicked.connect(self.trigger_manual_backup)
        self.btn_view_logs = QPushButton("View Run Logs")
        self.btn_view_logs.clicked.connect(self.view_job_logs)
        
        job_select_layout.addWidget(self.job_combo)
        job_select_layout.addWidget(self.btn_load_backups)
        job_select_layout.addWidget(self.btn_run_now)
        job_select_layout.addWidget(self.btn_view_logs)
        manage_layout.addLayout(job_select_layout)
        
        self.table = QTableWidget()
        self.table.setColumnCount(1)
        self.table.setHorizontalHeaderLabels(["Available Snapshot Timestamps"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        manage_layout.addWidget(self.table)
        
        self.btn_restore = QPushButton("Restore Selected Version (Safe Restore)")
        self.btn_restore.setObjectName("DangerBtn")
        self.btn_restore.clicked.connect(self.restore_backup)
        manage_layout.addWidget(self.btn_restore)
        
        splitter.addWidget(manage_group)
        self.refresh_devices()

    def refresh_devices(self):
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for dev in self.db_mgr.get_devices():
            if self.db_mgr.device_status.get(dev['id']) == "Reachable":
                self.device_combo.addItem(f"{dev['name']} ({dev['ip']})", dev)
        self.device_combo.blockSignals(False)
        self.fetch_existing_jobs()

    def log(self, message):
        self.output_log.append(message)

    def fetch_existing_jobs(self):
        dev = self.device_combo.currentData()
        if not dev: return
        self.job_combo.clear()
        script = "ls /usr/local/bin/*_adminbackup.sh 2>/dev/null | awk -F'/' '{print $NF}' | sed 's/_adminbackup.sh//'"
        cmd = f"bash -c 'echo {base64.b64encode(script.encode()).decode()} | base64 -d | bash'"
        self.worker_fetch = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_fetch.finished.connect(self.populate_jobs)
        self.worker_fetch.start()

    def populate_jobs(self, result):
        if result['code'] == 0 and result['stdout'].strip():
            self.job_combo.addItems(result['stdout'].strip().split('\n'))
        else:
            self.job_combo.addItem("No policies found")

    def deploy_backup_job(self):
        dev = self.device_combo.currentData()
        job = self.job_name_in.text().strip()
        src = self.src_in.text().strip()
        dest = self.dest_in.text().strip()
        schedule = self.schedule_combo.currentData()
        if not dev or not job or not src or not dest or ' ' in job: return

        self.btn_deploy.setEnabled(False)
        self.log(f"Deploying Backup Policy '{job}' to {dev['name']}...")

        bash_payload = f"""set -e
command -v rsync >/dev/null 2>&1 || {{ apt-get update && apt-get install -y rsync || yum install -y rsync; }}
mkdir -p "{dest}"
cat << 'EOF' > /usr/local/bin/{job}_adminbackup.sh
#!/bin/bash
SRC="{src}"
DEST="{dest}"
mkdir -p "$DEST"
LATEST=$(ls -td "$DEST"/*/ 2>/dev/null | head -1)
NOW=$(date +"%Y-%m-%d_%H-%M-%S")
if [ -z "$LATEST" ]; then
    rsync -a --delete "$SRC/" "$DEST/$NOW/"
else
    rsync -a --delete --link-dest="$LATEST" "$SRC/" "$DEST/$NOW/"
fi
EOF
chmod +x /usr/local/bin/{job}_adminbackup.sh

cat << 'EOF' > /etc/systemd/system/{job}_adminbackup.service
[Unit]
Description=Automated Backup for {job}
[Service]
Type=oneshot
ExecStart=/usr/local/bin/{job}_adminbackup.sh
EOF

cat << 'EOF' > /etc/systemd/system/{job}_adminbackup.timer
[Unit]
Description=Timer for Backup {job}
[Timer]
OnCalendar={schedule}
Persistent=true
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload && systemctl enable --now {job}_adminbackup.timer
echo "Successfully deployed and enabled timer."
"""
        cmd = f"bash -c 'echo {base64.b64encode(bash_payload.encode()).decode()} | base64 -d | bash'"
        self.worker_deploy = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_deploy.finished.connect(self.on_deploy_finished)
        self.worker_deploy.start()

    def on_deploy_finished(self, result):
        self.btn_deploy.setEnabled(True)
        self.log(result['stdout'] if result['code']==0 else f"Error: {result['stderr']}")
        self.fetch_existing_jobs()

    def view_job_logs(self):
        dev = self.device_combo.currentData()
        job = self.job_combo.currentText()
        if not dev or "No policies" in job or not job: return
        self.log(f"Fetching logs for backup job '{job}'...")
        cmd = f"journalctl -u {job}_adminbackup.service -n 50 --no-pager"
        self.w_log = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.w_log.finished.connect(lambda r: self.log(r['stdout'] or "No recent logs."))
        self.w_log.start()

    def trigger_manual_backup(self):
        dev = self.device_combo.currentData()
        job = self.job_combo.currentText()
        if not dev or "No policies" in job or not job: return
        self.log(f"Triggering backup '{job}'...")
        cmd = f"systemctl start {job}_adminbackup.service"
        self.worker_trigger = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_trigger.finished.connect(lambda r: self.log("Completed!" if r['code']==0 else f"Fail: {r['stderr']}"))
        self.worker_trigger.start()

    def list_backups(self):
        dev = self.device_combo.currentData()
        job = self.job_combo.currentText()
        if not dev or "No policies" in job or not job: return
        script = f"SCRIPT=\"/usr/local/bin/{job}_adminbackup.sh\"; if [ -f \"$SCRIPT\" ]; then DEST=$(grep '^DEST=' \"$SCRIPT\" | cut -d'\"' -f2); ls -1 \"$DEST\"; fi"
        cmd = f"bash -c 'echo {base64.b64encode(script.encode()).decode()} | base64 -d | bash'"
        self.worker_list = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_list.finished.connect(self.populate_backups)
        self.worker_list.start()

    def populate_backups(self, result):
        self.table.setRowCount(0)
        if result['code'] == 0 and result['stdout'].strip():
            folders = [f for f in result['stdout'].strip().split('\n') if '_' in f]
            folders.sort(reverse=True)
            for i, f in enumerate(folders):
                self.table.insertRow(i)
                self.table.setItem(i, 0, QTableWidgetItem(f))

    def restore_backup(self):
        dev = self.device_combo.currentData()
        job = self.job_combo.currentText()
        row = self.table.currentRow()
        if not dev or "No policies" in job or row < 0: return
        target = self.table.item(row, 0).text()
        reply = QMessageBox.question(self, "Confirm", f"Restore '{target}'? A safety backup will be taken.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes: return
        
        self.btn_restore.setEnabled(False)
        script = f"""set -e
SCRIPT="/usr/local/bin/{job}_adminbackup.sh"
SRC=$(grep '^SRC=' "$SCRIPT" | cut -d'"' -f2)
DEST=$(grep '^DEST=' "$SCRIPT" | cut -d'"' -f2)
/usr/local/bin/{job}_adminbackup.sh
rsync -a --delete "$DEST/{target}/" "$SRC/"
echo "Restore Complete!"
"""
        cmd = f"bash -c 'echo {base64.b64encode(script.encode()).decode()} | base64 -d | bash'"
        self.worker_restore = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_restore.finished.connect(lambda r: self.btn_restore.setEnabled(True) or self.log(r['stdout']))
        self.worker_restore.start()
