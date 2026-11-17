"""Market data for the chart and the token summary: candles, volume, liquidity.

The source is GeckoTerminal's public API (no key, roughly 30 requests per minute),
so every answer is cached. Prices for trades still come from prices.py.
"""
import requests
from django.core.cache import cache

API = "https://api.geckoterminal.com/api/v2"
# our timeframe code -> (timeframe, aggregate, seconds per candle)
TIMEFRAMES = {"15m": ("minute", 15, 900), "1h": ("hour", 1, 3600), "4h": ("hour", 4, 14400), "1d": ("day", 1, 86400)}
CANDLES = 300
ERROR_TTL = 30  # remember errors briefly too, so we don't hammer the API


class MarketUnavailable(Exception):
    pass


def _get(path: str, params: dict | None = None) -> dict:
    try:
        r = requests.get(API + path, params=params, headers={"accept": "application/json"}, timeout=8)
    except requests.RequestException:
        raise MarketUnavailable("The chart service is not answering.")
    if r.status_code == 429:
        raise MarketUnavailable("Too many requests to the chart service, try again in a minute.")
    if r.status_code != 200:
        raise MarketUnavailable("There is no market data for this token.")
    return r.json()


def _cached(key: str, ttl: int, build):
    hit = cache.get(key)
    if hit is None:
        try:
            hit = {"ok": build()}
            cache.set(key, hit, ttl)
        except MarketUnavailable as e:
            hit = {"error": str(e)}
            cache.set(key, hit, ERROR_TTL)
    if "error" in hit:
        raise MarketUnavailable(hit["error"])
    return hit["ok"]


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pool_info(token) -> dict:
    """The token's main pool: address, liquidity, volume and 24h price change."""
    net = token.network
    if not net.gecko_id:
        raise MarketUnavailable(f"Charts are not set up for {net.name} (the GeckoTerminal ID field in the admin).")

    def build():
        pools = _get(f"/networks/{net.gecko_id}/tokens/{token.address.lower()}/pools", {"page": 1}).get("data") or []
        if not pools:
            raise MarketUnavailable("No pools were found for this token.")
        me = f"{net.gecko_id}_{token.address.lower()}"
        # take the first pool where our token is the base token: its price and change are about our token
        pool = next((p for p in pools if p["relationships"]["base_token"]["data"]["id"] == me), pools[0])
        a = pool["attributes"]
        return {
            "address": a["address"],
            "name": a.get("name", ""),
            "price_usd": _num(a.get("token_price_usd") or a.get("base_token_price_usd")),
            "liquidity_usd": _num(a.get("reserve_in_usd")),
            "volume_24h": _num((a.get("volume_usd") or {}).get("h24")),
            "change_24h": _num((a.get("price_change_percentage") or {}).get("h24")),
            "pools": len(pools),
        }

    return _cached(f"market:pool:{token.pk}", 300, build)


def candles(token, tf: str) -> list[dict]:
    """Candles in dollars, oldest first."""
    if tf not in TIMEFRAMES:
        tf = "1h"
    timeframe, aggregate, seconds = TIMEFRAMES[tf]
    pool = pool_info(token)

    def build():
        data = _get(
            f"/networks/{token.network.gecko_id}/pools/{pool['address']}/ohlcv/{timeframe}",
            {"aggregate": aggregate, "limit": CANDLES, "currency": "usd", "token": token.address.lower()},
        )
        rows = data["data"]["attributes"]["ohlcv_list"]
        return [
            {"time": int(t), "open": o, "high": h, "low": l, "close": c, "volume": v}
            for t, o, h, l, c, v in sorted(rows, key=lambda r: r[0])
        ]

    return _cached(f"market:candles:{token.pk}:{tf}", min(60, seconds // 10), build)


def trending(network, limit: int = 10, min_liquidity: float = 50_000) -> list[dict]:
    """Tokens from pools trending on GeckoTerminal right now. Not a recommendation and not a safety check."""
    if not network.gecko_id:
        return []

    def build():
        skip = {network.wrapped_native.lower(), network.stable_address.lower()}
        seen, out = set(), []
        for pool in _get(f"/networks/{network.gecko_id}/trending_pools", {"page": 1}).get("data") or []:
            a = pool.get("attributes") or {}
            base = pool["relationships"]["base_token"]["data"]["id"].split("_", 1)[-1].lower()
            liquidity = _num(a.get("reserve_in_usd")) or 0
            if base in skip or base in seen or liquidity < min_liquidity:
                continue
            seen.add(base)
            out.append({
                "address": base,
                "symbol": (a.get("name") or "?").split(" / ")[0].strip()[:20],
                "pool": a.get("name", ""),
                "liquidity_usd": liquidity,
                "volume_24h": _num((a.get("volume_usd") or {}).get("h24")),
                "change_24h": _num((a.get("price_change_percentage") or {}).get("h24")),
            })
        return out[:limit]

    try:
        return _cached(f"market:trending:{network.pk}", 300, build)
    except MarketUnavailable:
        return []
