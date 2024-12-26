from fastapi import APIRouter

from app import zex
from app.api.cache import timed_lru_cache
from app.config import settings
from app.models.response import Chain, ExchangeInfoResponse, Symbol, Token

from . import CHAIN_TYPES, NAMES, USDT_MAINNET

router = APIRouter()

market_filter_list = [
    "BTC-USDT",
    "LINK-USDT",
]

token_filter_list = [
    "BTC",
    "USDT",
    "LINK",
]


@router.get("/depth")
async def depth(symbol: str, limit: int = 500):
    return zex.get_order_book(symbol.upper(), limit)


def get_token_info(token) -> Token:
    t = Token(
        token=token,
        chainType="evm" if token[:3] not in ["BTC"] else "native_only",
        price=zex.markets[f"{token}-{USDT_MAINNET}"].get_last_price()
        if f"{token}-{USDT_MAINNET}" in zex.markets
        else 0
        if token != USDT_MAINNET
        else 1,
        change_24h=zex.markets[f"{token}-{USDT_MAINNET}"].get_price_change_24h_percent()
        if token != USDT_MAINNET and f"{token}-{USDT_MAINNET}" in zex.markets
        else 0,
        name=NAMES.get(token, token),
        symbol=token,
    )
    return t


@timed_lru_cache(seconds=60 if settings.zex.mainnet else 1)
def _exchange_info_response():
    return ExchangeInfoResponse(
        timezone="UTC",
        symbols=[
            Symbol(
                symbol=name,
                lastPrice=market.get_last_price(),
                volume24h=market.get_volume_24h(),
                priceChange24h=market.get_price_change_24h_percent(),
                high24h=market.get_high_24h(),
                low24h=market.get_low_24h(),
                priceChange7D=market.get_price_change_7d_percent(),
            )
            for name, market in zex.markets.items()
            if name in market_filter_list
        ],
        tokens=[
            get_token_info(token)
            for token in zex.assets.keys()
            if token in token_filter_list
        ],
        chains=[
            Chain(
                chain=c,
                chainType=CHAIN_TYPES[c],
            )
            for c in zex.deposits.keys()
        ],
    )


@router.get("/exchangeInfo")
async def exhange_info() -> ExchangeInfoResponse:
    return _exchange_info_response()


@router.get("/pairs")
async def pairs():
    return [pair for pair in zex.markets.keys() if pair in market_filter_list]


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
