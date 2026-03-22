import base64
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, 
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, 
                             QGroupBox, QFormLayout, QLineEdit, QMessageBox, QTextEdit)
from PyQt6.QtCore import Qt
from linux_admin.ui.workers import SSHWorker

class BackupsTab(QWidget):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        
        layout = QVBoxLayout(self)
        
        # --- 1. Device Selection ---
        header = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.currentIndexChanged.connect(self.fetch_existing_jobs)
        self.btn_refresh_jobs = QPushButton("Refresh Device Jobs")
        self.btn_refresh_jobs.clicked.connect(self.fetch_existing_jobs)
        
        header.addWidget(QLabel("Select Device:"))
        header.addWidget(self.device_combo)
        header.addWidget(self.btn_refresh_jobs)
        layout.addLayout(header)
        
        # --- 2. Setup New Backup Job ---
        setup_group = QGroupBox("Setup Automated Backup Job")
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
        
        self.btn_deploy = QPushButton("Deploy Systemd Backup Service & Timer")
        self.btn_deploy.clicked.connect(self.deploy_backup_job)
        
        setup_layout.addRow("Job Name:", self.job_name_in)
        setup_layout.addRow("Source Directory:", self.src_in)
        setup_layout.addRow("Destination Directory:", self.dest_in)
        setup_layout.addRow("Schedule (Timer):", self.schedule_combo)
        setup_layout.addRow(self.btn_deploy)
        layout.addWidget(setup_group)
        
        # --- 3. Manage Existing Backups ---
        manage_group = QGroupBox("Manage Jobs & Restore")
        manage_layout = QVBoxLayout(manage_group)
        
        job_select_layout = QHBoxLayout()
        self.job_combo = QComboBox()
        self.btn_load_backups = QPushButton("List Backups for Selected Job")
        self.btn_load_backups.clicked.connect(self.list_backups)
        self.btn_run_now = QPushButton("Trigger Backup Now")
        self.btn_run_now.clicked.connect(self.trigger_manual_backup)
        
        job_select_layout.addWidget(QLabel("Configured Jobs:"))
        job_select_layout.addWidget(self.job_combo)
        job_select_layout.addWidget(self.btn_load_backups)
        job_select_layout.addWidget(self.btn_run_now)
        manage_layout.addLayout(job_select_layout)
        
        self.table = QTableWidget()
        self.table.setColumnCount(1)
        self.table.setHorizontalHeaderLabels(["Available Backup Versions (Timestamps)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        manage_layout.addWidget(self.table)
        
        self.btn_restore = QPushButton("Restore Selected Version (Safe Restore)")
        self.btn_restore.setStyleSheet("background-color: #8b0000; color: white; font-weight: bold;")
        self.btn_restore.clicked.connect(self.restore_backup)
        manage_layout.addWidget(self.btn_restore)
        
        layout.addWidget(manage_group)
        
        # Output Log
        self.output_log = QTextEdit()
        self.output_log.setReadOnly(True)
        self.output_log.setMaximumHeight(120)
        layout.addWidget(QLabel("Operation Log:"))
        layout.addWidget(self.output_log)
        
        self.refresh_devices()

    def refresh_devices(self):
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for dev in self.db_mgr.get_devices():
            self.device_combo.addItem(f"{dev['name']} ({dev['ip']})", dev)
        self.device_combo.blockSignals(False)
        self.fetch_existing_jobs()

    def log(self, message):
        self.output_log.append(message)

    def fetch_existing_jobs(self):
        dev = self.device_combo.currentData()
        if not dev: return
        self.job_combo.clear()
        
        # Run command safely using base64 wrapper
        script = "ls /usr/local/bin/*_adminbackup.sh 2>/dev/null | awk -F'/' '{print $NF}' | sed 's/_adminbackup.sh//'"
        b64_script = base64.b64encode(script.encode('utf-8')).decode('utf-8')
        cmd = f"bash -c 'echo {b64_script} | base64 -d | bash'"
        
        self.worker_fetch = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_fetch.finished.connect(self.populate_jobs)
        self.worker_fetch.start()

    def populate_jobs(self, result):
        if result['code'] == 0 and result['stdout'].strip():
            jobs = result['stdout'].strip().split('\n')
            self.job_combo.addItems(jobs)
        else:
            self.job_combo.addItem("No jobs found")

    def deploy_backup_job(self):
        dev = self.device_combo.currentData()
        job_name = self.job_name_in.text().strip()
        src = self.src_in.text().strip()
        dest = self.dest_in.text().strip()
        schedule = self.schedule_combo.currentData()
        
        if not dev or not job_name or not src or not dest:
            QMessageBox.warning(self, "Error", "All fields are required.")
            return
            
        if ' ' in job_name:
            QMessageBox.warning(self, "Error", "Job name cannot contain spaces.")
            return

        self.btn_deploy.setEnabled(False)
        self.log(f"Deploying Backup Job '{job_name}' to {dev['name']}...")

        # Notice `set -e` at the top. This ensures if ANY line fails, the entire script fails and throws an error back to our UI.
        bash_payload = f"""set -e
# Ensure rsync exists
command -v rsync >/dev/null 2>&1 || {{ apt-get update && apt-get install -y rsync || yum install -y rsync; }}

mkdir -p "{dest}"

cat << 'EOF' > /usr/local/bin/{job_name}_adminbackup.sh
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
chmod +x /usr/local/bin/{job_name}_adminbackup.sh

cat << 'EOF' > /etc/systemd/system/{job_name}_adminbackup.service
[Unit]
Description=Automated Backup for {job_name}
[Service]
Type=oneshot
ExecStart=/usr/local/bin/{job_name}_adminbackup.sh
EOF

cat << 'EOF' > /etc/systemd/system/{job_name}_adminbackup.timer
[Unit]
Description=Timer for Backup {job_name}
[Timer]
OnCalendar={schedule}
Persistent=true
[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now {job_name}_adminbackup.timer
echo "Successfully deployed and enabled timer for {job_name}."
"""

        # Encode script to avoid all multi-line & quote escaping issues over SSH
        b64_script = base64.b64encode(bash_payload.encode('utf-8')).decode('utf-8')
        cmd = f"bash -c 'echo {b64_script} | base64 -d | bash'"

        self.worker_deploy = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_deploy.finished.connect(self.on_deploy_finished)
        self.worker_deploy.start()

    def on_deploy_finished(self, result):
        self.btn_deploy.setEnabled(True)
        if result['code'] == 0:
            self.log(result['stdout'])
            self.fetch_existing_jobs()
            QMessageBox.information(self, "Success", "Backup job deployed and timer started!")
        else:
            self.log(f"Error: {result['stderr']}")
            QMessageBox.critical(self, "Error", "Failed to deploy. Check logs for details.")

    def trigger_manual_backup(self):
        dev = self.device_combo.currentData()
        job = self.job_combo.currentText()
        if not dev or job == "No jobs found" or not job: return
        
        self.log(f"Triggering manual backup for '{job}'...")
        cmd = f"systemctl start {job}_adminbackup.service" # Single line command, standard execution is fine here
        
        self.worker_trigger = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_trigger.finished.connect(lambda r: self.log("Backup completed successfully!" if r['code']==0 else f"Failed: {r['stderr']}"))
        self.worker_trigger.start()

    def list_backups(self):
        dev = self.device_combo.currentData()
        job = self.job_combo.currentText()
        if not dev or job == "No jobs found" or not job: return
        
        self.log(f"Fetching backups for '{job}'...")
        
        script = f"""set -e
SCRIPT="/usr/local/bin/{job}_adminbackup.sh"
if [ -f "$SCRIPT" ]; then
    DEST=$(grep '^DEST=' "$SCRIPT" | cut -d'"' -f2)
    ls -1 "$DEST"
fi
"""
        b64_script = base64.b64encode(script.encode('utf-8')).decode('utf-8')
        cmd = f"bash -c 'echo {b64_script} | base64 -d | bash'"
        
        self.worker_list = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_list.finished.connect(self.populate_backups_table)
        self.worker_list.start()

    def populate_backups_table(self, result):
        self.table.setRowCount(0)
        if result['code'] == 0 and result['stdout'].strip():
            folders = result['stdout'].strip().split('\n')
            # Filter out random files, keep only timestamp directories roughly
            folders = [f for f in folders if '_' in f and '-' in f]
            # Sort descending (newest first)
            folders.sort(reverse=True)
            
            for i, f in enumerate(folders):
                self.table.insertRow(i)
                self.table.setItem(i, 0, QTableWidgetItem(f))
        else:
            self.log("No existing backup folders found.")

    def restore_backup(self):
        dev = self.device_combo.currentData()
        job = self.job_combo.currentText()
        row = self.table.currentRow()
        
        if not dev or job == "No jobs found" or not job or row < 0:
            QMessageBox.warning(self, "Warning", "Please select a backup version from the table to restore.")
            return
            
        target_version = self.table.item(row, 0).text()
        
        reply = QMessageBox.question(self, "Confirm Restore", 
                                     f"Are you sure you want to restore to version '{target_version}'?\n\n"
                                     "A safety backup of the CURRENT state will be taken automatically before restoring.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                                     
        if reply != QMessageBox.StandardButton.Yes: return
        
        self.btn_restore.setEnabled(False)
        self.log(f"Starting safe restore sequence to '{target_version}'...")
        
        restore_script = f"""set -e
SCRIPT="/usr/local/bin/{job}_adminbackup.sh"
SRC=$(grep '^SRC=' "$SCRIPT" | cut -d'"' -f2)
DEST=$(grep '^DEST=' "$SCRIPT" | cut -d'"' -f2)

echo "Taking pre-restore safety backup..."
/usr/local/bin/{job}_adminbackup.sh

echo "Restoring from $DEST/{target_version}/ to $SRC/"
# Notice the trailing slashes, they are crucial in rsync to copy contents!
rsync -a --delete "$DEST/{target_version}/" "$SRC/"

echo "Restore Complete!"
"""
        b64_script = base64.b64encode(restore_script.encode('utf-8')).decode('utf-8')
        cmd = f"bash -c 'echo {b64_script} | base64 -d | bash'"
        
        self.worker_restore = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_restore.finished.connect(self.on_restore_finished)
        self.worker_restore.start()

    def on_restore_finished(self, result):
        self.btn_restore.setEnabled(True)
        if result['code'] == 0:
            self.log(result['stdout'])
            QMessageBox.information(self, "Success", "Restore sequence completed successfully! A backup of the pre-restore state was also saved.")
            self.list_backups() # Refresh table to show the new safety backup
        else:
            self.log(f"Restore Failed: {result['stderr']}")
            QMessageBox.critical(self, "Error", "Restore sequence failed. Check logs.")
