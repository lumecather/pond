"""Live mode: real swaps from the trading wallet.

A trade goes: checks -> quote the best route -> (approval when selling) ->
simulate with estimate_gas (if it would fail we find out before sending, without paying gas) ->
sign -> send (through the private RPC if the network has one) -> wait for the receipt.
"""
import time
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from eth_account import Account

from bot.models import Order, Side, TradingWallet

from . import chain, config, crypto, dex, prices, vault

WAIT_SECONDS = 150            # how long we wait for the transaction to be included
DEADLINE_SECONDS = 300        # after this the swap cancels itself in the contract
PENDING_GIVE_UP = timedelta(minutes=15)
WEI = Decimal(10**18)


class LiveError(Exception):
    pass


def wallet_of(user) -> TradingWallet:
    wallet = TradingWallet.objects.filter(user=user).first()
    if not wallet:
        raise LiveError("Create a trading wallet first (the Wallet tab).")
    return wallet


def _account(wallet):
    try:
        return Account.from_key(crypto.private_key(wallet))
    except vault.Locked as e:
        raise LiveError(str(e))


def check_allowed(user, token):
    if not user.live_enabled:
        raise LiveError("Live trading is off. Turn it on in Settings.")
    if not token.is_verified:
        raise LiveError("Live mode only trades verified tokens for now.")
    if not token.network.wrapped_native:
        raise LiveError(f"No DEX is configured for {token.network.name}.")


def _w3(network):
    try:
        return chain.get_w3(network)
    except chain.ChainError as e:
        raise LiveError(str(e))


def _fees(w3) -> dict:
    """EIP-1559 fees with headroom: survive a base fee increase over the next blocks."""
    base = w3.eth.get_block("latest")["baseFeePerGas"]
    try:
        tip = max(int(w3.eth.max_priority_fee), 10**8)
    except Exception:
        tip = 10**9
    return {"maxFeePerGas": base * 2 + tip, "maxPriorityFeePerGas": tip}


def _send(network, w3, account, tx: dict) -> str:
    """Simulates, signs and sends a transaction. Returns its hash."""
    tx = {**tx, "from": account.address, "chainId": network.chain_id or w3.eth.chain_id,
          "nonce": w3.eth.get_transaction_count(account.address, "pending"), **_fees(w3)}
    have = w3.eth.get_balance(account.address)
    short = f"Not enough {network.native_symbol} including gas: the wallet has {Decimal(have) / WEI:.5f}"
    try:
        tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.25)
    except Exception as e:
        text = str(e)
        if "enough balance" in text or "insufficient funds" in text:
            raise LiveError(f"{short}, but {Decimal(tx.get('value', 0)) / WEI:.5f} plus gas is needed. Nothing was spent.")
        raise LiveError(f"The network rejected the trade in simulation, nothing was spent: {text[:120]}")
    need = tx.get("value", 0) + tx["gas"] * tx["maxFeePerGas"]
    if have < need:
        raise LiveError(f"{short}, but up to {Decimal(need) / WEI:.5f} is needed. Nothing was spent.")
    raw = account.sign_transaction(tx).raw_transaction
    sender = chain._w3(network.private_rpc_url) if network.private_rpc_url else w3
    try:
        return sender.eth.send_raw_transaction(raw).to_0x_hex()
    except Exception as e:
        raise LiveError(f"Couldn't send the transaction: {str(e)[:120]}")


def _receipt(w3, tx_hash: str, timeout: int = WAIT_SECONDS):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            if receipt:
                return receipt
        except Exception:
            pass
        time.sleep(3)
    return None


def _gas_cost(receipt) -> Decimal:
    return Decimal(receipt["gasUsed"] * receipt.get("effectiveGasPrice", 0)) / WEI


def _ensure_allowance(network, w3, account, token_address: str, spender: str, amount: int):
    """Let the router spend the token. We approve exactly the trade amount, never "unlimited"."""
    erc20 = w3.eth.contract(address=token_address, abi=dex.ERC20_ABI)
    current = erc20.functions.allowance(account.address, spender).call()
    if current >= amount:
        return
    steps = [0, amount] if current > 0 else [amount]  # USDT requires resetting to zero first
    for value in steps:
        tx_hash = _send(network, w3, account, {"to": token_address, "data": erc20.functions.approve(spender, value)._encode_transaction_data(), "value": 0})
        receipt = _receipt(w3, tx_hash)
        if receipt is None:
            raise LiveError("The approval was sent but isn't confirmed yet, so the swap was not sent. "
                            f"Wait a few minutes before trading again (approval: {tx_hash}).")
        if receipt["status"] != 1:
            raise LiveError("Couldn't approve the router. The swap was not sent.")


def execute(order, amount_native, sell_percent):
    """Executes the order on chain and fills in its fields. Raises LiveError or DexError with a readable message."""
    user, token, net = order.user, order.token, order.token.network
    check_allowed(user, token)
    if order.side == Side.BUY:  # check the amount before touching the network
        amount = Decimal(amount_native or 0)
        limit = config.live_limit()
        if amount <= 0:
            raise LiveError("Enter how much to buy for.")
        if amount > limit:
            raise LiveError(f"That is above the single-buy limit ({limit.normalize():f} {net.native_symbol}). The limit is set in Settings.")
    wallet = wallet_of(user)
    refresh_pending(user)
    if Order.objects.filter(user=user, status=Order.Status.PENDING).exists():
        # a second transaction with the same nonce would replace the first one
        raise LiveError("The previous trade is not in a block yet. Wait for it and try again.")
    w3 = _w3(net)
    account = _account(wallet)
    slippage = Decimal(user.slippage_bps) / Decimal(10000)
    deadline = int(time.time()) + DEADLINE_SECONDS
    erc20 = w3.eth.contract(address=token.address, abi=dex.ERC20_ABI)
    unit = Decimal(10**token.decimals)

    if order.side == Side.BUY:
        amount = Decimal(amount_native or 0)
        amount_in = int(amount * WEI)
        route = dex.best_route(net, w3, net.wrapped_native, token.address, amount_in)
        min_out = int(route.amount_out * (1 - slippage))
        before = erc20.functions.balanceOf(account.address).call()
        tx = dex.build_buy(net, w3, route, token.address, amount_in, min_out, account.address, deadline)
        order.amount_native, order.amount_token = amount, Decimal(route.amount_out) / unit
    else:
        percent = int(sell_percent or 0)
        if not 1 <= percent <= 100:
            raise LiveError("Enter what percentage to sell (1–100).")
        have = erc20.functions.balanceOf(account.address).call()
        amount_in = have * percent // 100
        if amount_in <= 0:
            raise LiveError(f"The trading wallet has no {token.symbol}.")
        route = dex.best_route(net, w3, token.address, net.wrapped_native, amount_in)
        min_out = int(route.amount_out * (1 - slippage))
        _ensure_allowance(net, w3, account, token.address, route.router, amount_in)
        before = w3.eth.get_balance(account.address)
        tx = dex.build_sell(net, w3, route, token.address, amount_in, min_out, account.address, deadline)
        order.amount_native, order.amount_token = Decimal(route.amount_out) / WEI, Decimal(amount_in) / unit

    order.tx_hash = _send(net, w3, account, tx)
    order.status = Order.Status.PENDING
    order.save()  # save the hash right away: even if something fails later, the trade can be found in the explorer
    receipt = _receipt(w3, order.tx_hash)
    if receipt is None:
        order.error = "Transaction sent but not in a block yet. The status will update by itself."
        return
    _finish(order, w3, receipt, account.address, before)


def _finish(order, w3, receipt, address, before=None):
    """Fills in the order from the receipt. `before` is the balance before the trade, to record the actual result."""
    order.gas_native = _gas_cost(receipt)
    if receipt["status"] != 1:
        order.status, order.error = Order.Status.FAILED, "The network reverted the trade (the price moved past the tolerance or the deadline passed). Only gas was spent."
        return
    order.status, order.error = Order.Status.FILLED, ""
    if before is not None:
        token = order.token
        if order.side == Side.BUY:
            after = w3.eth.contract(address=token.address, abi=dex.ERC20_ABI).functions.balanceOf(address).call()
            got = Decimal(after - before) / Decimal(10**token.decimals)
            if got > 0:
                order.amount_token = got
        else:
            got = Decimal(w3.eth.get_balance(address) - before) / WEI + order.gas_native
            if got > 0:
                order.amount_native = got
    if order.amount_token:
        order.price = order.amount_native / order.amount_token
        try:
            order.price_usd = order.price * prices.native_usd(order.token.network)
        except prices.PriceUnavailable:
            pass


def refresh_pending(user):
    """Completes orders that were not in a block yet when we stopped waiting."""
    for order in Order.objects.filter(user=user, status=Order.Status.PENDING).exclude(tx_hash="").select_related("token__network"):
        try:
            w3 = _w3(order.token.network)
            receipt = w3.eth.get_transaction_receipt(order.tx_hash)
        except Exception:
            receipt = None
        if receipt:
            _finish(order, w3, receipt, None)
        elif timezone.now() - order.created_at > PENDING_GIVE_UP:
            order.status, order.error = Order.Status.FAILED, "The transaction was dropped without being included. Nothing was spent."
        else:
            continue
        order.save()


def portfolio(user, network, tokens) -> dict:
    """What the trading wallet holds now. Same format as the demo portfolio."""
    wallet = wallet_of(user)
    w3 = _w3(network)
    tokens = list(tokens)
    try:
        native_wei, raw = dex.balances(network, w3, wallet.address, tokens)
    except Exception:
        raise LiveError("Couldn't read the wallet balances: the network is not answering.")
    native = Decimal(native_wei) / WEI
    try:
        usd = prices.native_usd(network)
    except prices.PriceUnavailable:
        usd = None
    rows, total = [], native
    prices.warm(t for t in tokens if raw.get(t.pk, 0) > 0)
    for token in tokens:
        amount = Decimal(raw.get(token.pk, 0)) / Decimal(10**token.decimals)
        if amount <= 0:
            continue
        try:
            price = prices.get_price(token)
            value = amount * price
            total += value
        except prices.PriceUnavailable:
            price = value = None
        rows.append({
            "token": token, "amount": amount, "price": price, "value": value,
            "price_usd": price * usd if price is not None and usd else None,
            "value_usd": value * usd if value is not None and usd else None,
        })
    return {"native": native, "native_usd": native * usd if usd else None, "positions": rows,
            "total": total, "total_usd": total * usd if usd else None, "pnl_percent": None, "usd_rate": usd}


def token_amount(user, token) -> Decimal:
    wallet = wallet_of(user)
    raw = _w3(token.network).eth.contract(address=token.address, abi=dex.ERC20_ABI).functions.balanceOf(wallet.address).call()
    return Decimal(raw) / Decimal(10**token.decimals)


def native_amount(user, network) -> Decimal:
    return Decimal(_w3(network).eth.get_balance(wallet_of(user).address)) / WEI


def withdraw(user, network, token=None) -> str:
    """Withdraws the whole balance of the network coin or a token to the address from Settings."""
    to = config.withdraw_address(user)
    if not to:
        raise LiveError("No withdrawal address yet: set one in Settings.")
    wallet = wallet_of(user)
    w3 = _w3(network)
    account = _account(wallet)
    if token is None:
        fees = _fees(w3)
        value = w3.eth.get_balance(account.address) - 21000 * fees["maxFeePerGas"]
        if value <= 0:
            raise LiveError("The balance doesn't even cover the gas for a transfer.")
        tx = {"to": to, "value": value, "gas": 21000, "from": account.address, **fees,
              "chainId": network.chain_id or w3.eth.chain_id, "nonce": w3.eth.get_transaction_count(account.address, "pending")}
        try:
            return w3.eth.send_raw_transaction(account.sign_transaction(tx).raw_transaction).to_0x_hex()
        except Exception as e:
            raise LiveError(f"Couldn't send the transfer: {str(e)[:120]}")
    erc20 = w3.eth.contract(address=token.address, abi=dex.ERC20_ABI)
    amount = erc20.functions.balanceOf(account.address).call()
    if amount <= 0:
        raise LiveError(f"The trading wallet has no {token.symbol}.")
    return _send(network, w3, account, {"to": token.address, "data": erc20.functions.transfer(to, amount)._encode_transaction_data(), "value": 0})
