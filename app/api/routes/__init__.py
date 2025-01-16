from app.config import settings

USDT_MAINNET = settings.zex.usdt_mainnet

CHAIN_TYPES = {
    "BTC": "native_only",
    "POL": "evm",
    "BSC": "evm",
    "ARB": "evm",
    "OPT": "evm",
}

NETWORK_NAME = {
    "BTC": "Bitcoin",
    "POL": "Polygon",
    "BSC": "Binance Smart Chain",
    "ARB": "Arbitrum",
    "OPT": "Optimism",
}

NAMES = {
    "BTC": "Bitcoin",
    "USDT": "USD Tether",
    "USDC": "USD coin",
    "WBTC": "Wrapped Bitcoin",
    "LINK": "ChainLink",
}
