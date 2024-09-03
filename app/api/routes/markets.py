from fastapi import APIRouter

from app import zex
from app.models.response import Chain, ExchangeInfoResponse, Symbol, Token

from . import CHAIN_CONTRACTS, CHAIN_TYPES, DECIMALS, NAMES, SYMBOLS, TAGS, USDT_MAINNET

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
                if f"{token}-{USDT_MAINNET}" in zex.markets
                else 0
                if token != USDT_MAINNET
                else 1,
                change_24h=zex.markets[
                    f"{token}-{USDT_MAINNET}"
                ].get_price_change_24h_percent()
                if token != USDT_MAINNET and f"{token}-{USDT_MAINNET}" in zex.markets
                else 0,
                name=NAMES[token],
                symbol=SYMBOLS[token],
                tag=TAGS[token],
            )
            for token in zex.balances.keys()
        ],
        chains=[
            Chain(
                chain=c,
                chainType=CHAIN_TYPES[c],
                contractAddress=CHAIN_CONTRACTS.get(c, None),
            )
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
