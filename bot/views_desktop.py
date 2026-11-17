"""App screens: launch login, password, settings."""
import secrets
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from web3 import Web3

from users.models import User

from .models import Network, Token, TradingWallet
from .services import chain, config, vault

LOCAL_USER = "local"


def start(request):
    """The app window opens this link with the launch token and gets in without an account password."""
    token = request.GET.get("token", "")
    if not settings.DESKTOP_TOKEN or not secrets.compare_digest(token, settings.DESKTOP_TOKEN):
        return render(request, "desktop/closed.html", status=403)
    user, created = User.objects.get_or_create(username=LOCAL_USER, defaults={"is_staff": True, "is_superuser": True})
    if created:
        user.set_unusable_password()
        user.save()
    login(request, user)
    return redirect("dashboard")


def setup(request):
    """First launch: choose a password."""
    if vault.is_set():
        return redirect("dashboard")
    error = ""
    if request.method == "POST":
        password, repeat = request.POST.get("password", ""), request.POST.get("repeat", "")
        if len(password) < vault.MIN_LENGTH:
            error = f"The password must be at least {vault.MIN_LENGTH} characters."
        elif password != repeat:
            error = "The passwords don't match."
        elif not request.POST.get("understood"):
            error = "Tick the box to confirm you understand the password can't be recovered."
        else:
            vault.create(password)
            messages.success(request, "Password set. Now paste an RPC URL: without it the app can't see prices.")
            return redirect("app_settings")
    return render(request, "desktop/setup.html", {"bare": True, "error": error, "min_length": vault.MIN_LENGTH})


def unlock(request):
    if vault.is_unlocked():
        return redirect("dashboard")
    error = ""
    if request.method == "POST":
        if vault.unlock(request.POST.get("password", "")):
            return redirect("dashboard")
        error = "Wrong password."
    return render(request, "desktop/unlock.html", {"bare": True, "error": error, "data_dir": settings.DATA_DIR})


@require_POST
def lock(request):
    vault.lock()
    return redirect("unlock")


def _decimal(raw):
    try:
        value = Decimal(str(raw).replace(",", ".").replace(" ", ""))
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def app_settings(request):
    user = request.user
    networks = list(Network.objects.filter(is_active=True))
    if request.method == "POST":
        action = request.POST.get("action")
        if action in ("save_rpc", "test_rpc"):
            net = next((n for n in networks if n.slug == request.POST.get("network")), None)
            if net:
                url = request.POST.get("url", "").strip()
                if action == "save_rpc":
                    config.set_rpc_url(net, url)
                    chain._w3.cache_clear()
                try:
                    info = chain.probe(url or config.rpc_url(net))
                    if net.chain_id and info["chain_id"] != net.chain_id:
                        messages.error(request, f"{net.name}: the node answers, but it is a different network (chain ID {info['chain_id']}, "
                                                f"expected {net.chain_id}). You may have picked a testnet.")
                    else:
                        saved = "Saved. " if action == "save_rpc" else ""
                        messages.success(request, f"{saved}{net.name}: the node works, latest block {info['block']}.")
                except chain.ChainError as e:
                    messages.error(request, f"{net.name}: {e}")
        elif action == "trading":
            ok = True
            limit = _decimal(request.POST.get("limit", ""))
            if limit is None or limit <= 0:
                messages.error(request, "The buy limit must be a number above zero.")
                ok = False
            slip = _decimal(request.POST.get("slippage", ""))
            if slip is None or not Decimal("0.1") <= slip <= Decimal(20):
                messages.error(request, "Slippage tolerance must be between 0.1 and 20 %.")
                ok = False
            address = request.POST.get("withdraw", "").strip()
            if address and not Web3.is_address(address):
                messages.error(request, "The withdrawal address doesn't look like a wallet address.")
                ok = False
            elif address and TradingWallet.objects.filter(address__iexact=address).exists():
                messages.error(request, "That is the trading wallet itself. Use your main wallet's address.")
                ok = False
            elif address and Token.objects.filter(address__iexact=address).exists():
                messages.error(request, "That is a token contract, not a wallet: money sent there is lost.")
                ok = False
            enable = bool(request.POST.get("live"))
            if enable and not user.live_enabled and not request.POST.get("live_understood"):
                messages.error(request, "To turn on live trading, tick the box confirming you understand the risk.")
                ok = False
            if ok:
                config.put(config.LIVE_LIMIT, str(limit.normalize()))
                config.put(config.WITHDRAW_ADDRESS, Web3.to_checksum_address(address) if address else "")
                user.slippage_bps = int(slip * 100)
                user.live_enabled = enable
                user.save(update_fields=["slippage_bps", "live_enabled"])
                if not enable:
                    request.session["mode"] = "paper"
                messages.success(request, "Trading settings saved.")
        elif action == "password":
            old, new, repeat = (request.POST.get(k, "") for k in ("old", "new", "repeat"))
            if len(new) < vault.MIN_LENGTH:
                messages.error(request, f"The new password must be at least {vault.MIN_LENGTH} characters.")
            elif new != repeat:
                messages.error(request, "The new passwords don't match.")
            elif not vault.change(old, new):
                messages.error(request, "The current password is wrong.")
            else:
                messages.success(request, "Password changed.")
        return redirect("app_settings")

    rows = []
    for net in networks:
        url = config.rpc_url(net)
        rows.append({"net": net, "url": url, "from_env": bool(url) and not config.get(f"rpc:{net.rpc_env}")})
    return render(request, "desktop/settings.html", {
        "tab": "settings", "rows": rows,
        "limit": config.live_limit(), "slippage": Decimal(user.slippage_bps) / 100,
        "withdraw": config.get(config.WITHDRAW_ADDRESS), "data_dir": settings.DATA_DIR,
        "first": not any(r["url"] for r in rows),
    })
