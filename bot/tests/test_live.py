"""Live-mode tests on a real in-memory EVM (eth-tester).

Instead of Uniswap they use test contracts from bot/testdata/Mocks.sol with the same function signatures
and a fixed rate. The whole path is checked: quote, approval, simulation, signing, sending, receipt.
Needs requirements-dev.txt; without it these tests are skipped.
"""
import json
from decimal import Decimal
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.test import TestCase, override_settings
from web3 import Web3

from bot.models import Network, Order, Rule, Token
from bot.services import config, crypto, dex, engine, live, prices, trading
from users.models import User

from .base import AppTestCase

try:
    import eth_tester  # noqa: F401
    HAVE_TESTER = True
except ImportError:
    HAVE_TESTER = False

MOCKS = json.loads((Path(__file__).parent.parent / "testdata" / "mocks.json").read_text())
ETH = 10**18


class SelectorTests(TestCase):
    """Our ABIs must produce the same selectors as the real Uniswap and Multicall3 contracts."""

    def test_selectors(self):
        w3 = Web3()
        a, b = "0x" + "11" * 20, "0x" + "22" * 20
        a, b = Web3.to_checksum_address(a), Web3.to_checksum_address(b)
        v2 = w3.eth.contract(abi=dex.V2_ABI)
        v3 = w3.eth.contract(abi=dex.V3_ROUTER_ABI)
        expected = {
            v2.encode_abi("swapExactETHForTokensSupportingFeeOnTransferTokens", args=[1, [a, b], a, 1]): "0xb6f9de95",
            v2.encode_abi("swapExactTokensForETHSupportingFeeOnTransferTokens", args=[1, 1, [a, b], a, 1]): "0x791ac947",
            v2.encode_abi("getAmountsOut", args=[1, [a, b]]): "0xd06ca61f",
            v3.encode_abi("exactInputSingle", args=[(a, b, 500, a, 1, 1, 0)]): "0x04e45aaf",
            v3.encode_abi("unwrapWETH9", args=[1, a]): "0x49404b7c",
            v3.encode_abi("multicall", args=[1, [b"\x00"]]): "0x5ae401dc",
            w3.eth.contract(abi=dex.V3_QUOTER_ABI).encode_abi("quoteExactInputSingle", args=[(a, b, 1, 500, 0)]): "0xc6a5026a",
            w3.eth.contract(abi=dex.MULTICALL_ABI).encode_abi("aggregate3", args=[[(a, True, b"")]]): "0x82ad56cb",
            w3.eth.contract(abi=dex.ERC20_ABI).encode_abi("approve", args=[a, 1]): "0x095ea7b3",
            w3.eth.contract(abi=dex.ERC20_ABI).encode_abi("transfer", args=[a, 1]): "0xa9059cbb",
        }
        for data, selector in expected.items():
            self.assertEqual(data[:10], selector)


@skipUnless(HAVE_TESTER, "eth-tester missing: pip install -r requirements-dev.txt")
@override_settings(LIVE_MAX_TRADE_NATIVE="0.05")
class LiveTradingTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.w3 = w3 = Web3(Web3.EthereumTesterProvider())
        self.boss = w3.eth.accounts[0]

        def deploy(name, *args, value=0):
            c = w3.eth.contract(abi=MOCKS[name]["abi"], bytecode=MOCKS[name]["bytecode"])
            receipt = w3.eth.wait_for_transaction_receipt(c.constructor(*args).transact({"from": self.boss, "value": value}))
            return w3.eth.contract(address=receipt["contractAddress"], abi=MOCKS[name]["abi"])

        self.coin = deploy("MockToken")
        weth = deploy("MockToken").address  # only the "WETH" address is needed
        self.v2 = deploy("MockV2Router", weth, 1000, value=5 * ETH)   # 1 ETH = 1000 tokens
        self.v3 = deploy("MockV3", weth, 1100, value=5 * ETH)         # the 0.05 % pool has a better rate: 1100
        for router in (self.v2, self.v3):
            self.coin.functions.transfer(router.address, 10**24).transact({"from": self.boss})

        self.net = Network.objects.create(
            name="Test", slug="testnet", chain_id=w3.eth.chain_id, rpc_env="X", native_symbol="ETH",
            router_address=self.v2.address, wrapped_native=weth, v3_router=self.v3.address, v3_quoter=self.v3.address,
        )
        self.token = Token.objects.create(network=self.net, address=self.coin.address, symbol="MOCK", decimals=18, is_verified=True)
        self.user.live_enabled = True
        self.user.save()
        self.home = w3.eth.accounts[1]  # the user's main wallet, set as the withdrawal address
        config.put(config.WITHDRAW_ADDRESS, self.home)
        self.wallet = crypto.create_wallet(self.user)
        w3.eth.send_transaction({"from": self.boss, "to": self.wallet.address, "value": ETH})

        for target, value in (("bot.services.live._w3", lambda n: w3), ("bot.services.chain.get_w3", lambda n: w3),
                              ("bot.services.prices.get_price", lambda t: Decimal("0.001")),
                              ("bot.services.prices.native_usd", lambda n: Decimal("3000")), ("bot.services.live.time.sleep", lambda s: None)):
            p = patch(target, side_effect=value)
            p.start()
            self.addCleanup(p.stop)

    def coins(self, address=None):
        return self.coin.functions.balanceOf(address or self.wallet.address).call()

    def buy(self, amount="0.01", user=None):
        return trading.execute_order(user or self.user, self.token, "buy", amount_native=Decimal(amount), mode="live")

    def test_buy_takes_best_route_v3(self):
        order = self.buy()
        self.assertEqual((order.status, order.error), ("filled", ""))
        self.assertEqual(self.coins(), 11 * ETH)                      # 0.01 ETH * 1100: the V3 0.05 % pool
        self.assertEqual(order.amount_token, Decimal(11))
        self.assertTrue(order.tx_hash.startswith("0x") and len(order.tx_hash) == 66)
        self.assertGreater(order.gas_native, 0)
        self.assertEqual(self.w3.eth.get_transaction(order.tx_hash)["to"], self.v3.address)

    def test_sell_half_with_approve_and_unwrap(self):
        self.buy()
        before = self.w3.eth.get_balance(self.wallet.address)
        order = trading.execute_order(self.user, self.token, "sell", sell_percent=50, mode="live")
        self.assertEqual((order.status, order.error), ("filled", ""))
        self.assertEqual(self.coins(), 55 * ETH // 10)                # 5.5 tokens left
        # for selling V2 is better: 5.5 / 1000 = 0.0055 vs 5.5 / 1100 = 0.005 on V3
        self.assertEqual(order.amount_native, Decimal("0.0055"))
        self.assertEqual(self.w3.eth.get_transaction(order.tx_hash)["to"], self.v2.address)
        gained = self.w3.eth.get_balance(self.wallet.address) - before
        self.assertTrue(45 * ETH // 10000 < gained < 55 * ETH // 10000)  # 0.0055 minus gas for the approval and the swap
        self.assertEqual(self.coin.functions.allowance(self.wallet.address, self.v2.address).call(), 0)  # the approval was used up exactly

    def test_sell_through_v3_unwraps_to_eth(self):
        Network.objects.filter(pk=self.net.pk).update(router_address="")   # no V2, so only V3 is left
        self.token.refresh_from_db()
        self.buy()
        order = trading.execute_order(self.user, self.token, "sell", sell_percent=100, mode="live")
        self.assertEqual((order.status, order.error), ("filled", ""))
        # for selling the 0.3 % pool is better (rate 1078): 11 / 1078; the wallet got ETH, not WETH
        self.assertAlmostEqual(float(order.amount_native), 11 / 1078, places=12)
        self.assertEqual(self.w3.eth.get_transaction(order.tx_hash)["to"], self.v3.address)
        self.assertEqual(self.coins(), 0)

    def test_price_comes_from_the_best_route(self):
        # V3 gives 1100 tokens per ETH and V2 only 1000, so the V3 pool (fee 0.05 %) wins.
        # Real pools charge the fee inside the quote, so it is taken back out to get the mid price;
        # the mock pool doesn't charge one, which is why the result is a hair under 1/1100.
        with patch("bot.services.prices.get_w3", return_value=self.w3):
            self.assertEqual(prices._route_price(self.token), Decimal("0.9995") / Decimal(1100))

    def test_v2_only_network(self):
        Network.objects.filter(pk=self.net.pk).update(v3_router="", v3_quoter="")
        self.token.refresh_from_db()
        self.assertEqual(self.buy().status, "filled")
        self.assertEqual(self.coins(), 10 * ETH)                      # V2 rate: 1000
        order = trading.execute_order(self.user, Token.objects.get(pk=self.token.pk), "sell", sell_percent=100, mode="live")
        self.assertEqual((order.status, order.amount_native), ("filled", Decimal("0.01")))
        self.assertEqual(self.coins(), 0)

    def test_guards_send_nothing(self):
        nonce = lambda: self.w3.eth.get_transaction_count(self.wallet.address)
        self.assertIn("limit", self.buy("0.5").error)                 # above the single-buy limit
        stranger = User.objects.create(username="demo-only")
        self.assertIn("Live trading is off", self.buy(user=stranger).error)
        Token.objects.filter(pk=self.token.pk).update(is_verified=False)
        self.token.refresh_from_db()
        self.assertIn("verified tokens", self.buy().error)
        self.assertEqual(nonce(), 0)
        self.assertEqual(Order.objects.filter(status="failed").count(), 3)

    def test_price_moved_is_caught_before_sending(self):
        """The quote promised more than the pool really gives: the simulation catches it and no gas is spent."""
        real = dex.best_route

        def optimistic(*a):
            route = real(*a)
            route.amount_out *= 2
            return route

        before = self.w3.eth.get_balance(self.wallet.address)
        with patch("bot.services.dex.best_route", side_effect=optimistic):
            order = self.buy()
        self.assertEqual(order.status, "failed")
        self.assertIn("nothing was spent", order.error)
        self.assertEqual(self.w3.eth.get_balance(self.wallet.address), before)

    def test_not_enough_for_gas(self):
        poor = User.objects.create(username="poor", live_enabled=True)
        wallet = crypto.create_wallet(poor)
        self.w3.eth.send_transaction({"from": self.boss, "to": wallet.address, "value": ETH // 100})  # exactly the buy amount, nothing for gas
        self.assertIn("including gas", self.buy(user=poor).error)

    def test_withdraw_goes_to_settings_address(self):
        self.buy()
        home = self.home
        live.withdraw(self.user, self.net, self.token)
        self.assertEqual((self.coins(), self.coins(home)), (0, 11 * ETH))
        before = self.w3.eth.get_balance(home)
        live.withdraw(self.user, self.net)
        self.assertGreater(self.w3.eth.get_balance(home) - before, 98 * ETH // 100)
        self.assertLess(self.w3.eth.get_balance(self.wallet.address), ETH // 1000)

    def test_portfolio_and_live_rule(self):
        self.buy()
        p = live.portfolio(self.user, self.net, [self.token])
        self.assertEqual(p["positions"][0]["amount"], Decimal(11))
        Rule.objects.create(user=self.user, token=self.token, trigger="above", trigger_price_usd=Decimal("2"), action="sell", sell_percent=100, mode="live")
        self.assertEqual(engine.check_rules(), 1)                     # the price of $3 is above $2
        self.assertEqual(self.coins(), 0)
        self.assertEqual(Order.objects.filter(source="rule", mode="live", status="filled").count(), 1)

    def test_page_needs_second_click(self):
        session = self.client.session
        session["mode"], session["network"] = "live", "testnet"
        session.save()
        with patch("bot.services.market._get", side_effect=Exception("offline")):
            self.assertContains(self.client.get(f"/trade/?token={self.token.pk}"), "real money")
            self.client.post("/trade/", {"token": self.token.pk, "side": "buy", "amount": "0,01"})
            self.assertEqual(self.coins(), 0)                         # nothing was sent without the confirmation
            self.client.post("/trade/", {"token": self.token.pk, "side": "buy", "amount": "0,01", "confirm": "1"})
            self.assertEqual(self.coins(), 11 * ETH)
            for url in ("/pond/", "/wallet/", "/history/", "/rules/"):
                self.assertEqual(self.client.get(url).status_code, 200, url)
