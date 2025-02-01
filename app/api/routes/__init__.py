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
    "HOL": "Holesky",
    "SEP": "Sepolia",
    "BST": "Binance Testnet",
}

NAMES = {
    "BTC": "Bitcoin",
    "USDT": "USD Tether",
    "USDC": "USD coin",
    "WBTC": "Wrapped Bitcoin",
    "LINK": "ChainLink",
    "zUSDT": "Zex USDT",
    "zEIGEN": "Zex Eigen",
    "zWBTC": "Zex Wrapped Bitcoin",
    "ETH": "Ethereum",
    "BNB": "BNB",
}
