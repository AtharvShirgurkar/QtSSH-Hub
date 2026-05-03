from PyQt6.QtCore import QThread, pyqtSignal
from linux_admin.core.ssh_client import SSHClientManager

class SSHWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, device_data, command, sec_mgr, use_sudo=False):
        super().__init__()
        self.device_data = device_data
        self.command = command
        self.sec_mgr = sec_mgr
        self.use_sudo = use_sudo

    def run(self):
        try:
            cred = self.sec_mgr.decrypt(self.device_data['credential'])
            client = SSHClientManager(
                self.device_data['ip'], 
                self.device_data['port'], 
                self.device_data['username'], 
                self.device_data['auth_type'], 
                cred
            )
            sudo_pwd = cred if (self.use_sudo and self.device_data['auth_type'] == 'password') else None
            out, err, code = client.execute(self.command, use_sudo=self.use_sudo, sudo_password=sudo_pwd)
            client.close()
            self.finished.emit({'stdout': out, 'stderr': err, 'code': code, 'device': self.device_data})
        except Exception as e:
            self.error.emit(str(e))

class AnsibleWorker(QThread):
    finished = pyqtSignal(str, str, int)
    error = pyqtSignal(str)

    def __init__(self, ansible_mgr, devices, packages, state):
        super().__init__()
        self.ansible_mgr = ansible_mgr
        self.devices = devices
        self.packages = packages
        self.state = state

    def run(self):
        try:
            out, err, code = self.ansible_mgr.run_package_playbook(self.devices, self.packages, self.state)
            self.finished.emit(out, err, code)
        except Exception as e:
            self.error.emit(str(e))
