import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

class SecurityManager:
    def __init__(self):
        self.config_dir = os.path.expanduser("~/.linux_admin_app")
        self.salt_file = os.path.join(self.config_dir, "salt.key")
        self.verify_file = os.path.join(self.config_dir, "verify.dat")
        self.fernet = None

    def is_initialized(self):
        return os.path.exists(self.salt_file) and os.path.exists(self.verify_file)

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))

    def setup_master_password(self, password: str):
        salt = os.urandom(16)
        with open(self.salt_file, "wb") as f:
            f.write(salt)
            
        key = self._derive_key(password, salt)
        self.fernet = Fernet(key)
        
        enc_token = self.fernet.encrypt(b"LINUX_ADMIN_AUTH_SUCCESS")
        with open(self.verify_file, "wb") as f:
            f.write(enc_token)

    def verify_and_load(self, password: str) -> bool:
        try:
            with open(self.salt_file, "rb") as f:
                salt = f.read()
            key = self._derive_key(password, salt)
            f_temp = Fernet(key)
            
            with open(self.verify_file, "rb") as f:
                enc_token = f.read()
                
            decrypted = f_temp.decrypt(enc_token)
            if decrypted == b"LINUX_ADMIN_AUTH_SUCCESS":
                self.fernet = f_temp
                return True
            return False
        except Exception:
            return False

    def encrypt(self, data: str) -> str:
        if not self.fernet:
            raise Exception("Security module not initialized")
        return self.fernet.encrypt(data.encode()).decode()

    def decrypt(self, encrypted_data: str) -> str:
        if not self.fernet:
            raise Exception("Security module not initialized")
        return self.fernet.decrypt(encrypted_data.encode()).decode()
