from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from bot.models import Network, Token, TradingWallet
from bot.services import chain, config, dex


class Command(BaseCommand):
    help = "Dry run for live mode, nothing is sent: routes, quotes, wallet balances and a simulated buy."

    def add_arguments(self, parser):
        parser.add_argument("symbol", nargs="?", default="LINK", help="token symbol, LINK by default")
        parser.add_argument("--amount", default="0.005", help="test buy amount in the network coin")

    def handle(self, *args, symbol, amount, **kw):
        net = Network.objects.get(slug="ethereum")
        token = Token.objects.filter(network=net, symbol__iexact=symbol, is_verified=True).first()
        if not token:
            raise CommandError(f"There is no verified token {symbol}.")
        w3 = chain.get_w3(net)
        self.stdout.write(f"Network: chainId {w3.eth.chain_id}, block {w3.eth.block_number}, base fee {w3.eth.get_block('latest')['baseFeePerGas'] / 1e9:.2f} gwei")
        self.stdout.write(f"Private sending: {net.private_rpc_url or 'none (public mempool)'}")
        self.stdout.write(f"Single-buy limit: {config.live_limit()} {net.native_symbol}")

        amount_in = int(Decimal(amount) * 10**18)
        self.stdout.write(f"\nBuy {token.symbol} for {amount} {net.native_symbol}, routes:")
        routes = dex.quotes(net, w3, net.wrapped_native, token.address, amount_in)
        if not routes:
            raise CommandError("No route answered: check the router addresses in the admin.")
        for i, r in enumerate(routes):
            self.stdout.write(f"  {'*' if i == 0 else ' '} {r.label:18} -> {Decimal(r.amount_out) / 10**token.decimals:.6f} {token.symbol}")
        back = dex.quotes(net, w3, token.address, net.wrapped_native, routes[0].amount_out)
        if back:
            loss = 100 - back[0].amount_out * 100 / amount_in
            self.stdout.write(f"Sell back: {back[0].label} -> {Decimal(back[0].amount_out) / 10**18:.6f} {net.native_symbol} (round-trip loss {loss:.2f} %)")

        for wallet in TradingWallet.objects.select_related("user"):
            native, raw = dex.balances(net, w3, wallet.address, [token])
            state = "allowed" if wallet.user.live_enabled else "off"
            self.stdout.write(f"\nWallet {wallet.address} (live trading {state}): "
                              f"{Decimal(native) / 10**18:.5f} {net.native_symbol}, {Decimal(raw[token.pk]) / 10**token.decimals:.6f} {token.symbol}")
            if native > amount_in:
                tx = dex.build_buy(net, w3, routes[0], token.address, amount_in, int(routes[0].amount_out * 0.99), wallet.address, w3.eth.get_block("latest")["timestamp"] + 300)
                try:
                    gas = w3.eth.estimate_gas({**tx, "from": wallet.address})
                    self.stdout.write(self.style.SUCCESS(f"  Simulated buy passed: the network would accept it, gas about {gas}. Nothing was sent."))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  Simulated buy FAILED: {e}"))
            else:
                self.stdout.write("  Balance is below the test amount, so the simulated buy was skipped.")
