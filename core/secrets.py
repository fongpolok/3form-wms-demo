"""
Encrypt API keys and ERP passwords before they are stored in the database
(Fernet: AES-128-CBC + HMAC). The key lives in .env as INTEGRATION_KEY.
Secrets are never sent back to the browser; screens only show the last 4 characters.
"""
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("app")


class SecretError(Exception):
    pass


def _fernet():
    key = os.environ.get("INTEGRATION_KEY", "")
    if not key:
        raise SecretError("INTEGRATION_KEY is missing from .env, so secrets cannot be stored.")
    return Fernet(key.encode())


def encrypt(plain):
    return _fernet().encrypt(plain.encode()).decode() if plain else ""


def decrypt(token):
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        logger.error("Stored secret cannot be decrypted (INTEGRATION_KEY changed?)")
        raise SecretError("A stored secret cannot be read. It was saved with a different INTEGRATION_KEY; please re-enter it.")


def mask(plain):
    return f"••••{plain[-4:]}" if plain else ""
