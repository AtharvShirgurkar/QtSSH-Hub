import base64
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, 
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, 
                             QGroupBox, QFormLayout, QLineEdit, QMessageBox, QTextEdit, QSplitter, QSpinBox, QDialog)
from PyQt6.QtCore import Qt
from linux_admin.ui.workers import SSHWorker

class BackupJobDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Backup Policy")
        self.resize(450, 300)
        layout = QFormLayout(self)
        
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
        self.schedule_combo.addItem("Monthly (1st day)", "*-*-01 00:00:00")
        
        self.retention_spin = QSpinBox()
        self.retention_spin.setRange(1, 365)
        self.retention_spin.setValue(7)
        self.retention_spin.setSuffix(" backups")
        
        self.btn_deploy = QPushButton("Deploy Backup Policy")
        self.btn_deploy.setObjectName("PrimaryBtn")
        self.btn_deploy.clicked.connect(self.accept)
        
        layout.addRow("Job Alias:", self.job_name_in)
        layout.addRow("Source Dir:", self.src_in)
        layout.addRow("Dest Dir:", self.dest_in)
        layout.addRow("Schedule:", self.schedule_combo)
        layout.addRow("Retention:", self.retention_spin)
        layout.addRow(self.btn_deploy)
        
    def get_data(self):
        return {
            "name": self.job_name_in.text().strip(),
            "src": self.src_in.text().strip(),
            "dest": self.dest_in.text().strip(),
            "schedule": self.schedule_combo.currentData(),
            "retention": self.retention_spin.value()
        }

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
        
        # --- Target Node Selection ---
        header = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(250)
        self.device_combo.currentIndexChanged.connect(self.fetch_existing_jobs)
        self.btn_refresh_jobs = QPushButton("Refresh Host Data")
        self.btn_refresh_jobs.clicked.connect(self.fetch_existing_jobs)
        
        header.addWidget(QLabel("Target Node:"))
        header.addWidget(self.device_combo)
        header.addWidget(self.btn_refresh_jobs)
        header.addStretch()
        layout.addLayout(header)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # --- Left Panel: Job Management ---
        jobs_grp = QGroupBox("Configured Backup Policies")
        jobs_lay = QVBoxLayout(jobs_grp)
        
        self.jobs_table = QTableWidget()
        self.jobs_table.setColumnCount(3)
        self.jobs_table.setHorizontalHeaderLabels(["Job Alias", "Timer State", "Active"])
        self.jobs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.jobs_table.verticalHeader().setVisible(False)
        self.jobs_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.jobs_table.itemSelectionChanged.connect(self.on_job_selected)
        jobs_lay.addWidget(self.jobs_table)
        
        jobs_btns1 = QHBoxLayout()
        self.btn_add_job = QPushButton("Create Policy")
        self.btn_add_job.clicked.connect(self.show_add_job_dialog)
        self.btn_del_job = QPushButton("Delete Policy")
        self.btn_del_job.setObjectName("DangerBtn")
        self.btn_del_job.clicked.connect(self.delete_job)
        jobs_btns1.addWidget(self.btn_add_job)
        jobs_btns1.addWidget(self.btn_del_job)
        
        jobs_btns2 = QHBoxLayout()
        self.btn_toggle_timer = QPushButton("Toggle Timer")
        self.btn_toggle_timer.clicked.connect(self.toggle_timer)
        self.btn_view_logs = QPushButton("View Logs")
        self.btn_view_logs.clicked.connect(self.view_job_logs)
        self.btn_run_now = QPushButton("Trigger Backup Now")
        self.btn_run_now.setObjectName("PrimaryBtn")
        self.btn_run_now.clicked.connect(self.trigger_manual_backup)
        
        jobs_btns2.addWidget(self.btn_toggle_timer)
        jobs_btns2.addWidget(self.btn_view_logs)
        jobs_btns2.addWidget(self.btn_run_now)
        
        jobs_lay.addLayout(jobs_btns1)
        jobs_lay.addLayout(jobs_btns2)
        splitter.addWidget(jobs_grp)
        
        # --- Right Panel: Snapshot Management ---
        snaps_grp = QGroupBox("Available Snapshots & Restore")
        snaps_lay = QVBoxLayout(snaps_grp)
        
        self.snaps_table = QTableWidget()
        self.snaps_table.setColumnCount(2)
        self.snaps_table.setHorizontalHeaderLabels(["Snapshot Timestamp", "Size on Disk"])
        self.snaps_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.snaps_table.verticalHeader().setVisible(False)
        self.snaps_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        snaps_lay.addWidget(self.snaps_table)
        
        snaps_btns = QHBoxLayout()
        self.btn_refresh_snaps = QPushButton("Refresh List")
        self.btn_refresh_snaps.clicked.connect(self.list_backups)
        self.btn_del_snap = QPushButton("Delete Snapshot")
        self.btn_del_snap.setObjectName("DangerBtn")
        self.btn_del_snap.clicked.connect(self.delete_snapshot)
        
        self.btn_restore = QPushButton("Safe Restore Selected")
        self.btn_restore.setStyleSheet("background-color: #fab387; color: #11111b; font-weight: bold;")
        self.btn_restore.clicked.connect(self.restore_backup)
        
        snaps_btns.addWidget(self.btn_refresh_snaps)
        snaps_btns.addWidget(self.btn_del_snap)
        snaps_btns.addWidget(self.btn_restore)
        snaps_lay.addLayout(snaps_btns)
        splitter.addWidget(snaps_grp)
        
        splitter.setSizes([550, 450])
        
        # --- Bottom Panel: Log Output ---
        self.output_log = QTextEdit()
        self.output_log.setReadOnly(True)
        self.output_log.setStyleSheet("background-color: #11111b; font-family: monospace;")
        self.output_log.setMaximumHeight(150)
        layout.addWidget(QLabel("Operation Log:"))
        layout.addWidget(self.output_log)
        
        self.refresh_devices()

    def refresh_devices(self):
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        device_status = getattr(self.db_mgr, 'device_status', {})
        for dev in self.db_mgr.get_devices():
            if device_status.get(dev['id']) == "Reachable":
                self.device_combo.addItem(f"{dev['name']} ({dev['ip']})", dev)
        self.device_combo.blockSignals(False)
        self.fetch_existing_jobs()

    def log(self, message):
        self.output_log.append(message)

    # --- Job Management Logic ---
    def fetch_existing_jobs(self):
        dev = self.device_combo.currentData()
        if not dev: return
        self.jobs_table.setRowCount(0)
        self.snaps_table.setRowCount(0)
        
        # FIX: Robustly fetch systemd status without allowing multi-line string output on failures
        script = """
        for script in /usr/local/bin/*_adminbackup.sh; do
            if [ -f "$script" ]; then
                job=$(basename "$script" | sed 's/_adminbackup.sh//')
                
                state=$(systemctl is-enabled "${job}_adminbackup.timer" 2>/dev/null || true)
                active=$(systemctl is-active "${job}_adminbackup.timer" 2>/dev/null || true)
                
                [ -z "$state" ] && state="unknown"
                [ -z "$active" ] && active="unknown"
                
                # Strip newlines completely to prevent parser breaking
                state=$(echo "$state" | tr -d '\n')
                active=$(echo "$active" | tr -d '\n')
                
                echo "$job|$state|$active"
            fi
        done
        """
        b64_script = base64.b64encode(script.encode('utf-8')).decode('utf-8')
        cmd = f"bash -c 'echo {b64_script} | base64 -d | bash'"
        
        self.worker_fetch = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_fetch.finished.connect(self.populate_jobs)
        self.worker_fetch.start()

    def populate_jobs(self, result):
        self.jobs_table.setRowCount(0)
        if result['code'] == 0 and result['stdout'].strip():
            lines = result['stdout'].strip().split('\n')
            for i, line in enumerate(lines):
                parts = line.split('|')
                if len(parts) == 3:
                    self.jobs_table.insertRow(i)
                    self.jobs_table.setItem(i, 0, QTableWidgetItem(parts[0]))
                    
                    state_item = QTableWidgetItem(parts[1])
                    if parts[1] == 'enabled': state_item.setForeground(Qt.GlobalColor.green)
                    else: state_item.setForeground(Qt.GlobalColor.gray)
                    self.jobs_table.setItem(i, 1, state_item)
                    
                    active_item = QTableWidgetItem(parts[2])
                    if parts[2] == 'active': active_item.setForeground(Qt.GlobalColor.green)
                    else: active_item.setForeground(Qt.GlobalColor.gray)
                    self.jobs_table.setItem(i, 2, active_item)

    def on_job_selected(self):
        self.list_backups()

    def show_add_job_dialog(self):
        dev = self.device_combo.currentData()
        if not dev:
            QMessageBox.warning(self, "Warning", "Please select a target node first.")
            return
            
        dlg = BackupJobDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            if not data['name'] or not data['src'] or not data['dest']:
                QMessageBox.warning(self, "Error", "All fields are required.")
                return
            if ' ' in data['name']:
                QMessageBox.warning(self, "Error", "Job alias cannot contain spaces.")
                return
            self.deploy_backup_job(data)

    def deploy_backup_job(self, data):
        dev = self.device_combo.currentData()
        job_name = data['name']
        src = data['src']
        dest = data['dest']
        schedule = data['schedule']
        retention = data['retention']

        self.log(f"Deploying Backup Job '{job_name}' to {dev['name']}...")

        bash_payload = f"""set -e
command -v rsync >/dev/null 2>&1 || {{ apt-get update && apt-get install -y rsync || yum install -y rsync; }}
mkdir -p "{dest}"

cat << 'EOF' > /usr/local/bin/{job_name}_adminbackup.sh
#!/bin/bash
SRC="{src}"
DEST="{dest}"
RETENTION={retention}

mkdir -p "$DEST"
LATEST=$(ls -td "$DEST"/*/ 2>/dev/null | head -1)
NOW=$(date +"%Y-%m-%d_%H-%M-%S")

if [ -z "$LATEST" ]; then
    rsync -a --delete "$SRC/" "$DEST/$NOW/"
else
    rsync -a --delete --link-dest="$LATEST" "$SRC/" "$DEST/$NOW/"
fi

# Apply retention policy
if [ "$RETENTION" -gt 0 ]; then
    cd "$DEST" && ls -td */ 2>/dev/null | tail -n +$((RETENTION + 1)) | xargs -I {{}} rm -rf "{{}}"
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
systemctl enable --now {job_name}_adminbackup.timer >/dev/null 2>&1
echo "Successfully deployed and enabled timer for {job_name}."
"""
        b64_script = base64.b64encode(bash_payload.encode('utf-8')).decode('utf-8')
        cmd = f"bash -c 'echo {b64_script} | base64 -d | bash'"

        self.worker_deploy = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_deploy.finished.connect(lambda r: self.log(r['stdout']) or self.fetch_existing_jobs())
        self.worker_deploy.start()

    def delete_job(self):
        dev = self.device_combo.currentData()
        row = self.jobs_table.currentRow()
        if not dev or row < 0: return
        job = self.jobs_table.item(row, 0).text()
        
        reply = QMessageBox.question(self, "Confirm Delete", 
                                     f"Delete backup policy '{job}'? Existing snapshots will NOT be deleted.", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes: return
        
        script = f"""
        systemctl stop {job}_adminbackup.timer 2>/dev/null || true
        systemctl disable {job}_adminbackup.timer 2>/dev/null || true
        rm -f /etc/systemd/system/{job}_adminbackup.timer
        rm -f /etc/systemd/system/{job}_adminbackup.service
        rm -f /usr/local/bin/{job}_adminbackup.sh
        systemctl daemon-reload
        echo "Backup policy '{job}' successfully removed from the system."
        """
        b64_script = base64.b64encode(script.encode('utf-8')).decode('utf-8')
        cmd = f"bash -c 'echo {b64_script} | base64 -d | bash'"
        
        self.worker_del = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_del.finished.connect(lambda r: self.log(r['stdout']) or self.fetch_existing_jobs())
        self.worker_del.start()

    def toggle_timer(self):
        dev = self.device_combo.currentData()
        row = self.jobs_table.currentRow()
        if not dev or row < 0: return
        job = self.jobs_table.item(row, 0).text()
        state = self.jobs_table.item(row, 1).text()
        
        action = "disable" if state == "enabled" else "enable"
        
        # Hide systemd's noisy "Removed symlink" stderr output by redirecting to /dev/null
        script = f"""
        if [ "{action}" = "enable" ]; then
            systemctl enable {job}_adminbackup.timer >/dev/null 2>&1
            systemctl start {job}_adminbackup.timer >/dev/null 2>&1
            echo "Timer successfully enabled for {job}."
        else
            systemctl stop {job}_adminbackup.timer >/dev/null 2>&1
            systemctl disable {job}_adminbackup.timer >/dev/null 2>&1
            echo "Timer successfully disabled for {job}."
        fi
        """
        b64_script = base64.b64encode(script.encode('utf-8')).decode('utf-8')
        cmd = f"bash -c 'echo {b64_script} | base64 -d | bash'"
        
        self.worker_toggle = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_toggle.finished.connect(lambda r: self.log(r['stdout']) or self.fetch_existing_jobs())
        self.worker_toggle.start()

    def view_job_logs(self):
        dev = self.device_combo.currentData()
        row = self.jobs_table.currentRow()
        if not dev or row < 0: return
        job = self.jobs_table.item(row, 0).text()
        
        self.log(f"Fetching logs for backup job '{job}'...")
        cmd = f"journalctl -u {job}_adminbackup.service -n 50 --no-pager"
        self.w_log = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.w_log.finished.connect(lambda r: self.log(r['stdout'] or "No recent logs."))
        self.w_log.start()

    def trigger_manual_backup(self):
        dev = self.device_combo.currentData()
        row = self.jobs_table.currentRow()
        if not dev or row < 0: return
        job = self.jobs_table.item(row, 0).text()
        
        self.btn_run_now.setEnabled(False)
        self.log(f"Triggering manual backup for '{job}'... Please wait, this may take a moment.")
        
        cmd = f"systemctl start {job}_adminbackup.service"
        self.worker_trigger = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_trigger.finished.connect(self.on_manual_trigger_done)
        self.worker_trigger.start()

    def on_manual_trigger_done(self, r):
        self.btn_run_now.setEnabled(True)
        if r['code'] == 0:
            self.log("Manual backup completed successfully!")
            self.list_backups()
        else:
            self.log(f"Manual backup failed: {r['stderr']}")

    # --- Snapshot Management Logic ---
    def list_backups(self):
        dev = self.device_combo.currentData()
        row = self.jobs_table.currentRow()
        if not dev or row < 0: return
        job = self.jobs_table.item(row, 0).text()
        
        script = f"""
        SCRIPT="/usr/local/bin/{job}_adminbackup.sh"
        if [ -f "$SCRIPT" ]; then
            DEST=$(grep '^DEST=' "$SCRIPT" | cut -d'"' -f2)
            if [ -d "$DEST" ]; then
                cd "$DEST"
                for dir in */ ; do
                    if [ "$dir" != "*/" ]; then
                        size=$(du -sh "$dir" | cut -f1)
                        echo "${{dir%/}}|$size"
                    fi
                done
            fi
        fi
        """
        b64_script = base64.b64encode(script.encode('utf-8')).decode('utf-8')
        cmd = f"bash -c 'echo {b64_script} | base64 -d | bash'"
        
        self.worker_list = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_list.finished.connect(self.populate_snaps)
        self.worker_list.start()

    def populate_snaps(self, result):
        self.snaps_table.setRowCount(0)
        if result['code'] == 0 and result['stdout'].strip():
            lines = result['stdout'].strip().split('\n')
            lines = [l for l in lines if '|' in l and '_' in l and '-' in l]
            lines.sort(reverse=True)
            for i, line in enumerate(lines):
                parts = line.split('|')
                if len(parts) == 2:
                    self.snaps_table.insertRow(i)
                    self.snaps_table.setItem(i, 0, QTableWidgetItem(parts[0]))
                    self.snaps_table.setItem(i, 1, QTableWidgetItem(parts[1]))

    def delete_snapshot(self):
        dev = self.device_combo.currentData()
        job_row = self.jobs_table.currentRow()
        snap_row = self.snaps_table.currentRow()
        if not dev or job_row < 0 or snap_row < 0: return
        
        job = self.jobs_table.item(job_row, 0).text()
        target = self.snaps_table.item(snap_row, 0).text()
        
        reply = QMessageBox.question(self, "Confirm Delete", 
                                     f"Are you sure you want to permanently delete snapshot '{target}'?", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes: return
        
        script = f"""
        SCRIPT="/usr/local/bin/{job}_adminbackup.sh"
        DEST=$(grep '^DEST=' "$SCRIPT" | cut -d'"' -f2)
        if [ -d "$DEST/{target}" ]; then
            rm -rf "$DEST/{target}"
            echo "Snapshot '{target}' successfully deleted."
        else
            echo "Error: Snapshot '{target}' not found on disk."
        fi
        """
        b64_script = base64.b64encode(script.encode('utf-8')).decode('utf-8')
        cmd = f"bash -c 'echo {b64_script} | base64 -d | bash'"
        
        self.worker_del_snap = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
        self.worker_del_snap.finished.connect(lambda r: self.log(r['stdout']) or self.list_backups())
        self.worker_del_snap.start()

    def restore_backup(self):
        dev = self.device_combo.currentData()
        job_row = self.jobs_table.currentRow()
        snap_row = self.snaps_table.currentRow()
        
        if not dev or job_row < 0 or snap_row < 0:
            QMessageBox.warning(self, "Warning", "Please select a backup version from the table to restore.")
            return
            
        job = self.jobs_table.item(job_row, 0).text()
        target_version = self.snaps_table.item(snap_row, 0).text()
        
        reply = QMessageBox.question(self, "Confirm Restore", 
                                     f"Restore to version '{target_version}'?\n\n"
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
            self.list_backups()
        else:
            self.log(f"Restore Failed: {result['stderr']}")
            QMessageBox.critical(self, "Error", "Restore sequence failed. Check logs.")
