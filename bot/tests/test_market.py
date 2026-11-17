"""Chart data, token list, price fallback and guides."""
import re
from decimal import Decimal
from unittest.mock import patch

from bot.models import Rule, Token
from bot.services import market, prices, trading
from guides import figures
from guides.models import Guide

from .base import ETH_USD, PRICE, AppTestCase

# GeckoTerminal answers in the shape the API returns them (shortened).
POOLS = {"data": [
    {"attributes": {"address": "0xstlink", "name": "stLINK / LINK", "reserve_in_usd": "500", "volume_usd": {"h24": "1"}, "price_change_percentage": {"h24": "0"}},
     "relationships": {"base_token": {"data": {"id": "eth_0xother"}}}},
    {"attributes": {"address": "0xa6cc", "name": "LINK / WETH 0.3%", "reserve_in_usd": "11316284.38", "volume_usd": {"h24": "834372.7"}, "price_change_percentage": {"h24": "0.33"}},
     "relationships": {"base_token": {"data": {"id": "eth_0x514910771af9ca656af840dff83e8264ecf986ca"}}}},
]}
OHLCV = {"data": {"attributes": {"ohlcv_list": [[1794837600, 9.07, 9.32, 9.07, 9.26, 112553.7], [1794834000, 9.07, 9.08, 9.05, 9.078, 40816.1]]}}}


def fake_api(path, params=None):
    return OHLCV if "/ohlcv/" in path else POOLS


class MarketTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.token = Token.objects.get(symbol="LINK")

    def test_pool_and_candles(self):
        with patch("bot.services.market._get", side_effect=fake_api) as get:
            pool = market.pool_info(self.token)
            self.assertEqual(pool["address"], "0xa6cc")  # the pool where LINK is the base token
            self.assertAlmostEqual(pool["change_24h"], 0.33)
            rows = market.candles(self.token, "1h")
            self.assertEqual([r["time"] for r in rows], [1794834000, 1794837600])  # oldest first
            market.candles(self.token, "1h")
            self.assertEqual(get.call_count, 2)  # the repeat request came from the cache

    @patch("bot.services.prices.native_usd", return_value=ETH_USD)
    @patch("bot.services.prices.get_price", return_value=PRICE)
    def test_chart_api(self, *_):
        trading.execute_order(self.user, self.token, "buy", amount_native=Decimal("0.2"))
        Rule.objects.create(user=self.user, token=self.token, trigger="above", trigger_price_usd=Decimal("12"), action="sell", sell_percent=50)
        with patch("bot.services.market._get", side_effect=fake_api):
            data = self.client.get(f"/api/chart/?token={self.token.pk}&tf=1h").json()
            self.assertEqual(self.client.get(f"/trade/?token={self.token.pk}").status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["candles"]), 2)
        self.assertEqual({l["kind"]: l["price"] for l in data["levels"]}, {"sell": 12.0, "avg": 3.0})
        self.assertEqual(data["trades"][0]["side"], "buy")
        r = self.client.get(f"/rules/?token={self.token.pk}&price=8.5&trigger=below")
        self.assertContains(r, 'value="8.5"')

    def test_market_down_is_not_fatal(self):
        with patch("bot.services.market._get", side_effect=market.MarketUnavailable("no data")), \
             patch("bot.services.prices.get_price", return_value=PRICE), patch("bot.services.prices.native_usd", return_value=ETH_USD):
            self.assertEqual(self.client.get(f"/trade/?token={self.token.pk}").status_code, 200)
            self.assertFalse(self.client.get(f"/api/chart/?token={self.token.pk}").json()["ok"])


class TokensAndGuidesTests(AppTestCase):
    def test_verified_tokens_have_descriptions(self):
        verified = Token.objects.filter(is_verified=True)
        self.assertGreaterEqual(verified.count(), 25)
        self.assertFalse(verified.filter(description="").exists())
        self.assertEqual(Token.objects.get(symbol="FLOKI").decimals, 9)

    def test_market_page_and_trending(self):
        trend = {"data": [{"attributes": {"name": "NEW / WETH", "reserve_in_usd": "900000", "volume_usd": {"h24": "5"}, "price_change_percentage": {"h24": "12"}},
                           "relationships": {"base_token": {"data": {"id": "eth_0x00000000000000000000000000000000000000aa"}}}},
                          {"attributes": {"name": "TINY / WETH", "reserve_in_usd": "100"}, "relationships": {"base_token": {"data": {"id": "eth_0xbb"}}}}]}
        with patch("bot.services.market._get", return_value=trend):
            r = self.client.get("/tokens/")
        self.assertContains(r, "Chainlink")
        self.assertContains(r, "NEW")
        self.assertNotContains(r, "TINY")  # too little liquidity to be listed as trending

    def test_price_falls_back_to_market(self):
        token = Token.objects.get(symbol="ONDO")
        with patch("bot.services.dex.quotes", return_value=[]), patch("bot.services.prices.get_w3"), \
             patch("bot.services.prices.native_usd", return_value=ETH_USD), \
             patch("bot.services.market._get", side_effect=lambda path, params=None: {"data": [{"attributes": {"address": "0xp", "token_price_usd": "1.5"}, "relationships": {"base_token": {"data": {"id": "x"}}}}]}):
            self.assertEqual(prices.get_price(token), Decimal("1.5") / ETH_USD)
            self.assertTrue(self.client.get(f"/api/price/?token={token.pk}").json()["ok"])

    def test_guides_have_pictures(self):
        for slug in ("chart-reading", "candle-models", "patterns"):
            html = self.client.get(f"/guides/{slug}/").content.decode()
            self.assertIn("<svg", html)
            self.assertNotIn("[[fig:", html)
        used = set(re.findall(r"\[\[fig:([\w-]+)\]\]", " ".join(Guide.objects.values_list("body", flat=True))))
        self.assertTrue(used and used <= set(figures.FIGURES))


class AddedTokenTests(AppTestCase):
    def add(self, address):
        data = {"address": address, "symbol": "NEW", "name": "New", "decimals": 18}
        with patch("bot.services.chain.read_token", return_value=data):
            self.client.post("/tokens/add/", {"address": address})
        return Token.objects.get(symbol="NEW")

    def test_remove_added_token(self):
        token = self.add("0x00000000000000000000000000000000000000aa")
        with patch("bot.services.market._get", side_effect=market.MarketUnavailable("offline")), \
             patch("bot.services.prices.get_price", return_value=PRICE), patch("bot.services.prices.native_usd", return_value=ETH_USD):
            self.assertContains(self.client.get(f"/trade/?token={token.pk}"), "Remove from my list")
        self.client.post(f"/tokens/{token.pk}/remove/")
        self.assertFalse(Token.objects.filter(pk=token.pk).exists())

    @patch("bot.services.market._get", side_effect=market.MarketUnavailable("offline"))
    @patch("bot.services.prices.native_usd", return_value=ETH_USD)
    @patch("bot.services.prices.get_price", return_value=PRICE)
    def test_token_with_trades_is_hidden_not_deleted(self, *_):
        token = self.add("0x00000000000000000000000000000000000000bb")
        trading.execute_order(self.user, token, "buy", amount_native=Decimal("0.1"))
        self.client.post(f"/tokens/{token.pk}/remove/")
        token.refresh_from_db()
        self.assertIsNone(token.added_by)                     # kept for the trade history
        self.assertNotContains(self.client.get("/tokens/"), "New</small>")
        verified = Token.objects.get(symbol="LINK")
        self.assertEqual(self.client.post(f"/tokens/{verified.pk}/remove/").status_code, 404)  # verified tokens can't be removed
