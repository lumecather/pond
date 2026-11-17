from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """The app has a single local user; these are their trading preferences."""

    pro_mode = models.BooleanField("Pro mode", default=False, help_text="Show contract addresses, prices in the network coin and other details.")
    live_enabled = models.BooleanField("live trading allowed", default=False, help_text="Can trade real money from the trading wallet.")
    slippage_bps = models.PositiveSmallIntegerField("slippage tolerance, bps", default=100, help_text="100 = 1 %. If the price moves further, the swap is cancelled.")
