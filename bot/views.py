from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .context import current_mode, current_network
from .forms import RuleForm
from .models import Mode, Network, Order, Rule, Side, Token, TradingWallet
from .services import chain, config, crypto, live, market, prices, trading, vault


def _tokens(user, network):
    """The network's verified tokens plus the ones the user added by address."""
    return Token.objects.filter(network=network).filter(Q(is_verified=True) | Q(added_by=user))


def _decimal(raw):
    """A number typed by the user. A comma also works as the decimal point."""
    try:
        value = Decimal(str(raw or "").replace(",", ".").replace(" ", ""))
    except InvalidOperation:
        return None
    return value if value.is_finite() else None  # "NaN" and "Infinity" parse, but can't be compared


def _price_info(token):
    """Token price for display; on failure, the error text instead of a price."""
    info = {"price": None, "price_usd": None, "error": ""}
    try:
        info["price"] = prices.get_price(token)
        info["price_usd"] = info["price"] * prices.native_usd(token.network)
    except prices.PriceUnavailable as e:
        info["error"] = "" if info["price"] else str(e)
    return info


def home(request):
    return redirect("dashboard")


@login_required
def dashboard(request):
    network, _ = current_network(request)
    ctx = {"tab": "pond"}
    mode = current_mode(request)
    ctx["need_rpc"] = bool(network) and not config.rpc_url(network)
    if network:
        if mode == Mode.LIVE:
            live.refresh_pending(request.user)
            try:
                ctx["p"] = live.portfolio(request.user, network, _tokens(request.user, network))
            except live.LiveError as e:
                ctx["live_error"] = str(e)
        else:
            ctx["p"] = trading.portfolio(request.user, network)
        ctx["rules"] = request.user.rules.filter(is_active=True, mode=mode, token__network=network).select_related("token")[:5]
        ctx["orders"] = request.user.orders.filter(mode=mode, token__network=network).select_related("token")[:5]
    return render(request, "dashboard.html", ctx)


@login_required
def trade(request):
    network, _ = current_network(request)
    tokens = _tokens(request.user, network) if network else Token.objects.none()

    if request.method == "POST":
        token = get_object_or_404(tokens, pk=request.POST.get("token"))
        side = request.POST.get("side")
        if side not in Side.values:
            return redirect("trade")
        mode = current_mode(request)
        if mode == Mode.LIVE and request.POST.get("confirm") != "1":
            messages.error(request, "Not sent: in live mode a trade has to be confirmed with a second click.")
            return redirect(f"/trade/?token={token.pk}")
        order = trading.execute_order(
            request.user, token, side, mode=mode,
            amount_native=_decimal(request.POST.get("amount")),
            sell_percent=_decimal(request.POST.get("percent")),
        )
        if order.status == Order.Status.FILLED:
            verb = "Bought" if side == Side.BUY else "Sold"
            messages.success(request, f"{verb} {order.amount_token.normalize():f} {token.symbol} for {order.amount_native.normalize():f} {network.native_symbol}.")
        elif order.status == Order.Status.PENDING:
            messages.success(request, "Trade sent and waiting to be included in a block. The result will appear in History.")
        else:
            messages.error(request, order.error)
        return redirect(f"/trade/?token={token.pk}")

    # the page remembers the last token you opened, so coming back to Trade doesn't jump to the first one
    key = f"trade_token:{network.pk}" if network else "trade_token"
    token = (tokens.filter(pk=request.GET.get("token") or 0).first()
             or tokens.filter(pk=request.session.get(key) or 0).first() or tokens.first())
    if token:
        request.session[key] = token.pk
    ctx = {"tab": "trade", "tokens": tokens, "token": token, "limit": None}
    if token:
        ctx["info"] = _price_info(token)
        if current_mode(request) == Mode.LIVE:
            ctx["limit"] = config.live_limit()
            try:
                ctx["have_token"] = live.token_amount(request.user, token)
                ctx["have_native"] = live.native_amount(request.user, network)
            except Exception as e:
                ctx["have_token"] = ctx["have_native"] = 0
                ctx["live_error"] = str(e) if isinstance(e, live.LiveError) else "Couldn't read the wallet balance: the network is not answering."
            if not token.is_verified:
                ctx["live_error"] = "Live mode only trades verified tokens for now."
        else:
            ctx["have_token"] = trading.paper_token_amount(request.user, token)
            ctx["have_native"] = trading.paper_native(request.user, network).amount
        try:
            ctx["market"] = market.pool_info(token)
        except market.MarketUnavailable as e:
            ctx["market_error"] = str(e)
    return render(request, "trade.html", ctx)


@login_required
def price_data(request):
    """The token's current price: the trade page polls it every few seconds."""
    network, _ = current_network(request)
    token = _tokens(request.user, network).filter(pk=request.GET.get("token") or 0).first() if network else None
    if not token:
        return JsonResponse({"ok": False, "error": "Token not found."}, status=404)
    info = _price_info(token)
    if info["price"] is None:
        return JsonResponse({"ok": False, "error": info["error"]})
    return JsonResponse({
        "ok": True, "price": float(info["price"]),
        "price_usd": float(info["price_usd"]) if info["price_usd"] is not None else None,
    })


@login_required
def tokens(request):
    """Market: every token on the network grouped by category, search, trending tokens and adding by address."""
    network, _ = current_network(request)
    items = list(_tokens(request.user, network)) if network else []
    if current_mode(request) == Mode.LIVE:
        try:
            held = {r["token"].pk for r in live.portfolio(request.user, network, items)["positions"]} if network else set()
        except Exception:
            held = set()
    else:
        held = set(request.user.paper_balances.filter(token__isnull=False, amount__gt=0).values_list("token_id", flat=True))
    groups = [{"title": "Your positions", "tokens": [t for t in items if t.pk in held]}]
    for value, label in Token.Category.choices:
        groups.append({"title": label, "tokens": [t for t in items if t.is_verified and t.category == value]})
    groups.append({"title": "Added by you (not verified)", "tokens": [t for t in items if not t.is_verified]})
    known = {t.address.lower() for t in items}
    trending = [t for t in market.trending(network) if t["address"] not in known] if network else []
    return render(request, "tokens.html", {
        "tab": "trade", "groups": [g for g in groups if g["tokens"]], "trending": trending, "count": len(items),
    })


@login_required
@require_POST
def demo_reset(request):
    trading.reset_paper(request.user)
    messages.success(request, "Demo restarted: your balance is back to the start and rules are paused.")
    return redirect("dashboard")


@login_required
def chart_data(request):
    """Data for the chart: candles, the user's rule levels and their trades in this token."""
    network, _ = current_network(request)
    token = _tokens(request.user, network).filter(pk=request.GET.get("token") or 0).first() if network else None
    if not token:
        return JsonResponse({"ok": False, "error": "Token not found."}, status=404)
    try:
        rows = market.candles(token, request.GET.get("tf", "1h"))
    except market.MarketUnavailable as e:
        return JsonResponse({"ok": False, "error": str(e)})

    mode = current_mode(request)
    levels = [
        {"price": float(r.trigger_price_usd), "kind": r.action, "title": "buy" if r.action == Side.BUY else f"sell {r.sell_percent} %"}
        for r in request.user.rules.filter(token=token, is_active=True, mode=mode)
    ]
    orders = list(request.user.orders.filter(token=token, mode=mode, status=Order.Status.FILLED, price_usd__isnull=False).order_by("created_at"))
    # average entry price of what was bought and not sold yet
    amount = cost = 0.0
    for o in orders:
        if o.side == Side.BUY:
            amount += float(o.amount_token)
            cost += float(o.amount_token) * float(o.price_usd)
        elif amount > 0:
            left = max(amount - float(o.amount_token), 0.0)
            cost *= left / amount
            amount = left
    if amount > 0 and cost > 0:
        levels.append({"price": cost / amount, "kind": "avg", "title": "my entry"})
    trades = [{"time": int(o.created_at.timestamp()), "side": o.side} for o in orders]
    return JsonResponse({"ok": True, "candles": rows, "levels": levels, "trades": trades})


@login_required
@require_POST
def token_add(request):
    network, _ = current_network(request)
    try:
        data = chain.read_token(network, request.POST.get("address", "").strip())
    except chain.ChainError as e:
        messages.error(request, str(e))
        return redirect("tokens")
    token, created = Token.objects.get_or_create(
        network=network, address=data["address"],
        defaults={"symbol": data["symbol"], "name": data["name"], "decimals": data["decimals"], "added_by": request.user},
    )
    if not created and not token.is_verified and token.added_by_id is None:
        token.added_by = request.user  # it was removed earlier and kept only for the trade history
        token.save(update_fields=["added_by"])
        created = True
    if created:
        messages.success(request, f"{token.symbol} added. It is not verified: see the guide on scam tokens.")
    return redirect(f"/trade/?token={token.pk}")


@login_required
@require_POST
def token_remove(request, pk):
    """Remove a token the user added. One that has trades is only hidden, so the history stays intact."""
    token = get_object_or_404(Token, pk=pk, is_verified=False, added_by=request.user)
    request.user.rules.filter(token=token).update(is_active=False)
    if token.order_set.exists():
        token.added_by = None
        token.save(update_fields=["added_by"])
    else:
        token.delete()
    messages.success(request, f"{token.symbol} removed from your list.")
    return redirect("tokens")


@login_required
def rules(request):
    network, _ = current_network(request)
    mode = current_mode(request)
    tokens = _tokens(request.user, network) if network else Token.objects.none()
    if mode == Mode.LIVE:
        tokens = tokens.filter(is_verified=True)  # live mode only trades verified tokens
    if request.method == "POST":
        post = request.POST.copy()
        for f in ("trigger_price_usd", "amount_native"):
            post[f] = post.get(f, "").replace(",", ".").replace(" ", "")
        form = RuleForm(post, tokens=tokens, limit=config.live_limit() if mode == Mode.LIVE else None)
        if form.is_valid():
            rule = form.save(commit=False)
            rule.user = request.user
            rule.mode = mode
            rule.save()
            messages.success(request, "Rule enabled. The bot is watching the price.")
            return redirect("rules")
    else:
        # the chart sends ?token=&price=&trigger=, so prefill the form with them
        trigger = request.GET.get("trigger") if request.GET.get("trigger") in Rule.Trigger.values else "below"
        initial = {"trigger": trigger, "action": "buy", "token": tokens.filter(pk=request.GET.get("token") or 0).first()}
        price = _decimal(request.GET.get("price"))
        if price and price > 0:
            initial["trigger_price_usd"] = price.normalize()
        form = RuleForm(tokens=tokens, initial=initial)
    items = request.user.rules.filter(mode=mode, token__network=network).select_related("token").prefetch_related("order_set") if network else []
    return render(request, "rules.html", {"tab": "rules", "form": form, "rules": items, "tokens": tokens})


@login_required
@require_POST
def rule_toggle(request, pk):
    rule = get_object_or_404(Rule, pk=pk, user=request.user)
    rule.is_active = not rule.is_active
    if rule.is_active:
        rule.last_fired = None  # re-enabled by hand: check it right away, without the cooldown
    rule.save(update_fields=["is_active", "last_fired"])
    return redirect("rules")


@login_required
@require_POST
def rule_delete(request, pk):
    get_object_or_404(Rule, pk=pk, user=request.user).delete()
    return redirect("rules")


@login_required
def wallet(request):
    network, _ = current_network(request)
    w = TradingWallet.objects.filter(user=request.user).first()
    ctx = {"tab": "wallet", "wallet": w}
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create" and not w:
            crypto.create_wallet(request.user)
            messages.success(request, "Trading wallet created.")
            return redirect("wallet")
        if action == "import" and not w:
            try:
                crypto.import_wallet(request.user, request.POST.get("private_key", ""))
                messages.success(request, "Wallet imported and encrypted with your password.")
            except crypto.ImportError_ as e:
                messages.error(request, str(e))
            return redirect("wallet")
        if action == "export" and w:
            if not vault.check(request.POST.get("password", "")):
                messages.error(request, "Wrong password: the key was not shown.")
                return redirect("wallet")
            ctx["private_key"] = crypto.private_key(w)
        if action == "withdraw" and w and network:
            token = _tokens(request.user, network).filter(pk=request.POST.get("token") or 0).first()
            try:
                tx_hash = live.withdraw(request.user, network, token)
                to = config.withdraw_address()
                messages.success(request, f"Transfer sent to {to[:6]}…{to[-4:]}. Hash: {tx_hash}")
            except Exception as e:
                messages.error(request, str(e) if isinstance(e, live.LiveError) else f"Transfer not sent: {str(e)[:150]}")
            return redirect("wallet")
    ctx["withdraw_to"] = config.withdraw_address()
    if w and network:
        ctx["limit"] = config.live_limit()
        try:
            ctx["p"] = live.portfolio(request.user, network, _tokens(request.user, network))
        except Exception:
            ctx["balance_error"] = "Couldn't read the balances: the network is not answering."
    return render(request, "wallet.html", ctx)


@login_required
def history(request):
    network, _ = current_network(request)
    live.refresh_pending(request.user)
    orders = request.user.orders.filter(token__network=network).select_related("token__network")[:200] if network else []
    return render(request, "history.html", {"tab": "pond", "orders": orders})


@login_required
@require_POST
def set_network(request, slug):
    get_object_or_404(Network, slug=slug, is_active=True)
    request.session["network"] = slug
    return redirect(request.POST.get("next") or "dashboard")


@login_required
@require_POST
def toggle_pro(request):
    request.user.pro_mode = not request.user.pro_mode
    request.user.save(update_fields=["pro_mode"])
    return redirect(request.POST.get("next") or "dashboard")


@login_required
@require_POST
def set_mode(request, mode):
    if mode == "live" and not request.user.live_enabled:
        messages.error(request, "Live trading is off. Turn it on in Settings.")
    else:
        request.session["mode"] = "live" if mode == "live" else "paper"
    return redirect(request.POST.get("next") or "dashboard")
