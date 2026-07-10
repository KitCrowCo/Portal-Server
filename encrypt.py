# backend/encrypt.py
"""
Symmetric encryption for stored credentials (git tokens, API keys, etc.)
Key derived from SECRET_KEY so nothing extra to manage.
Fernet = AES-128-CBC + HMAC-SHA256. Standard, auditable, reversible.

Usage:
    from .crypto import encrypt_token, decrypt_token
    stored = encrypt_token("ghp_actualtoken")
    plain  = decrypt_token(stored)
"""

import hashlib, base64, os
from cryptography.fernet import Fernet, InvalidToken

_SECRET = os.getenv("SECRET_KEY", "super-secret-fcss-key")

def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(_SECRET.encode()).digest())
    return Fernet(key)

def encrypt_token(plaintext: str) -> str:
    if not plaintext: return ""
    return _fernet().encrypt(plaintext.encode()).decode()

def decrypt_token(ciphertext: str) -> str:
    if not ciphertext: return ""
    return _fernet().decrypt(ciphertext.encode()).decode()
