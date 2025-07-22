import os
import pickle
from pathlib import Path
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
import base64

class SecureObjectStore:
    def __init__(self, password: str, key_dir: str = "~/.secure_object_store"):
        self.backend = default_backend()
        self.key_dir = Path(os.path.expanduser(key_dir))
        self.salt_file = self.key_dir / "salt.bin"
        self.key = self._derive_key(password)

    def _derive_key(self, password: str) -> bytes:
        """Derives a 256-bit AES key from the password using PBKDF2-HMAC-SHA256."""
        self.key_dir.mkdir(parents=True, exist_ok=True)
        if not self.salt_file.exists():
            salt = os.urandom(16)
            with open(self.salt_file, "wb") as f:
                f.write(salt)
        else:
            with open(self.salt_file, "rb") as f:
                salt = f.read()

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # AES-256
            salt=salt,
            iterations=100_000,
            backend=self.backend
        )
        return kdf.derive(password.encode())

    def encrypt(self, obj) -> bytes:
        """Encrypt a Python object using AES-256-GCM."""
        data = pickle.dumps(obj)
        iv = os.urandom(12)  # 96-bit IV recommended for GCM
        aesgcm = AESGCM(self.key)
        ciphertext = aesgcm.encrypt(iv, data, None)
        return iv + ciphertext  # prepend IV

    def decrypt(self, encrypted_data: bytes):
        """Decrypt the AES-256-GCM encrypted object."""
        iv = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        aesgcm = AESGCM(self.key)
        decrypted = aesgcm.decrypt(iv, ciphertext, None)
        return pickle.loads(decrypted)
