"""Starting data: Ethereum with its DEX contracts and a set of verified tokens.

Robinhood Chain is added switched off: it has an RPC slot, but no DEX addresses yet.
"""
from django.db import migrations
from web3 import Web3

cs = lambda a: Web3.to_checksum_address(a.lower())

# symbol, name, address, decimals, category, what it is
TOKENS = [
    ("USDC", "USD Coin", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", 6, "stable", "A stablecoin: always about $1. You can't profit from its price; it's a \"dollar on the blockchain\"."),
    ("USDT", "Tether USD", "0xdAC17F958D2ee523a2206206994597C13D831ec7", 6, "stable", "Tether's stablecoin: always about $1. The most popular \"dollar on the blockchain\"."),
    ("DAI", "Dai", "0x6B175474E89094C44Da98b954EedeAC495271d0F", 18, "stable", "A stablecoin of about $1 issued not by a company but by a protocol, backed by crypto collateral."),
    ("WBTC", "Wrapped Bitcoin", "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", 8, "major", "Bitcoin on Ethereum: its price follows BTC."),
    ("wstETH", "Lido Wrapped Staked ETH", "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0", 18, "major", "ETH staked through Lido: follows the ETH price and slowly grows with staking rewards."),
    ("LINK", "Chainlink", "0x514910771AF9Ca656af840dff83E8264EcF986CA", 18, "defi", "Chainlink: a service that brings prices and other outside data onto the blockchain."),
    ("UNI", "Uniswap", "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984", 18, "defi", "The token of Uniswap, the largest DEX, which our trades also go through."),
    ("AAVE", "Aave", "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9", 18, "defi", "The token of Aave, the largest service for lending and borrowing crypto."),
    ("LDO", "Lido DAO", "0x5A98FcBEA516Cf06857215779Fd812CA3beF1B32", 18, "defi", "The governance token of Lido, the biggest ETH staking service."),
    ("ENA", "Ethena", "0x57e114B691Db790C35207b2e685D4A43181e6061", 18, "defi", "The token of Ethena, a protocol that issues the \"synthetic dollar\" USDe."),
    ("ONDO", "Ondo", "0xfAbA6f8e4a5E8Ab82F62fe7C39859FA577269BE3", 18, "defi", "Ondo brings traditional assets such as US Treasury bonds onto the blockchain."),
    ("CRV", "Curve DAO", "0xD533a949740bb3306d119CC777fa900bA034cd52", 18, "defi", "The token of Curve, an exchange used mostly for swapping stablecoins."),
    ("COMP", "Compound", "0xc00e94Cb662C3520282E6f5717214004A7f26888", 18, "defi", "The token of Compound, one of the first crypto lending services."),
    ("SNX", "Synthetix", "0xC011a73ee8576Fb46F5E1c5751cA3B9Fe0af2a6F", 18, "defi", "The token of Synthetix, a platform for trading derivatives."),
    ("1INCH", "1inch", "0x111111111117dC0aa78b770fA6A738034120C302", 18, "defi", "The token of 1inch, a service that finds the best exchange rate across many DEXes."),
    ("SUSHI", "SushiSwap", "0x6B3595068778DD592e39A122f4f5a5cF09C90fE2", 18, "defi", "The token of SushiSwap, a DEX that started as a copy of Uniswap."),
    ("GRT", "The Graph", "0xc944E90C64B2c07662A292be6244BDf05Cda44a7", 18, "defi", "The Graph: a \"search engine\" for blockchain data used by apps."),
    ("ENS", "Ethereum Name Service", "0xC18360217D8F7Ab5e7c516566761Ea12Ce7F9D72", 18, "defi", "The token of the Ethereum Name Service: addresses like name.eth instead of long 0x… strings."),
    ("ARB", "Arbitrum", "0xB50721BCf8d664c30412Cfbc6cf7a15145234ad1", 18, "defi", "The token of Arbitrum, a network on top of Ethereum with cheap and fast transfers."),
    ("FET", "Fetch.ai", "0xaea46A60368A7bD060eec7DF8CBa43b7EF41Ad85", 18, "other", "The token of a project at the crossroads of crypto and artificial intelligence."),
    ("APE", "ApeCoin", "0x4d224452801ACEd8B2F0aebE155379bb5D594381", 18, "other", "The token of the Bored Ape Yacht Club community, a well-known NFT collection."),
    ("PEPE", "Pepe", "0x6982508145454Ce325dDbE47a25d4ec3d2311933", 18, "meme", "A frog meme token. Nothing stands behind it; the price lives on crowd interest and swings hard."),
    ("SHIB", "Shiba Inu", "0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE", 18, "meme", "A dog meme token, one of the oldest and biggest. Its price follows the market's mood."),
    ("FLOKI", "Floki", "0xcf0C122c6b73ff809C693DB761e7BaeBe62b6a2E", 9, "meme", "A meme token named after Elon Musk's dog. High risk, sharp swings."),
    ("MOG", "Mog Coin", "0xaaeE1A9723aaDB7afA2810263653A34bA2C21C7a", 18, "meme", "A cat meme token. Very cheap per coin, with big price swings."),
]


def seed(apps, schema_editor):
    Network = apps.get_model("bot", "Network")
    Token = apps.get_model("bot", "Token")
    eth = Network.objects.create(
        name="Ethereum", slug="ethereum", chain_id=1, rpc_env="WEB3_PROVIDER_ETHEREUM",
        native_symbol="ETH", explorer_url="https://etherscan.io", gecko_id="eth",
        router_address=cs("0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"),     # Uniswap V2 Router02
        wrapped_native=cs("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"),     # WETH
        stable_address=cs("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"), stable_decimals=6,  # USDC
        v3_router=cs("0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"),          # Uniswap SwapRouter02
        v3_quoter=cs("0x61fFE014bA17989E743c5F6cB21bF9697530B21e"),          # Uniswap QuoterV2
        multicall_address=cs("0xcA11bde05977b3631167028862bE2a173976CA11"),  # Multicall3
        private_rpc_url="https://rpc.flashbots.net/fast",                    # Flashbots Protect
    )
    for symbol, name, address, decimals, category, description in TOKENS:
        Token.objects.create(network=eth, symbol=symbol, name=name, address=cs(address), decimals=decimals,
                             category=category, description=description, is_verified=True)
    Network.objects.create(name="Robinhood Chain", slug="robinhood", rpc_env="WEB3_PROVIDER_ROBINHOOD", native_symbol="ETH", is_active=False)


class Migration(migrations.Migration):
    dependencies = [("bot", "0002_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
