"""Demo trading, rules and pages."""
from decimal import Decimal
from unittest.mock import patch

from bot.models import Order, PaperBalance, Rule, Token
from bot.services import engine, market, trading

from .base import ETH_USD, PRICE, AppTestCase


@patch("bot.services.market._get", side_effect=market.MarketUnavailable("offline test"))
@patch("bot.services.prices.native_usd", return_value=ETH_USD)
@patch("bot.services.prices.get_price", return_value=PRICE)
class PaperTradingTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.token = Token.objects.get(symbol="LINK")

    def test_buy_then_sell(self, *_):
        o = trading.execute_order(self.user, self.token, "buy", amount_native=Decimal("0.5"))
        self.assertEqual(o.status, Order.Status.FILLED)
        self.assertEqual(o.amount_token, Decimal("498.5"))  # 0.5 / 0.001 minus 0.3 %
        self.assertEqual(trading.paper_native(self.user, self.token.network).amount, Decimal("0.5"))

        o = trading.execute_order(self.user, self.token, "sell", sell_percent=50)
        self.assertEqual(o.status, Order.Status.FILLED)
        self.assertEqual(trading.paper_token_amount(self.user, self.token), Decimal("249.25"))

    def test_not_enough_balance(self, *_):
        o = trading.execute_order(self.user, self.token, "buy", amount_native=Decimal("5"))
        self.assertEqual(o.status, Order.Status.FAILED)
        self.assertIn("Not enough", o.error)
        self.assertFalse(PaperBalance.objects.filter(user=self.user, token=self.token, amount__gt=0).exists())

    def test_rule_fires_once(self, *_):
        rule = Rule.objects.create(user=self.user, token=self.token, trigger="below", trigger_price_usd=Decimal("3.5"), action="buy", amount_native=Decimal("0.1"))
        Rule.objects.create(user=self.user, token=self.token, trigger="above", trigger_price_usd=Decimal("10"), action="sell", sell_percent=100)
        self.assertEqual(engine.check_rules(), 1)  # the price is $3: below 3.5 yes, above 10 no
        rule.refresh_from_db()
        self.assertFalse(rule.is_active)
        self.assertEqual(Order.objects.get().source, Order.Source.RULE)
        self.assertEqual(engine.check_rules(), 0)

    def test_pages_open(self, *_):
        for url in ("/", "/pond/", "/trade/", "/tokens/", "/rules/", "/wallet/", "/history/", "/settings/", "/guides/", "/guides/start/", "/admin/"):
            self.assertIn(self.client.get(url).status_code, (200, 302), url)
            self.assertEqual(self.client.get(url, follow=True).status_code, 200, url)
        r = self.client.post("/trade/", {"token": self.token.pk, "side": "buy", "amount": "0.2"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Order.objects.filter(status="filled").count(), 1)
        r = self.client.post("/rules/", {"token": self.token.pk, "trigger": "above", "trigger_price_usd": "4.5", "action": "sell", "sell_percent": "50"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Rule.objects.count(), 1)

    def test_comma_works_as_decimal_point(self, *_):
        self.client.post("/trade/", {"token": self.token.pk, "side": "buy", "amount": "0,2"})
        self.assertEqual(Order.objects.get().amount_native, Decimal("0.2"))

    def test_demo_reset(self, *_):
        trading.execute_order(self.user, self.token, "buy", amount_native=Decimal("0.4"))
        self.client.post("/demo/reset/")
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(trading.paper_native(self.user, self.token.network).amount, Decimal("1"))


@patch("bot.services.market._get", side_effect=market.MarketUnavailable("offline test"))
@patch("bot.services.prices.native_usd", return_value=ETH_USD)
@patch("bot.services.prices.get_price", return_value=PRICE)
class RuleFailureTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.token = Token.objects.get(symbol="LINK")

    def test_failed_rule_retries_then_switches_off(self, *_):
        from datetime import timedelta
        # a stop-loss with nothing to sell: it must not die on the first failure
        rule = Rule.objects.create(user=self.user, token=self.token, trigger="below", trigger_price_usd=Decimal("5"), action="sell", sell_percent=100)
        self.assertEqual(engine.check_rules(), 1)
        rule.refresh_from_db()
        self.assertTrue(rule.is_active)
        self.assertEqual(engine.check_rules(), 0)  # waits RETRY before the next attempt
        with self.assertLogs("pond.engine", "WARNING"):
            for _ in range(2):
                Rule.objects.filter(pk=rule.pk).update(last_fired=rule.last_fired - timedelta(minutes=6))
                rule.refresh_from_db()
                engine.check_rules()
                rule.refresh_from_db()
        self.assertFalse(rule.is_active)  # three failures in a row
        self.assertEqual(Order.objects.filter(rule=rule, status="failed").count(), 3)

    def test_live_rules_wait_while_locked(self, *_):
        from bot.services import vault
        rule = Rule.objects.create(user=self.user, token=self.token, trigger="below", trigger_price_usd=Decimal("5"), action="buy", amount_native=Decimal("0.01"), mode="live")
        vault.lock()
        self.assertEqual(engine.check_rules(), 0)
        rule.refresh_from_db()
        self.assertTrue(rule.is_active)
        self.assertFalse(Order.objects.exists())

    def test_one_broken_rule_does_not_stop_others(self, *_):
        Rule.objects.create(user=self.user, token=self.token, trigger="below", trigger_price_usd=Decimal("5"), action="buy", amount_native=Decimal("0.1"))
        Rule.objects.create(user=self.user, token=self.token, trigger="below", trigger_price_usd=Decimal("6"), action="buy", amount_native=Decimal("0.1"))
        real = trading.execute_order
        calls = []

        def flaky(*a, **kw):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("database is locked")
            return real(*a, **kw)

        with patch("bot.services.engine.execute_order", side_effect=flaky), self.assertLogs("pond.engine", "ERROR"):
            self.assertEqual(engine.check_rules(), 1)
        self.assertEqual(Order.objects.filter(status="filled").count(), 1)

    def test_nan_input_is_rejected_not_crashing(self, *_):
        r = self.client.post("/trade/", {"token": self.token.pk, "side": "buy", "amount": "NaN"}, follow=True)
        self.assertContains(r, "Enter how much")
        r = self.client.post("/trade/", {"token": self.token.pk, "side": "sell", "percent": "nan"}, follow=True)
        self.assertEqual(r.status_code, 200)
        r = self.client.post("/settings/", {"action": "trading", "limit": "NaN", "slippage": "1"}, follow=True)
        self.assertContains(r, "above zero")
