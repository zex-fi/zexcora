from fastapi import APIRouter

from app import zex
from app.models.response import Chain, ExchangeInfoResponse, Symbol, Token

router = APIRouter()

USDT_MAINNET = "HOL:1"

DECIMALS = {
    "BTC:0": 8,
    "XMR:0": 12,
    "HOL:1": 6,
    "HOL:2": 6,
    "HOL:3": 8,
    "HOL:4": 18,
    "BST:1": 6,
    "BST:2": 6,
    "BST:3": 8,
    "BST:4": 18,
    "SEP:1": 6,
    "SEP:2": 6,
    "SEP:3": 8,
    "SEP:4": 18,
}

TAGS = {
    "BTC:0": "btc",
    "XMR:0": "xmr",
    "HOL:1": "usdt",
    "HOL:2": "usdc",
    "HOL:3": "wbtc",
    "HOL:4": "link",
    "BST:1": "usdt",
    "BST:2": "usdc",
    "BST:3": "wbtc",
    "BST:4": "link",
    "SEP:1": "usdt",
    "SEP:2": "usdc",
    "SEP:3": "wbtc",
    "SEP:4": "link",
}

CHAIN_TYPES = {
    "BTC": "native_only",
    "XMR": "native_only",
    "HOL": "evm",
    "BST": "evm",
    "SEP": "evm",
}

NAMES = {
    "BTC:0": "Bitcoin",
    "XMR:0": "Monero",
    "HOL:1": "USD Tether",
    "HOL:2": "USD coin",
    "HOL:3": "Wrapped Bitcoin",
    "HOL:4": "ChainLink",
    "BST:1": "USD Tether",
    "BST:2": "USD coin",
    "BST:3": "Wrapped Bitcoin",
    "BST:4": "ChainLink",
    "SEP:1": "USD Tether",
    "SEP:2": "USD coin",
    "SEP:3": "Wrapped Bitcoin",
    "SEP:4": "ChainLink",
}

SYMBOLS = {
    "BTC:0": "BTC",
    "XMR:0": "XMR",
    "HOL:1": "USDT",
    "HOL:2": "USDC",
    "HOL:3": "WBTC",
    "HOL:4": "LINK",
    "BST:1": "USDT",
    "BST:2": "USDC",
    "BST:3": "WBTC",
    "BST:4": "LINK",
    "SEP:1": "USDT",
    "SEP:2": "USDC",
    "SEP:3": "WBTC",
    "SEP:4": "LINK",
}


@router.get("/depth")
async def depth(symbol: str, limit: int = 500):
    return zex.get_order_book(symbol.upper(), limit)


@router.get("/trades")
async def trades(symbol: str, limit: int = 500):
    raise NotImplementedError()


@router.get("/historicalTrades")
async def historical_trades(symbol: str, limit: int = 500, fromId: int | None = None):
    raise NotImplementedError()


@router.get("/exchangeInfo")
async def exhange_info() -> ExchangeInfoResponse:
    resp = ExchangeInfoResponse(
        timezone="UTC",
        symbols=[
            Symbol(
                symbol=name,
                lastPrice=market.get_last_price(),
                volume24h=market.get_volume_24h(),
                priceChange24h=market.get_price_change_24h_percent(),
                high24h=market.get_high_24h(),
                low24h=market.get_low_24h(),
                priceChange7D=market.get_price_change_7D_percent(),
            )
            for name, market in zex.markets.items()
        ],
        tokens=[
            Token(
                chain=token[:3],
                id=int(token[4:]),
                address=None,  # TODO: implement
                chainType="evm" if token[:3] not in ["BTC", "XMR"] else "native_only",
                decimals=DECIMALS[token],
                price=zex.markets[f"{token}-{USDT_MAINNET}"].get_last_price()
                if token != USDT_MAINNET
                else 1,
                change_24h=zex.markets[
                    f"{token}-{USDT_MAINNET}"
                ].get_price_change_24h_percent()
                if token != USDT_MAINNET
                else 0,
                name=NAMES[token],
                symbol=SYMBOLS[token],
                tag=TAGS[token],
            )
            for token in zex.balances.keys()
        ],
        chains=[
            Chain(chain=c, chainType=CHAIN_TYPES[c])
            for c in zex.deposited_blocks.keys()
        ],
    )
    return resp


@router.get("/pairs")
async def pairs():
    return list(zex.markets.keys())


@router.get("/aggTrades")
async def agg_trades(
    symbol: str,
    fromId: int | None = None,
    startTime: int | None = None,
    endTime: int | None = None,
    limit: int = 500,
):
    raise NotImplementedError()


@router.get("/klines")
async def klines(
    symbol: str,
    interval: str,
    startTime: int | None = None,
    endTime: int | None = None,
    limit: int = 500,
):
    base_klines = zex.get_kline(symbol.upper())
    if len(base_klines) == 0:
        return []
    if not startTime:
        startTime = base_klines.index[0]

    if not endTime:
        endTime = base_klines.iloc[-1]["CloseTime"]

    return [
        [
            idx,
            x["Open"],
            x["High"],
            x["Low"],
            x["Close"],
            x["Volume"],
            x["CloseTime"],
            0,
            x["NumberOfTrades"],
            0,
            0,
            -1,
        ]
        for idx, x in base_klines.iterrows()
        if startTime <= idx and endTime >= x["CloseTime"]
    ][-limit:]
