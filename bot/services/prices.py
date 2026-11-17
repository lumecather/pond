"""Prices from the DEX: quote a small test trade over every Uniswap V2 and V3 pool and take the best.

Why a test trade and not "1 token": a pool with almost no liquidity can show any price, and moving it
costs a few dollars. A 0.05 ETH test trade gets a terrible quote from such a pool, so the deep pool wins.
This is also the route a live trade would take, so rule triggers match live execution.
The pool fee is taken out of the quote, so the price is the market (mid) price: the same number the chart
shows, and demo trades charge their fee once, like a real swap.
Results are cached for a few seconds so pages don't hit the RPC on every view.
"""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from django.core.cache import cache

from . import dex, market
from .chain import ChainError, get_w3

CACHE_SECONDS = 10
PROBE_WEI = 5 * 10**16  # the test trade: 0.05 of the network coin


class PriceUnavailable(Exception):
    pass


def get_price(token) -> Decimal:
    """Price of one token in the network coin."""
    key = f"price:{token.pk}"
    price = cache.get(key)
    if price is None:
        price = _route_price(token)
        if price is None:
            # no Uniswap pool answered (or no DEX configured): use the main pool's price from GeckoTerminal
            price = _market_price(token)
        if price <= 0:
            raise PriceUnavailable("The token price is zero: the pool has no liquidity.")
        cache.set(key, price, CACHE_SECONDS)
    return price


def _route_price(token):
    """Price in the network coin from the best route for a PROBE_WEI buy, or None if no pool answered."""
    net = token.network
    if not net.wrapped_native:
        return None
    try:
        w3 = get_w3(net)
    except ChainError as e:
        raise PriceUnavailable(str(e))
    routes = dex.quotes(net, w3, net.wrapped_native, token.address, PROBE_WEI)
    if not routes:
        return None
    best = routes[0]
    spent = Decimal(PROBE_WEI) / Decimal(10**18) * (1 - _fee(best))  # what reached the pool after its fee
    return spent / (Decimal(best.amount_out) / Decimal(10**token.decimals))


def _fee(route) -> Decimal:
    return Decimal(route.fee) / Decimal(1_000_000)  # 3000 -> 0.003


def _market_price(token) -> Decimal:
    try:
        usd = market.pool_info(token).get("price_usd")
    except market.MarketUnavailable as e:
        raise PriceUnavailable(str(e))
    if not usd:
        raise PriceUnavailable("Couldn't get the token price.")
    return Decimal(str(usd)) / native_usd(token.network)


def native_usd(network) -> Decimal:
    """Price of the network coin in dollars (via the network's stablecoin)."""
    key = f"native_usd:{network.pk}"
    price = cache.get(key)
    if price is None:
        if not network.stable_address:
            raise PriceUnavailable(f"No stablecoin is configured for {network.name}.")
        try:
            w3 = get_w3(network)
        except ChainError as e:
            raise PriceUnavailable(str(e))
        routes = dex.quotes(network, w3, network.wrapped_native, network.stable_address, 10**18)
        if not routes:
            raise PriceUnavailable("Couldn't get a price: the network is not answering.")
        price = Decimal(routes[0].amount_out) / Decimal(10**network.stable_decimals) / (1 - _fee(routes[0]))
        cache.set(key, price, CACHE_SECONDS)
    return price


def get_price_usd(token) -> Decimal:
    return get_price(token) * native_usd(token.network)


def warm(tokens) -> None:
    """Fetch the prices of several tokens at the same time, so a page with many positions doesn't wait
    for them one after another. Errors are ignored here: the caller asks again and shows them."""
    tokens = list(tokens)
    for t in tokens:
        t.network  # load from the database here, not inside the threads
    missing = [t for t in tokens if cache.get(f"price:{t.pk}") is None]
    if len(missing) < 2:
        return
    with ThreadPoolExecutor(max_workers=min(6, len(missing))) as pool:
        list(pool.map(_try_price, missing))


def _try_price(token):
    try:
        get_price(token)
    except Exception:
        pass
