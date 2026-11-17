from django.core.management.base import BaseCommand

from bot.models import Token
from bot.services import chain


class Command(BaseCommand):
    help = "Checks verified tokens against the chain: symbol and decimals. Fixes decimals, reports symbol mismatches."

    def handle(self, *args, **kw):
        bad = 0
        for token in Token.objects.filter(is_verified=True, network__is_active=True).select_related("network"):
            try:
                data = chain.read_token(token.network, token.address)
            except chain.ChainError as e:
                bad += 1
                self.stderr.write(f"{token.symbol:8} {token.address}  unreadable: {e}")
                continue
            if data["decimals"] != token.decimals:
                self.stdout.write(self.style.WARNING(f"{token.symbol:8} decimals {token.decimals} -> {data['decimals']} (fixed)"))
                token.decimals = data["decimals"]
                token.save(update_fields=["decimals"])
            if data["symbol"].lower() != token.symbol.lower():
                bad += 1
                self.stderr.write(f"{token.symbol:8} {token.address}  the contract says {data['symbol']!r}: check the address")
            else:
                self.stdout.write(f"{token.symbol:8} ok")
        self.stdout.write(self.style.SUCCESS("All tokens match.") if not bad else self.style.ERROR(f"Problem tokens: {bad}"))
