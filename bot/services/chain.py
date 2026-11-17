"""Connecting to a network and reading token data."""
from functools import lru_cache

from web3 import Web3

ERC20_ABI = [
    {"name": "symbol", "inputs": [], "outputs": [{"type": "string"}], "stateMutability": "view", "type": "function"},
    {"name": "name", "inputs": [], "outputs": [{"type": "string"}], "stateMutability": "view", "type": "function"},
    {"name": "decimals", "inputs": [], "outputs": [{"type": "uint8"}], "stateMutability": "view", "type": "function"},
]
class ChainError(Exception):
    pass


@lru_cache(maxsize=None)
def _w3(url: str) -> Web3:
    return Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 8}))


def get_w3(network) -> Web3:
    from . import config

    url = config.rpc_url(network)
    if not url:
        raise ChainError(f"No RPC URL for {network.name} yet: open Settings and paste one.")
    return _w3(url)


def probe(url: str) -> dict:
    """Checks an RPC URL: does the node answer, and which network is it."""
    if not url.startswith(("https://", "http://")):
        raise ChainError("Use the link that starts with https:// (not wss://).")
    try:
        w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 8}))
        return {"chain_id": w3.eth.chain_id, "block": w3.eth.block_number}
    except Exception as e:
        text = str(e)
        if "401" in text or "403" in text:
            raise ChainError("The node refused access: check that the key is copied in full and activated.")
        raise ChainError(f"The node did not answer: {text[:120]}")


def read_token(network, address: str) -> dict:
    """The token's symbol, name and decimals, read from its contract."""
    if not Web3.is_address(address):
        raise ChainError("That doesn't look like a token address.")
    address = Web3.to_checksum_address(address.lower())
    c = get_w3(network).eth.contract(address=address, abi=ERC20_ABI)
    try:
        symbol, decimals = c.functions.symbol().call(), c.functions.decimals().call()
    except Exception:
        raise ChainError("Couldn't read the token: check the address and the network.")
    try:
        name = c.functions.name().call()
    except Exception:
        name = ""
    return {"address": address, "symbol": symbol[:20], "name": name[:80], "decimals": decimals}
