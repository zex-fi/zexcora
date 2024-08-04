from fastapi import APIRouter

from app import zex
from app.models.response import ExchangeInfoResponse, Symbol

router = APIRouter()


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
async def exhange_info():
    resp = ExchangeInfoResponse(
        timezone="UTC",
        symbols=[
            Symbol(
                symbol=name,
                lastPrice=market.get_last_price(),
                volume24h=market.get_veolume_24h(),
                priceChange24h=market.get_price_change_24h(),
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
