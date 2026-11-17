"""Values the user sets on the Settings screen."""
import os
from decimal import Decimal, InvalidOperation

from django.conf import settings

from bot.models import AppSetting

LIVE_LIMIT = "live_limit"
WITHDRAW_ADDRESS = "withdraw_address"


def get(key: str, default: str = "") -> str:
    row = AppSetting.objects.filter(key=key).first()
    return row.value if row else default


def put(key: str, value: str):
    AppSetting.objects.update_or_create(key=key, defaults={"value": value})


def rpc_url(network) -> str:
    """The network's RPC URL: from Settings first, then from an environment variable with the same name."""
    return get(f"rpc:{network.rpc_env}") or os.getenv(network.rpc_env, "")


def set_rpc_url(network, url: str):
    put(f"rpc:{network.rpc_env}", url)


def live_limit() -> Decimal:
    """The cap for a single buy in live mode, in the network's coin."""
    try:
        return Decimal(get(LIVE_LIMIT) or settings.LIVE_MAX_TRADE_NATIVE)
    except InvalidOperation:
        return Decimal(settings.LIVE_MAX_TRADE_NATIVE)


def withdraw_address(user=None) -> str:
    """Where the Withdraw buttons send money: the user's main wallet, set in Settings."""
    return get(WITHDRAW_ADDRESS)
