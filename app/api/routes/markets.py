from fastapi import APIRouter

from app import zex
from app.api.cache import timed_lru_cache
from app.models.response import Chain, ExchangeInfoResponse, Symbol, Token

from . import CHAIN_TYPES, NAMES, SYMBOLS, TAGS, USDT_MAINNET

router = APIRouter()

market_filter_list = [
    "BTC:1-POL:1",
    "XMR:1-POL:1",
    "POL:4-POL:1",
    "BSC:4-POL:1",
    "ARB:4-POL:1",
]

token_filter_list = [
    "BTC:1",
    "XMR:1",
    "POL:1",
    "POL:4",
    "BSC:4",
    "ARB:4",
]


@router.get("/depth")
async def depth(symbol: str, limit: int = 500):
    return zex.get_order_book(symbol.upper(), limit)


def get_token_info(token) -> Token:
    chain = token[:3]
    id = int(token[4:])
    address = zex.token_id_to_contract_on_chain_lookup.get(chain, {}).get(
        id, "0x" + "0" * 40
    )
    t = Token(
        chain=chain,
        id=id,
        address=address,
        chainType="evm" if chain not in ["BTC", "XMR"] else "native_only",
        decimals=zex.token_decimal_on_chain_lookup.get(chain, {}).get(address, 8),
        price=zex.markets[f"{token}-{USDT_MAINNET}"].get_last_price()
        if f"{token}-{USDT_MAINNET}" in zex.markets
        else 0
        if token != USDT_MAINNET
        else 1,
        change_24h=zex.markets[f"{token}-{USDT_MAINNET}"].get_price_change_24h_percent()
        if token != USDT_MAINNET and f"{token}-{USDT_MAINNET}" in zex.markets
        else 0,
        name=NAMES.get(token, token),
        symbol=SYMBOLS.get(token, token),
        tag=TAGS.get(token, token),
    )
    return t


@timed_lru_cache(seconds=60)
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
            for c in zex.deposited_blocks.keys()
        ],
    )


@router.get("/exchangeInfo")
async def exhange_info() -> ExchangeInfoResponse:
    return _exchange_info_response()


@router.get("/pairs")
async def pairs():
    return list(zex.markets.keys())


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
