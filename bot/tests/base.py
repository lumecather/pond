"""Shared test setup: a local user who has set a password and is logged in, like after the first launch."""
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase

from bot.services import vault
from users.models import User

PASSWORD = "correct horse"
PRICE = Decimal("0.001")   # 1 token = 0.001 ETH
ETH_USD = Decimal("3000")  # so the token is worth $3


class AppTestCase(TestCase):
    login = True

    def setUp(self):
        cache.clear()
        vault.lock()
        self.addCleanup(vault.lock)
        self.user = User.objects.create(username="local", is_staff=True, is_superuser=True)
        vault.create(PASSWORD)
        if self.login:
            self.client.force_login(self.user)
