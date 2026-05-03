import paramiko
import io
import socket

class SSHClientManager:
    def __init__(self, ip, port, username, auth_type, credential):
        self.ip = ip
        self.port = port
        self.username = username
        self.auth_type = auth_type
        self.credential = credential
        self.client = None

    def connect(self):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            if self.auth_type == 'password':
                self.client.connect(self.ip, port=self.port, username=self.username, password=self.credential, timeout=10)
            elif self.auth_type == 'key':
                clean_key = self.credential.replace('\r\n', '\n').strip() + '\n'
                key_file = io.StringIO(clean_key)
                pkey = None
                
                for key_class in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
                    try:
                        key_file.seek(0)
                        pkey = key_class.from_private_key(key_file)
                        break
                    except Exception:
                        pass
                
                if not pkey:
                    raise Exception("Invalid or unsupported private key format. Ensure it is an unencrypted RSA, Ed25519, or ECDSA key.")
                    
                self.client.connect(self.ip, port=self.port, username=self.username, pkey=pkey, timeout=10)
        except Exception as e:
            raise Exception(f"Failed to connect to {self.ip}: {str(e)}")

    def execute(self, command, use_sudo=False, sudo_password=None):
        if not self.client:
            self.connect()
            
        if use_sudo:
            if sudo_password:
                command = f"sudo -S -p '' {command}"
            else:
                command = f"sudo -n {command}"
            
        stdin, stdout, stderr = self.client.exec_command(command)
        
        if use_sudo and sudo_password:
            stdin.write(sudo_password + "\n")
            stdin.flush()
            
        stdin.close()
        stdout.channel.settimeout(30.0)
        
        try:
            out = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            exit_status = stdout.channel.recv_exit_status()
        except socket.timeout:
            return "", "SSH Command execution timed out.", 124
            
        return out, err, exit_status

    def close(self):
        if self.client:
            self.client.close()
            self.client = None
