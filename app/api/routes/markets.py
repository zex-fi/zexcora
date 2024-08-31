from fastapi import APIRouter

from app import zex
from app.models.response import Asset, ExchangeInfoResponse, Symbol

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
    "HOL:3": "btc",
    "HOL:4": "link",
    "BST:1": "usdt",
    "BST:2": "usdc",
    "BST:3": "btc",
    "BST:4": "link",
    "SEP:1": "usdt",
    "SEP:2": "usdc",
    "SEP:3": "btc",
    "SEP:4": "link",
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
                baseAsset=Asset(
                    chain=market.base_token[:3],
                    id=int(market.base_token[4:]),
                    chainType="evm"
                    if market.base_token[:3] not in ["BTC", "XMR"]
                    else "native_only",
                    address=None,  # TODO: implement
                    decimals=DECIMALS[market.base_token],
                    price=zex.markets[
                        f"{market.base_token}-{USDT_MAINNET}"
                    ].get_last_price()
                    if market.base_token != USDT_MAINNET
                    else 1,
                    change_24h=zex.markets[
                        f"{market.base_token}-{USDT_MAINNET}"
                    ].get_price_change_24h_percent()
                    if market.base_token != USDT_MAINNET
                    else 0,
                    tag=TAGS[market.base_token],
                ),
                quoteAsset=Asset(
                    chain=market.quote_token[:3],
                    id=int(market.quote_token[4:]),
                    address=None,  # TODO: implement
                    chainType="evm"
                    if market.quote_token[:3] not in ["BTC", "XMR"]
                    else "native_only",
                    decimals=DECIMALS[market.quote_token],
                    price=zex.markets[
                        f"{market.quote_token}-{USDT_MAINNET}"
                    ].get_last_price()
                    if market.quote_token != USDT_MAINNET
                    else 1,
                    change_24h=zex.markets[
                        f"{market.quote_token}-{USDT_MAINNET}"
                    ].get_price_change_24h_percent()
                    if market.quote_token != USDT_MAINNET
                    else 0,
                    tag=TAGS[market.quote_token],
                ),
                lastPrice=market.get_last_price(),
                volume24h=market.get_volume_24h(),
                priceChange24h=market.get_price_change_24h_percent(),
                high24h=market.get_high_24h(),
                low24h=market.get_low_24h(),
                priceChange7D=market.get_price_change_7D_percent(),
            )
            for name, market in zex.markets.items()
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
