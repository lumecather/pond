"""The app password.

The encryption key is derived from the password with scrypt. Neither the password nor the key is saved:
only a salt and a check string encrypted with that key are stored. After you enter the password the key
lives in memory while the app is open. Without the password the trading wallet's private key can't be
recovered from the database file.
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken
from django.db import transaction

from bot.models import TradingWallet

from . import config

SALT, CHECK = "vault_salt", "vault_check"
CHECK_TEXT = b"pond-vault-ok"
MIN_LENGTH = 8
_key = None  # the key in process memory, shared by the window and the bot


class Locked(Exception):
    pass


def _derive(password: str, salt: bytes) -> bytes:
    raw = hashlib.scrypt(password.encode(), salt=salt, n=2**15, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=32)
    return base64.urlsafe_b64encode(raw)


def _try(password: str):
    salt = config.get(SALT)
    if not salt:
        return None
    key = _derive(password, base64.b64decode(salt))
    try:
        ok = Fernet(key).decrypt(config.get(CHECK).encode()) == CHECK_TEXT
    except InvalidToken:
        return None
    return key if ok else None


def _store(key: bytes, salt: bytes):
    config.put(SALT, base64.b64encode(salt).decode())
    config.put(CHECK, Fernet(key).encrypt(CHECK_TEXT).decode())


def is_set() -> bool:
    return bool(config.get(SALT))


def is_unlocked() -> bool:
    return _key is not None


def create(password: str):
    global _key
    if is_set():
        raise ValueError("A password is already set.")
    salt = os.urandom(16)
    key = _derive(password, salt)
    _store(key, salt)
    _key = key


def unlock(password: str) -> bool:
    global _key
    key = _try(password)
    if key:
        _key = key
    return key is not None


def check(password: str) -> bool:
    return _try(password) is not None


def lock():
    global _key
    _key = None


def fernet() -> Fernet:
    if _key is None:
        raise Locked("Pond is locked: enter your password.")
    return Fernet(_key)


@transaction.atomic
def change(old: str, new: str) -> bool:
    """Changes the password and re-encrypts every trading wallet key with the new key."""
    global _key
    old_key = _try(old)
    if not old_key:
        return False
    salt = os.urandom(16)
    new_key = _derive(new, salt)
    for wallet in TradingWallet.objects.select_for_update():
        plain = Fernet(old_key).decrypt(wallet.encrypted_key.encode())
        wallet.encrypted_key = Fernet(new_key).encrypt(plain).decode()
        wallet.save(update_fields=["encrypted_key"])
    _store(new_key, salt)
    _key = new_key
    return True
