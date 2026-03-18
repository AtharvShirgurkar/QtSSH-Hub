import paramiko
import io

class SSHClientManager:
    def __init__(self, ip, port, username, auth_type, credential):
        self.ip = ip
        self.port = port
        self.username = username
        self.auth_type = auth_type
        self.credential = credential # Decrypted credential
        self.client = None

    def connect(self):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            if self.auth_type == 'password':
                self.client.connect(self.ip, port=self.port, username=self.username, password=self.credential, timeout=10)
            elif self.auth_type == 'key':
                # Treat credential as the private key string
                key_file = io.StringIO(self.credential)
                try:
                    pkey = paramiko.RSAKey.from_private_key(key_file)
                except paramiko.ssh_exception.PasswordRequiredException:
                    raise Exception("Encrypted private keys not supported yet in this snippet.")
                self.client.connect(self.ip, port=self.port, username=self.username, pkey=pkey, timeout=10)
        except Exception as e:
            raise Exception(f"Failed to connect to {self.ip}: {str(e)}")

    def execute(self, command, sudo_password=None):
        if not self.client:
            self.connect()
            
        if sudo_password:
            command = f"echo {sudo_password} | sudo -S -p '' {command}"
            
        stdin, stdout, stderr = self.client.exec_command(command)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        exit_status = stdout.channel.recv_exit_status()
        
        return out, err, exit_status

    def close(self):
        if self.client:
            self.client.close()
            self.client = None
