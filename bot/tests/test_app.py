"""App access and settings: launch token, password, RPC, trading settings, wallets."""
from decimal import Decimal
from unittest.mock import patch

from django.test import override_settings
from eth_account import Account

from bot.models import AppSetting, Network, Token, TradingWallet
from bot.services import chain, config, crypto, live, trading, vault
from users.models import User

from .base import ETH_USD, PASSWORD, PRICE, AppTestCase


@override_settings(DESKTOP_TOKEN="launch-token")
class FirstLaunchTests(AppTestCase):
    login = False

    def setUp(self):
        vault.lock()
        self.addCleanup(vault.lock)  # no user and no password yet: a fresh install

    def enter(self):
        return self.client.get("/desktop/start/?token=launch-token")

    def test_only_launch_token_lets_in(self):
        self.assertEqual(self.client.get("/pond/").status_code, 403)
        self.assertEqual(self.client.get("/desktop/start/?token=guess").status_code, 403)
        self.assertRedirects(self.enter(), "/pond/", target_status_code=302)
        self.assertRedirects(self.client.get("/pond/"), "/setup/")

    def test_first_run_password(self):
        self.enter()
        r = self.client.post("/setup/", {"password": "short", "repeat": "short", "understood": "1"})
        self.assertContains(r, "at least")
        r = self.client.post("/setup/", {"password": PASSWORD, "repeat": PASSWORD + "!", "understood": "1"})
        self.assertContains(r, "don&#x27;t match")
        r = self.client.post("/setup/", {"password": PASSWORD, "repeat": PASSWORD})
        self.assertContains(r, "can&#x27;t be recovered")
        r = self.client.post("/setup/", {"password": PASSWORD, "repeat": PASSWORD, "understood": "1"})
        self.assertRedirects(r, "/settings/")
        self.assertTrue(vault.is_set() and vault.is_unlocked())
        self.assertNotIn(PASSWORD, " ".join(AppSetting.objects.values_list("value", flat=True)))  # the password is never stored


class PasswordTests(AppTestCase):
    def test_lock_and_unlock(self):
        self.client.post("/lock/")
        self.assertRedirects(self.client.get("/pond/"), "/unlock/")
        self.assertContains(self.client.post("/unlock/", {"password": "wrong password"}), "Wrong password")
        self.assertRedirects(self.client.post("/unlock/", {"password": PASSWORD}), "/pond/")

    def test_wallet_key_needs_password(self):
        wallet = crypto.create_wallet(self.user)
        key = crypto.private_key(wallet)
        self.assertNotIn(key[2:], wallet.encrypted_key)
        # with the app locked the key can't be decrypted, and live mode says so plainly
        vault.lock()
        with self.assertRaises(vault.Locked):
            crypto.private_key(wallet)
        with self.assertRaisesMessage(live.LiveError, "locked"):
            live._account(wallet)
        vault.unlock(PASSWORD)
        r = self.client.post("/wallet/", {"action": "export", "password": "wrong password"}, follow=True)
        self.assertNotContains(r, key)
        with patch("bot.services.live.portfolio", side_effect=live.LiveError("offline")):
            self.assertContains(self.client.post("/wallet/", {"action": "export", "password": PASSWORD}), key)

    def test_change_password_keeps_wallet(self):
        wallet = crypto.create_wallet(self.user)
        key = crypto.private_key(wallet)
        self.client.post("/settings/", {"action": "password", "old": "wrong one!", "new": "new password 1", "repeat": "new password 1"})
        self.assertTrue(vault.check(PASSWORD))
        self.client.post("/settings/", {"action": "password", "old": PASSWORD, "new": "new password 1", "repeat": "new password 1"})
        vault.lock()
        self.assertFalse(vault.unlock(PASSWORD))
        self.assertTrue(vault.unlock("new password 1"))
        wallet.refresh_from_db()
        self.assertEqual(crypto.private_key(wallet), key)


class WalletTests(AppTestCase):
    def test_create_wallet(self):
        self.client.post("/wallet/", {"action": "create"})
        wallet = TradingWallet.objects.get()
        self.assertEqual(Account.from_key(crypto.private_key(wallet)).address, wallet.address)

    def test_import_own_wallet(self):
        acct = Account.create()
        r = self.client.post("/wallet/", {"action": "import", "private_key": "not a key"}, follow=True)
        self.assertContains(r, "look like a private key")
        self.client.post("/wallet/", {"action": "import", "private_key": acct.key.hex()})
        wallet = TradingWallet.objects.get()
        self.assertEqual(wallet.address, acct.address)
        self.assertEqual(Account.from_key(crypto.private_key(wallet)).address, acct.address)

    def test_withdraw_needs_address(self):
        crypto.create_wallet(self.user)
        with self.assertRaisesMessage(live.LiveError, "withdrawal address"):
            live.withdraw(self.user, Network.objects.get(slug="ethereum"))


class SettingsTests(AppTestCase):
    def test_rpc_from_settings(self):
        eth = Network.objects.get(slug="ethereum")
        with patch("bot.services.chain.probe", return_value={"chain_id": 1, "block": 123}):
            r = self.client.post("/settings/", {"action": "save_rpc", "network": "ethereum", "url": "https://rpc.example/key"}, follow=True)
        self.assertContains(r, "the node works")
        self.assertEqual(config.rpc_url(eth), "https://rpc.example/key")
        self.assertEqual(chain.get_w3(eth).provider.endpoint_uri, "https://rpc.example/key")
        with patch("bot.services.chain.probe", return_value={"chain_id": 11155111, "block": 5}):
            r = self.client.post("/settings/", {"action": "test_rpc", "network": "ethereum", "url": ""}, follow=True)
        self.assertContains(r, "different network")
        with self.assertRaisesMessage(chain.ChainError, "https://"):
            chain.probe("wss://x")

    def test_no_rpc_message_points_to_settings(self):
        with patch.dict("os.environ", {"WEB3_PROVIDER_ETHEREUM": ""}):
            with self.assertRaisesMessage(chain.ChainError, "Settings"):
                chain.get_w3(Network.objects.get(slug="ethereum"))

    def test_trading_settings(self):
        home = Account.create().address
        form = {"action": "trading", "limit": "0.05", "slippage": "0.5", "withdraw": home.lower(), "live": "1"}
        self.client.post("/settings/", form)
        self.user.refresh_from_db()
        self.assertFalse(self.user.live_enabled)  # live mode stays off without the "I understand the risk" box
        self.client.post("/settings/", {**form, "live_understood": "1"})
        self.user.refresh_from_db()
        self.assertTrue(self.user.live_enabled)
        self.assertEqual(self.user.slippage_bps, 50)
        self.assertEqual(config.live_limit(), Decimal("0.05"))
        self.assertEqual(config.withdraw_address(), home)  # saved in checksum form
        self.client.post("/settings/", {**form, "withdraw": "0x123"})
        self.assertEqual(config.withdraw_address(), home)  # a broken address is not saved
        crypto.create_wallet(self.user)
        with patch("bot.services.prices.get_price", return_value=PRICE), patch("bot.services.prices.native_usd", return_value=ETH_USD), \
             patch("bot.services.live._w3", return_value=None):
            order = trading.execute_order(self.user, Token.objects.get(symbol="LINK"), "buy", amount_native=Decimal("0.1"), mode="live")
        self.assertIn("single-buy limit", order.error)


class SmallFixesTests(AppTestCase):
    def test_admin_logout_returns_to_app(self):
        self.assertRedirects(self.client.post("/admin/logout/"), "/pond/", fetch_redirect_response=False)
        self.assertEqual(self.client.get("/pond/").status_code, 200)  # still logged in

    def test_withdraw_address_cant_be_wallet_or_token(self):
        wallet = crypto.create_wallet(self.user)
        base = {"action": "trading", "limit": "0.02", "slippage": "1"}
        r = self.client.post("/settings/", {**base, "withdraw": wallet.address}, follow=True)
        self.assertContains(r, "trading wallet itself")
        r = self.client.post("/settings/", {**base, "withdraw": Token.objects.get(symbol="USDC").address}, follow=True)
        self.assertContains(r, "token contract")
        self.assertEqual(config.withdraw_address(), "")

    @patch("bot.services.market._get", side_effect=Exception("offline"))
    def test_demo_charges_the_fee_once(self, _):
        # a pool at a mid price of 0.001 ETH with a 0.3 % fee quotes 0.05 * 0.997 / 0.001 tokens for 0.05 ETH
        from bot.services import dex, prices
        route = dex.Route("v2", 3000, int(Decimal("0.05") * Decimal("0.997") / Decimal("0.001") * 10**18), "0x")
        token = Token.objects.get(symbol="LINK")
        with patch("bot.services.dex.quotes", return_value=[route]), patch("bot.services.prices.get_w3"):
            self.assertEqual(prices._route_price(token).quantize(Decimal("1e-12")), Decimal("0.001"))
        with patch("bot.services.prices.get_price", return_value=Decimal("0.001")), patch("bot.services.prices.native_usd", return_value=ETH_USD):
            order = trading.execute_order(self.user, token, "buy", amount_native=Decimal("0.1"))
        self.assertEqual(order.amount_token, Decimal("99.7"))  # like a real swap: 0.1 * 0.997 / 0.001

    def test_reenabled_rule_checks_right_away(self):
        from django.utils import timezone
        from bot.models import Rule
        rule = Rule.objects.create(user=self.user, token=Token.objects.get(symbol="LINK"), trigger="below", trigger_price_usd=Decimal(5),
                                   action="buy", amount_native=Decimal("0.1"), is_active=False, last_fired=timezone.now())
        self.client.post(f"/rules/{rule.pk}/toggle/")
        rule.refresh_from_db()
        self.assertTrue(rule.is_active)
        self.assertIsNone(rule.last_fired)
