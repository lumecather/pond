from decimal import Decimal

from django.conf import settings
from django.db import models
from web3 import Web3

DEC = {"max_digits": 50, "decimal_places": 18}


def checksum(address: str) -> str:
    return Web3.to_checksum_address(address.lower()) if address else ""


class Network(models.Model):
    """A blockchain network. To add one: a row here (admin) and an RPC URL in Settings."""

    name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True)
    chain_id = models.PositiveIntegerField(null=True, blank=True)
    rpc_env = models.CharField(
        "RPC key", max_length=60,
        help_text="Name under which the RPC URL is stored, e.g. WEB3_PROVIDER_ETHEREUM. An environment variable with this name also works.",
    )
    native_symbol = models.CharField("native coin", max_length=10, default="ETH")
    explorer_url = models.URLField("block explorer", blank=True)
    router_address = models.CharField("DEX router (Uniswap V2 compatible)", max_length=42, blank=True)
    wrapped_native = models.CharField("wrapped native coin (WETH)", max_length=42, blank=True)
    stable_address = models.CharField("stablecoin for USD prices", max_length=42, blank=True)
    stable_decimals = models.PositiveSmallIntegerField(default=6)
    v3_router = models.CharField("Uniswap V3 router (SwapRouter02)", max_length=42, blank=True)
    v3_quoter = models.CharField("Uniswap V3 quoter (QuoterV2)", max_length=42, blank=True)
    multicall_address = models.CharField("Multicall3", max_length=42, blank=True)
    private_rpc_url = models.URLField(
        "private RPC for sending trades", blank=True,
        help_text="For example Flashbots Protect: the trade skips the public mempool, so MEV bots can't front-run it. Empty = normal sending.",
    )
    gecko_id = models.CharField(
        "GeckoTerminal ID", max_length=40, blank=True,
        help_text="Needed for charts. Ethereum is eth, Base is base. Full list: api.geckoterminal.com/api/v2/networks",
    )
    is_active = models.BooleanField("enabled", default=True)

    class Meta:
        ordering = ["id"]

    def save(self, *a, **kw):
        for f in ("router_address", "wrapped_native", "stable_address", "v3_router", "v3_quoter", "multicall_address"):
            setattr(self, f, checksum(getattr(self, f)))
        super().save(*a, **kw)

    def __str__(self):
        return self.name


class Token(models.Model):
    class Category(models.TextChoices):
        MAJOR = "major", "Majors"
        DEFI = "defi", "DeFi and infrastructure"
        MEME = "meme", "Memes"
        STABLE = "stable", "Stablecoins"
        OTHER = "other", "Other"

    network = models.ForeignKey(Network, on_delete=models.CASCADE, related_name="tokens")
    address = models.CharField(max_length=42)
    symbol = models.CharField(max_length=20)
    name = models.CharField(max_length=80, blank=True)
    decimals = models.PositiveSmallIntegerField(default=18)
    category = models.CharField(max_length=6, choices=Category.choices, default=Category.OTHER)
    description = models.CharField("what it is, in one sentence", max_length=200, blank=True)
    is_verified = models.BooleanField("verified", default=False, help_text="Verified tokens ship with the app and can be traded live.")
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        unique_together = [("network", "address")]
        ordering = ["-is_verified", "symbol"]

    def save(self, *a, **kw):
        self.address = checksum(self.address)
        super().save(*a, **kw)

    def __str__(self):
        return self.symbol


class TradingWallet(models.Model):
    """A separate wallet for the bot. The private key is only ever stored encrypted."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trading_wallet")
    address = models.CharField(max_length=42, unique=True)
    encrypted_key = models.TextField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.address


class Mode(models.TextChoices):
    PAPER = "paper", "Demo"
    LIVE = "live", "Live"


class Side(models.TextChoices):
    BUY = "buy", "Buy"
    SELL = "sell", "Sell"


class PaperBalance(models.Model):
    """Demo balance. An empty token means the network's coin (ETH)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="paper_balances")
    network = models.ForeignKey(Network, on_delete=models.CASCADE)
    token = models.ForeignKey(Token, null=True, blank=True, on_delete=models.CASCADE)
    amount = models.DecimalField(default=Decimal(0), **DEC)

    class Meta:
        verbose_name = "demo balance"
        constraints = [
            models.UniqueConstraint(fields=["user", "network", "token"], name="paper_token_unique"),
            models.UniqueConstraint(fields=["user", "network"], condition=models.Q(token__isnull=True), name="paper_native_unique"),
        ]


class Rule(models.Model):
    """A bot rule: "when the token's price drops below / rises above X $, buy / sell"."""

    class Trigger(models.TextChoices):
        BELOW = "below", "drops below"
        ABOVE = "above", "rises above"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rules")
    token = models.ForeignKey(Token, on_delete=models.CASCADE)
    trigger = models.CharField(max_length=10, choices=Trigger.choices)
    trigger_price_usd = models.DecimalField("price, $", **DEC)
    action = models.CharField(max_length=4, choices=Side.choices)
    amount_native = models.DecimalField("buy for (in the network coin)", null=True, blank=True, **DEC)
    sell_percent = models.PositiveSmallIntegerField("sell, %", null=True, blank=True)
    repeat = models.BooleanField(default=False, help_text="Otherwise the rule switches off after it fires once.")
    mode = models.CharField(max_length=5, choices=Mode.choices, default=Mode.PAPER)
    is_active = models.BooleanField("enabled", default=True)
    last_fired = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.token.symbol} {self.get_trigger_display()} ${self.trigger_price_usd.normalize():f} → {self.get_action_display().lower()}"


class Order(models.Model):
    class Status(models.TextChoices):
        FILLED = "filled", "Filled"
        FAILED = "failed", "Failed"
        PENDING = "pending", "Pending"

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        RULE = "rule", "Rule"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders")
    token = models.ForeignKey(Token, on_delete=models.PROTECT)
    side = models.CharField(max_length=4, choices=Side.choices)
    amount_native = models.DecimalField("amount in the network coin", default=Decimal(0), **DEC)
    amount_token = models.DecimalField("token amount", default=Decimal(0), **DEC)
    price = models.DecimalField("price in the network coin", default=Decimal(0), **DEC)
    price_usd = models.DecimalField("price, $", null=True, blank=True, **DEC)
    mode = models.CharField(max_length=5, choices=Mode.choices, default=Mode.PAPER)
    status = models.CharField(max_length=8, choices=Status.choices)
    source = models.CharField(max_length=6, choices=Source.choices, default=Source.MANUAL)
    rule = models.ForeignKey(Rule, null=True, blank=True, on_delete=models.SET_NULL)
    gas_native = models.DecimalField("gas, in the network coin", default=Decimal(0), **DEC)
    tx_hash = models.CharField(max_length=66, blank=True)
    error = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField("time", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class AppSetting(models.Model):
    """Values changed from the Settings screen: RPC URLs, limits and the password check data."""

    key = models.CharField(max_length=60, primary_key=True)
    value = models.TextField(blank=True)

    def __str__(self):
        return self.key
