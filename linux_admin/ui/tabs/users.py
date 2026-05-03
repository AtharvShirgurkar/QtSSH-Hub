from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QTextEdit, 
                             QPushButton, QRadioButton, QButtonGroup, QGroupBox, QLineEdit, QSplitter, QCheckBox, QFormLayout)
from PyQt6.QtCore import Qt
import base64
from linux_admin.ui.workers import SSHWorker

class UsersTab(QWidget):
    def __init__(self, sec_mgr, db_mgr):
        super().__init__()
        self.sec_mgr = sec_mgr
        self.db_mgr = db_mgr
        self.active_workers = []
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        title = QLabel("Users & Permissions Manager")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)
        
        # --- Target Selection ---
        target_group = QGroupBox("Target Selection")
        target_layout = QHBoxLayout(target_group)
        self.radio_device = QRadioButton("Single Server")
        self.radio_group = QRadioButton("Server Group")
        self.radio_device.setChecked(True)
        self.btn_group = QButtonGroup()
        self.btn_group.addButton(self.radio_device)
        self.btn_group.addButton(self.radio_group)
        self.target_combo = QComboBox()
        self.target_combo.setMinimumWidth(300)
        target_layout.addWidget(self.radio_device)
        target_layout.addWidget(self.radio_group)
        target_layout.addWidget(self.target_combo)
        target_layout.addStretch()
        layout.addWidget(target_group)
        
        self.radio_device.toggled.connect(self.refresh_targets)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # --- Left Panel: Management Forms ---
        forms_widget = QWidget()
        forms_layout = QVBoxLayout(forms_widget)
        forms_layout.setContentsMargins(0, 0, 10, 0)
        
        # 1. Create / Modify User
        user_grp = QGroupBox("Create or Modify User")
        user_lay = QFormLayout(user_grp)
        
        self.u_name = QLineEdit()
        self.u_pass = QLineEdit()
        self.u_pass.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.u_shell = QLineEdit("bash")
        self.u_groups = QLineEdit()
        self.u_groups.setPlaceholderText("comma-separated, e.g. docker,www-data")
        self.u_expiry = QLineEdit()
        self.u_expiry.setPlaceholderText("YYYY-MM-DD or blank")
        self.u_skel = QLineEdit()
        self.u_skel.setPlaceholderText("Alternative skeleton dir (optional)")
        self.u_home = QCheckBox("Create Home Directory (-m)")
        self.u_home.setChecked(True)
        
        self.btn_apply_user = QPushButton("Deploy User Configuration")
        self.btn_apply_user.setObjectName("PrimaryBtn")
        self.btn_apply_user.clicked.connect(self.apply_user)
        
        user_lay.addRow("Username:", self.u_name)
        user_lay.addRow("Password:", self.u_pass)
        user_lay.addRow("Login Shell:", self.u_shell)
        user_lay.addRow("Groups:", self.u_groups)
        user_lay.addRow("Account Expiry:", self.u_expiry)
        user_lay.addRow("Skel Dir:", self.u_skel)
        user_lay.addRow("", self.u_home)
        user_lay.addRow(self.btn_apply_user)
        forms_layout.addWidget(user_grp)
        
        # 2. Sudoers Management
        sudo_grp = QGroupBox("Sudoers Privilege Delegation")
        sudo_lay = QFormLayout(sudo_grp)
        self.s_user = QLineEdit()
        self.s_user.setPlaceholderText("Target Username")
        self.s_cmd = QLineEdit("ALL")
        self.s_cmd.setPlaceholderText("e.g. ALL, /usr/bin/systemctl restart nginx")
        self.s_nopw = QCheckBox("NOPASSWD (No password required for this rule)")
        
        s_btns = QHBoxLayout()
        self.btn_apply_sudo = QPushButton("Apply Sudo Rule")
        self.btn_apply_sudo.clicked.connect(self.apply_sudo)
        self.btn_revoke_sudo = QPushButton("Revoke All Custom Rules")
        self.btn_revoke_sudo.setObjectName("DangerBtn")
        self.btn_revoke_sudo.clicked.connect(self.revoke_sudo)
        s_btns.addWidget(self.btn_apply_sudo)
        s_btns.addWidget(self.btn_revoke_sudo)
        
        sudo_lay.addRow("Username:", self.s_user)
        sudo_lay.addRow("Allowed Cmd:", self.s_cmd)
        sudo_lay.addRow("", self.s_nopw)
        sudo_lay.addRow(s_btns)
        forms_layout.addWidget(sudo_grp)
        
        # 3. Delete User
        del_grp = QGroupBox("Remove User")
        del_lay = QVBoxLayout(del_grp)
        
        del_row1 = QHBoxLayout()
        self.d_user = QLineEdit()
        self.d_user.setPlaceholderText("Username to delete")
        self.btn_del = QPushButton("Delete User")
        self.btn_del.setObjectName("DangerBtn")
        self.btn_del.clicked.connect(self.delete_user)
        del_row1.addWidget(self.d_user)
        del_row1.addWidget(self.btn_del)
        
        self.d_rm_home = QCheckBox("Remove Home Directory (-r)")
        self.d_backup = QCheckBox("Backup Home to /root before removal (tar.xz)")
        self.d_backup.setEnabled(False)
        self.d_rm_home.toggled.connect(self.d_backup.setEnabled)
        
        del_lay.addLayout(del_row1)
        del_lay.addWidget(self.d_rm_home)
        del_lay.addWidget(self.d_backup)
        
        forms_layout.addWidget(del_grp)
        
        forms_layout.addStretch()
        splitter.addWidget(forms_widget)
        
        # --- Right Panel: Log Output ---
        self.output_log = QTextEdit()
        self.output_log.setReadOnly(True)
        self.output_log.setStyleSheet("font-family: monospace; background-color: #11111b;")
        splitter.addWidget(self.output_log)
        
        splitter.setSizes([500, 600])
        self.refresh_devices()

    def refresh_devices(self):
        self.refresh_targets()

    def refresh_targets(self):
        self.target_combo.clear()
        device_status = getattr(self.db_mgr, 'device_status', {})
        
        if self.radio_device.isChecked():
            for dev in self.db_mgr.get_devices():
                if device_status.get(dev['id']) == "Reachable":
                    self.target_combo.addItem(f"{dev['name']} ({dev['ip']})", [dev])
        else:
            for g in self.db_mgr.get_groups():
                devices = self.db_mgr.get_devices(group_id=g['id'])
                reachable_devs = [d for d in devices if device_status.get(d['id']) == "Reachable"]
                if reachable_devs:
                    self.target_combo.addItem(f"Group: {g['name']} ({len(reachable_devs)} reachable)", reachable_devs)

    def log(self, text):
        self.output_log.append(text)

    def execute_batch(self, bash_script):
        devices = self.target_combo.currentData()
        if not devices:
            self.log("No reachable devices selected.")
            return
            
        self.log(f"\n--- Initiating batch job on {len(devices)} target(s) ---")
        b64_script = base64.b64encode(bash_script.encode('utf-8')).decode('utf-8')
        cmd = f"bash -c 'echo {b64_script} | base64 -d | bash'"
        
        # Keep references to workers to prevent garbage collection mid-execution
        self.active_workers = []
        for dev in devices:
            worker = SSHWorker(dev, cmd, self.sec_mgr, use_sudo=True)
            worker.finished.connect(lambda r, n=dev['name']: self.on_worker_finished(r, n))
            self.active_workers.append(worker)
            worker.start()

    def on_worker_finished(self, result, name):
        if result['code'] == 0:
            self.log(f"[SUCCESS] {name}:\n{result['stdout']}")
        else:
            self.log(f"[FAILED] {name}:\n{result['stderr']}\n{result['stdout']}")

    def apply_user(self):
        user = self.u_name.text().strip()
        pw = self.u_pass.text()
        if not user:
            self.log("Username is required!")
            return
            
        script = f"""set -e
SHELL_BIN=$(which "{self.u_shell.text().strip()}" 2>/dev/null || echo /bin/bash)
ARGS=""
if [ "{self.u_home.isChecked()}" = "True" ]; then ARGS="-m"; else ARGS="-M"; fi
if [ -n "{self.u_skel.text().strip()}" ]; then ARGS="$ARGS -k {self.u_skel.text().strip()}"; fi
if [ -n "{self.u_groups.text().strip()}" ]; then ARGS="$ARGS -G {self.u_groups.text().strip()}"; fi
if [ -n "{self.u_expiry.text().strip()}" ]; then ARGS="$ARGS -e {self.u_expiry.text().strip()}"; fi

if id "{user}" &>/dev/null; then
    usermod -s "$SHELL_BIN" $ARGS "{user}"
    echo "User '{user}' successfully modified."
else
    useradd $ARGS -s "$SHELL_BIN" "{user}"
    echo "User '{user}' successfully created."
fi

if [ -n "{pw}" ]; then
    echo "{user}:{pw}" | chpasswd
    echo "Password updated."
fi
"""
        self.execute_batch(script)

    def apply_sudo(self):
        user = self.s_user.text().strip()
        cmd = self.s_cmd.text().strip()
        nopw = "NOPASSWD:" if self.s_nopw.isChecked() else ""
        if not user or not cmd:
            self.log("Username and Command are required for Sudoers.")
            return

        script = f"""set -e
USER="{user}"
FILE="/etc/sudoers.d/${{USER}}_custom"

# Write out the rule
echo "$USER ALL=(ALL) {nopw} {cmd}" > "$FILE"
chmod 440 "$FILE"

# Always safely check the sudoers file syntax
if visudo -c -f "$FILE" &>/dev/null; then
    echo "Sudoers rule safely applied for $USER."
else
    rm -f "$FILE"
    echo "Syntax error detected! Sudoers file was rejected and safely removed."
    exit 1
fi
"""
        self.execute_batch(script)

    def revoke_sudo(self):
        user = self.s_user.text().strip()
        if not user: return
        script = f"""
USER="{user}"
if ls /etc/sudoers.d/${{USER}}* 1> /dev/null 2>&1; then
    rm -f /etc/sudoers.d/${{USER}}*
    echo "All custom sudoers rules removed for $USER."
else
    echo "No custom rules found in /etc/sudoers.d/ for $USER."
fi
"""
        self.execute_batch(script)

    def delete_user(self):
        user = self.d_user.text().strip()
        if not user: return
        
        rm_home = self.d_rm_home.isChecked()
        backup = self.d_backup.isChecked()
        
        cmd_parts = []
        if rm_home and backup:
            cmd_parts.append(f'''
if [ -d "/home/{user}" ]; then
    echo "Backing up /home/{user} to /root/{user}_home_backup_$(date +%F).tar.xz..."
    tar -cJf "/root/{user}_home_backup_$(date +%F).tar.xz" -C /home "{user}"
fi
''')
        
        if rm_home:
            cmd_parts.append(f'userdel -r "{user}" 2>/dev/null || userdel "{user}"')
        else:
            cmd_parts.append(f'userdel "{user}"')
            
        script = f"""
if id "{user}" &>/dev/null; then
    {''.join(cmd_parts)}
    echo "User '{user}' removed from system."
else
    echo "User '{user}' does not exist."
fi
"""
        self.execute_batch(script)
