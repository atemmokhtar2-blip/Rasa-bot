from __future__ import annotations
import base64
import hashlib
from cryptography.fernet import Fernet

class WebhookSecretCipher:
    def __init__(self, key_material: str):
        key = base64.urlsafe_b64encode(hashlib.sha256(key_material.encode()).digest())
        self._fernet = Fernet(key)
    def encrypt(self, value: str) -> str: return self._fernet.encrypt(value.encode()).decode()
    def decrypt(self, value: str) -> str: return self._fernet.decrypt(value.encode()).decode()
