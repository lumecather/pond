"""Talking to DEXes: quotes and building swap transactions for Uniswap V2 and V3.

Nothing is sent to the network here, only reads and transaction data.
Sending is done by live.py.
"""
from dataclasses import dataclass

V3_FEES = (500, 3000, 10000)  # V3 pool fees: 0.05 %, 0.3 %, 1 %
ADDRESS_THIS = "0x0000000000000000000000000000000000000002"  # "the router itself" in SwapRouter02

ERC20_ABI = [
    {"name": "balanceOf", "type": "function", "stateMutability": "view", "inputs": [{"name": "a", "type": "address"}], "outputs": [{"type": "uint256"}]},
    {"name": "allowance", "type": "function", "stateMutability": "view", "inputs": [{"name": "o", "type": "address"}, {"name": "s", "type": "address"}], "outputs": [{"type": "uint256"}]},
    # outputs left empty on purpose: USDT returns no bool, and we don't need the answer
    {"name": "approve", "type": "function", "stateMutability": "nonpayable", "inputs": [{"name": "s", "type": "address"}, {"name": "v", "type": "uint256"}], "outputs": []},
    {"name": "transfer", "type": "function", "stateMutability": "nonpayable", "inputs": [{"name": "to", "type": "address"}, {"name": "v", "type": "uint256"}], "outputs": []},
]
V2_ABI = [
    {"name": "getAmountsOut", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "amountIn", "type": "uint256"}, {"name": "path", "type": "address[]"}], "outputs": [{"name": "amounts", "type": "uint256[]"}]},
    {"name": "swapExactETHForTokensSupportingFeeOnTransferTokens", "type": "function", "stateMutability": "payable",
     "inputs": [{"name": "amountOutMin", "type": "uint256"}, {"name": "path", "type": "address[]"}, {"name": "to", "type": "address"}, {"name": "deadline", "type": "uint256"}], "outputs": []},
    {"name": "swapExactTokensForETHSupportingFeeOnTransferTokens", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "amountIn", "type": "uint256"}, {"name": "amountOutMin", "type": "uint256"}, {"name": "path", "type": "address[]"}, {"name": "to", "type": "address"}, {"name": "deadline", "type": "uint256"}], "outputs": []},
]
_V3_PARAMS = {"name": "params", "type": "tuple", "components": [
    {"name": "tokenIn", "type": "address"}, {"name": "tokenOut", "type": "address"}, {"name": "fee", "type": "uint24"},
    {"name": "recipient", "type": "address"}, {"name": "amountIn", "type": "uint256"},
    {"name": "amountOutMinimum", "type": "uint256"}, {"name": "sqrtPriceLimitX96", "type": "uint160"}]}
V3_ROUTER_ABI = [  # SwapRouter02
    {"name": "exactInputSingle", "type": "function", "stateMutability": "payable", "inputs": [_V3_PARAMS], "outputs": [{"name": "amountOut", "type": "uint256"}]},
    {"name": "unwrapWETH9", "type": "function", "stateMutability": "payable", "inputs": [{"name": "amountMinimum", "type": "uint256"}, {"name": "recipient", "type": "address"}], "outputs": []},
    {"name": "multicall", "type": "function", "stateMutability": "payable", "inputs": [{"name": "deadline", "type": "uint256"}, {"name": "data", "type": "bytes[]"}], "outputs": [{"name": "", "type": "bytes[]"}]},
]
V3_QUOTER_ABI = [  # QuoterV2: not a view function, called via eth_call
    {"name": "quoteExactInputSingle", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "params", "type": "tuple", "components": [
         {"name": "tokenIn", "type": "address"}, {"name": "tokenOut", "type": "address"}, {"name": "amountIn", "type": "uint256"},
         {"name": "fee", "type": "uint24"}, {"name": "sqrtPriceLimitX96", "type": "uint160"}]}],
     "outputs": [{"name": "amountOut", "type": "uint256"}, {"name": "sqrtPriceX96After", "type": "uint160"},
                 {"name": "initializedTicksCrossed", "type": "uint32"}, {"name": "gasEstimate", "type": "uint256"}]},
]
MULTICALL_ABI = [  # Multicall3
    {"name": "aggregate3", "type": "function", "stateMutability": "payable",
     "inputs": [{"name": "calls", "type": "tuple[]", "components": [{"name": "target", "type": "address"}, {"name": "allowFailure", "type": "bool"}, {"name": "callData", "type": "bytes"}]}],
     "outputs": [{"name": "returnData", "type": "tuple[]", "components": [{"name": "success", "type": "bool"}, {"name": "returnData", "type": "bytes"}]}]},
    {"name": "getEthBalance", "type": "function", "stateMutability": "view", "inputs": [{"name": "addr", "type": "address"}], "outputs": [{"name": "balance", "type": "uint256"}]},
]


class DexError(Exception):
    pass


@dataclass
class Route:
    kind: str        # "v2" or "v3"
    fee: int         # V3 pool fee (3000 for V2, i.e. 0.3 %)
    amount_out: int  # expected output at the current price, in base units
    router: str      # router address: it gets the approval and receives the transaction

    @property
    def label(self):
        return "Uniswap V2" if self.kind == "v2" else f"Uniswap V3 {self.fee / 10000:g} %"


def _contract(w3, address, abi):
    return w3.eth.contract(address=address, abi=abi)


def quotes(network, w3, token_in: str, token_out: str, amount_in: int) -> list[Route]:
    """Every available swap route, best first. Pools that don't exist are skipped."""
    out = []
    if network.router_address:
        try:
            amount = _contract(w3, network.router_address, V2_ABI).functions.getAmountsOut(amount_in, [token_in, token_out]).call()[-1]
            out.append(Route("v2", 3000, amount, network.router_address))
        except Exception:
            pass
    if network.v3_router and network.v3_quoter:
        quoter = _contract(w3, network.v3_quoter, V3_QUOTER_ABI)
        for fee in V3_FEES:
            try:
                amount = quoter.functions.quoteExactInputSingle((token_in, token_out, amount_in, fee, 0)).call()[0]
                out.append(Route("v3", fee, amount, network.v3_router))
            except Exception:
                pass
    return sorted((r for r in out if r.amount_out > 0), key=lambda r: -r.amount_out)


def best_route(network, w3, token_in, token_out, amount_in) -> Route:
    found = quotes(network, w3, token_in, token_out, amount_in)
    if not found:
        raise DexError("No pool was found to swap this token.")
    return found[0]


def build_buy(network, w3, route: Route, token: str, amount_in: int, min_out: int, to: str, deadline: int) -> dict:
    """Buy a token with the network coin. The coin is sent with the transaction (value)."""
    weth = network.wrapped_native
    if route.kind == "v2":
        fn = _contract(w3, route.router, V2_ABI).functions.swapExactETHForTokensSupportingFeeOnTransferTokens(min_out, [weth, token], to, deadline)
    else:
        router = _contract(w3, route.router, V3_ROUTER_ABI)
        swap = router.encode_abi("exactInputSingle", args=[(weth, token, route.fee, to, amount_in, min_out, 0)])
        fn = router.functions.multicall(deadline, [swap])
    return {"to": route.router, "data": fn._encode_transaction_data(), "value": amount_in}


def build_sell(network, w3, route: Route, token: str, amount_in: int, min_out: int, to: str, deadline: int) -> dict:
    """Sell a token for the network coin. The router needs an approval for amount_in first."""
    weth = network.wrapped_native
    if route.kind == "v2":
        fn = _contract(w3, route.router, V2_ABI).functions.swapExactTokensForETHSupportingFeeOnTransferTokens(amount_in, min_out, [token, weth], to, deadline)
    else:
        router = _contract(w3, route.router, V3_ROUTER_ABI)
        # the router receives WETH itself, then unwraps it to ETH and sends it to us
        swap = router.encode_abi("exactInputSingle", args=[(token, weth, route.fee, ADDRESS_THIS, amount_in, min_out, 0)])
        unwrap = router.encode_abi("unwrapWETH9", args=[min_out, to])
        fn = router.functions.multicall(deadline, [swap, unwrap])
    return {"to": route.router, "data": fn._encode_transaction_data(), "value": 0}


def balances(network, w3, owner: str, tokens: list) -> tuple[int, dict]:
    """Native coin and token balances in one request (Multicall3). Returns (wei, {token.pk: raw amount})."""
    erc20 = w3.eth.contract(abi=ERC20_ABI)
    if not network.multicall_address:
        native = w3.eth.get_balance(owner)
        return native, {t.pk: _contract(w3, t.address, ERC20_ABI).functions.balanceOf(owner).call() for t in tokens}
    mc = _contract(w3, network.multicall_address, MULTICALL_ABI)
    calls = [(network.multicall_address, False, mc.encode_abi("getEthBalance", args=[owner]))]
    calls += [(t.address, True, erc20.encode_abi("balanceOf", args=[owner])) for t in tokens]
    result = mc.functions.aggregate3(calls).call()
    native = int.from_bytes(result[0][1], "big")
    return native, {t.pk: int.from_bytes(data, "big") if ok and data else 0 for t, (ok, data) in zip(tokens, result[1:])}
