"""Trading wallets: creating, importing and decrypting the private key.

Keys are encrypted with a key derived from the app password (see vault.py).
"""
from eth_account import Account

from bot.models import TradingWallet

from . import vault


def _fernet():
    return vault.fernet()


def _save(user, acct) -> TradingWallet:
    return TradingWallet.objects.create(
        user=user,
        address=acct.address,
        encrypted_key=_fernet().encrypt(acct.key.hex().encode()).decode(),
    )


def create_wallet(user) -> TradingWallet:
    return _save(user, Account.create())


class ImportError_(ValueError):
    pass


def import_wallet(user, private_key: str) -> TradingWallet:
    """Use your own wallet instead of a new one. The key stays on this computer, encrypted."""
    key = private_key.strip()
    if not key.startswith("0x"):
        key = "0x" + key
    try:
        acct = Account.from_key(key)
    except Exception:
        raise ImportError_("That doesn't look like a private key: it should be 64 characters of 0–9 and a–f.")
    if TradingWallet.objects.filter(address=acct.address).exists():
        raise ImportError_("This wallet has already been added.")
    return _save(user, acct)


def private_key(wallet: TradingWallet) -> str:
    key = _fernet().decrypt(wallet.encrypted_key.encode()).decode()
    return key if key.startswith("0x") else "0x" + key
