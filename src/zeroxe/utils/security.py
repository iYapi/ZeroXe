"""Security & Encryption Utilities.

Provides zero-dependency, machine-bound symmetric encryption for sensitive strings
(such as passwords and API tokens) stored in local configuration files.
"""

import base64
import getpass
import hashlib
import os
import socket
import uuid
from typing import Optional

from zeroxe import config


def _derive_machine_key(salt: bytes) -> bytes:
    """Derive a unique 32-byte encryption key bound to the local machine and current user."""
    identifiers = f"{uuid.getnode()}:{socket.gethostname()}:{getpass.getuser()}:{config.APP_NAME}:{config.ORGANIZATION_NAME}"
    return hashlib.pbkdf2_hmac("sha256", identifiers.encode("utf-8"), salt, 100000, dklen=32)


def encrypt_string(plain_text: str) -> str:
    """Encrypt a plaintext string into a machine-bound base64 encoded token."""
    if not plain_text:
        return ""

    salt = os.urandom(16)
    key = _derive_machine_key(salt)
    data = plain_text.encode("utf-8")

    # Generate keystream using SHA-256
    keystream = bytearray()
    counter = 0
    while len(keystream) < len(data):
        keystream.extend(hashlib.sha256(key + counter.to_bytes(4, "big")).digest())
        counter += 1

    # XOR cipher
    encrypted = bytes(b ^ k for b, k in zip(data, keystream[: len(data)]))
    payload = salt + encrypted
    return base64.b64encode(payload).decode("utf-8")


def decrypt_string(encrypted_token: str) -> str:
    """Decrypt a machine-bound base64 encoded token back to plaintext."""
    if not encrypted_token:
        return ""

    try:
        payload = base64.b64decode(encrypted_token.encode("utf-8"))
        if len(payload) < 16:
            return ""

        salt = payload[:16]
        encrypted = payload[16:]
        key = _derive_machine_key(salt)

        keystream = bytearray()
        counter = 0
        while len(keystream) < len(encrypted):
            keystream.extend(hashlib.sha256(key + counter.to_bytes(4, "big")).digest())
            counter += 1

        decrypted = bytes(b ^ k for b, k in zip(encrypted, keystream[: len(encrypted)]))
        return decrypted.decode("utf-8")
    except Exception:
        return ""
