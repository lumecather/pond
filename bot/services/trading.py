"""Order execution: demo trades are simulated in the database, live ones (live.py) send a real swap."""
from decimal import Decimal

from django.conf import settings
from django.db import transaction

from bot.models import Mode, Order, PaperBalance, Side

from . import dex, live, prices

Q = Decimal("1e-18")


def paper_native(user, network) -> PaperBalance:
    """Demo balance of the network coin; the starting amount is granted on first use."""
    bal, _ = PaperBalance.objects.get_or_create(
        user=user, network=network, token=None, defaults={"amount": Decimal(settings.PAPER_START_BALANCE)}
    )
    return bal


def paper_token_amount(user, token) -> Decimal:
    bal = PaperBalance.objects.filter(user=user, token=token).first()
    return bal.amount if bal else Decimal(0)


def execute_order(user, token, side, *, amount_native=None, sell_percent=None, mode=Mode.PAPER, source=Order.Source.MANUAL, rule=None) -> Order:
    """Always returns an Order: filled, or with an error message."""
    order = Order(user=user, token=token, side=side, mode=mode, source=source, rule=rule, status=Order.Status.FAILED)
    try:
        order.price = prices.get_price(token)
        try:
            order.price_usd = order.price * prices.native_usd(token.network)
        except prices.PriceUnavailable:
            pass
        if mode == Mode.PAPER:
            _execute_paper(order, amount_native, sell_percent)
        else:
            _execute_live(order, amount_native, sell_percent)
    except (prices.PriceUnavailable, TradeError, live.LiveError, dex.DexError) as e:
        _fail(order, str(e))
    except Exception as e:  # the network can answer anything; a failed order is better than a crashed page or bot
        if mode == Mode.PAPER:
            raise
        _fail(order, f"Unexpected error: {e}")
    order.save()
    return order


class TradeError(Exception):
    pass


def _fail(order, text):
    """An error before sending means the order failed. After sending, the transaction is on chain and we wait for its result."""
    if order.tx_hash:
        order.status = Order.Status.PENDING
        order.error = "Transaction sent, waiting for the result."
    else:
        order.status = Order.Status.FAILED
        order.error = text[:255]


@transaction.atomic
def _execute_paper(order, amount_native, sell_percent):
    user, token, net = order.user, order.token, order.token.network
    fee = Decimal(settings.PAPER_FEE)
    paper_native(user, net)
    native = PaperBalance.objects.select_for_update().get(user=user, network=net, token=None)
    tok, _ = PaperBalance.objects.select_for_update().get_or_create(user=user, network=net, token=token)

    if order.side == Side.BUY:
        amount = Decimal(amount_native or 0)
        if amount <= 0:
            raise TradeError("Enter how much to buy for.")
        if amount > native.amount:
            raise TradeError(f"Not enough {net.native_symbol}: the balance is {native.amount.normalize():f}.")
        got = (amount * (1 - fee) / order.price).quantize(Q)
        native.amount -= amount
        tok.amount += got
        order.amount_native, order.amount_token = amount, got
    else:
        percent = int(sell_percent or 0)
        if not 1 <= percent <= 100:
            raise TradeError("Enter what percentage to sell (1–100).")
        sold = (tok.amount * percent / 100).quantize(Q)
        if sold <= 0:
            raise TradeError(f"You have no {token.symbol} to sell.")
        got = (sold * order.price * (1 - fee)).quantize(Q)
        tok.amount -= sold
        native.amount += got
        order.amount_native, order.amount_token = got, sold

    native.save()
    tok.save()
    order.status = Order.Status.FILLED


def _execute_live(order, amount_native, sell_percent):
    live.execute(order, amount_native, sell_percent)


def portfolio(user, network) -> dict:
    """Demo portfolio: the network coin plus positions at current prices."""
    native = paper_native(user, network)
    try:
        usd = prices.native_usd(network)
    except prices.PriceUnavailable:
        usd = None
    rows, total = [], native.amount
    held = list(PaperBalance.objects.filter(user=user, network=network, token__isnull=False, amount__gt=0).select_related("token__network"))
    prices.warm(b.token for b in held)
    for bal in held:
        try:
            price = prices.get_price(bal.token)
            value = bal.amount * price
            total += value
        except prices.PriceUnavailable:
            price = value = None
        rows.append({
            "token": bal.token, "amount": bal.amount, "price": price, "value": value,
            "price_usd": price * usd if price is not None and usd else None,
            "value_usd": value * usd if value is not None and usd else None,
        })
    start = Decimal(settings.PAPER_START_BALANCE)
    return {
        "native": native.amount, "native_usd": native.amount * usd if usd else None,
        "positions": rows, "total": total, "total_usd": total * usd if usd else None,
        "pnl_percent": (total - start) / start * 100, "usd_rate": usd,
    }


def reset_paper(user):
    """Restart the demo: delete demo balances and demo trades. Rules stay but are paused."""
    PaperBalance.objects.filter(user=user).delete()
    Order.objects.filter(user=user, mode=Mode.PAPER).delete()
    user.rules.filter(mode=Mode.PAPER).update(is_active=False)
